"""Offline Quality Gate & mock verification tests for the 2-layer stylist benchmark."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from sqlmodel import Session

from app.agents.coordinator import generate_grounded_explanation_vi
from app.agents.state import OutfitItemSlot, RankedOutfit, StylistContext
from app.models.entities import OutfitSlotRole, WardrobeCategory
from tests.evaluation.benchmark.judge import (
    CrossFamilyJudgeClient,
    JsonlResultCache,
    JudgeConfig,
    run_judge_calibration,
)
from tests.evaluation.benchmark.reporting import render_markdown_report
from tests.evaluation.benchmark.runner import (
    estimate_api_budget,
    load_benchmark_bundle,
    run_benchmark,
    select_cases_for_split,
)
from tests.evaluation.benchmark.systems import (
    AbortedLiveRunError,
    TelemetryLLMProbe,
    run_single_prompt_gemini_baseline,
    seed_case_user,
)


def test_benchmark_fixtures_shape_split_and_no_leakage() -> None:
    """Verify frozen wardrobes (30F + 27M), 40 representative (28 dev / 12 holdout), 12 stress, and calibration."""
    bundle = load_benchmark_bundle()
    wardrobes = bundle["wardrobes"]["wardrobes"]
    bench = bundle["benchmark"]
    cal = bundle["calibration"]

    assert len(wardrobes["female_realistic_30"]) == 30
    assert len(wardrobes["male_realistic_27"]) == 27

    rep_cases = bench["representative_cases"]
    stress_cases = bench["stress_cases"]
    assert len(rep_cases) == 40
    assert len(stress_cases) == 12

    dev_cases = [c for c in rep_cases if c["split"] == "dev"]
    holdout_cases = [c for c in rep_cases if c["split"] == "holdout"]
    assert len(dev_cases) == 28
    assert len(holdout_cases) == 12

    # Ensure strict split disjointness and non-overlapping queries between dev & holdout
    dev_ids = {c["id"] for c in dev_cases}
    hold_ids = {c["id"] for c in holdout_cases}
    assert dev_ids.isdisjoint(hold_ids)
    dev_queries = {c["query"].strip().lower() for c in dev_cases}
    hold_queries = {c["query"].strip().lower() for c in holdout_cases}
    assert dev_queries.isdisjoint(hold_queries)

    # Every query contains Vietnamese diacritics
    assert all(any(ord(ch) > 127 for ch in c["query"]) for c in rep_cases + stress_cases)

    # Calibration fixture completeness
    assert cal is not None
    assert len(cal["pointwise_samples"]) == 16
    assert len(cal["pairwise_samples"]) == 10


def test_offline_two_layer_benchmark_and_ablation_gains(
    migrated_database: tuple[object, object],
) -> None:
    """Run offline 2-layer benchmark across baselines and ablations with 0 external API calls."""
    _, engine = migrated_database
    bundle = load_benchmark_bundle()

    report = run_benchmark(
        bundle=bundle,
        systems=("B0", "B1", "M-Full", "M-NoLoop1", "M-NoLoop2", "M-NoPersonalization"),
        split="all",
        include_stress=True,
        include_noise=False,
        live_llm=False,
        live_weather=False,
        judge=None,
        engine_override=engine,
    )

    assert report["metadata"]["run_complete"] is True
    assert report["metadata"]["representative_case_count"] == 40
    assert report["metadata"]["stress_case_count"] == 12

    rep = report["representative_summary"]
    m_full = rep["M-Full"]

    # Layer A mandatory technical invariants must be 100% for M-Full
    assert m_full["layer_a"]["case_pass_rate"] == 1.0
    assert m_full["layer_a"]["valid_item_grounding_rate"] == 1.0
    assert m_full["layer_a"]["outfit_structure_validity_rate"] == 1.0
    assert m_full["layer_a"]["must_avoid_compliance_rate"] == 1.0
    assert m_full["layer_a"]["explanation_factuality_rate"] == 1.0
    assert m_full["layer_a"]["bounded_and_persist_rate"] == 1.0

    # B1 context extraction accuracy and B3 personalization / wear avoidance
    assert m_full["layer_b"]["b1_context"]["micro_field_accuracy"] >= 0.85
    m_nopers = rep["M-NoPersonalization"]
    assert (
        m_full["layer_b"]["b3_personalization"]["profile_differentiation_rate"]
        > m_nopers["layer_b"]["b3_personalization"]["profile_differentiation_rate"]
    )
    assert m_nopers["layer_b"]["b3_personalization"]["profile_differentiation_rate"] == 0.0
    assert m_full["layer_b"]["b3_personalization"]["recent_wear_avoid_rate"] == 1.0
    assert m_full["functional"]["pass_rate"] >= 0.90

    # B0 random baseline violates constraints or functional accuracy compared to M-Full
    b0 = rep["B0"]
    assert b0["functional"]["pass_rate"] < m_full["functional"]["pass_rate"]

    # Diagnostic Stress Suite (isolated from representative cases): M-Full passes 12/12
    stress = report["stress_summary"]
    assert stress["M-Full"]["pass_ratio"] == "12/12"
    assert stress["M-Full"]["layer_a_ratio"] == "12/12"
    # Without Loop 1 or Loop 2, stress suite passes strictly fewer cases
    assert stress["M-NoLoop1"]["pass_rate"] < stress["M-Full"]["pass_rate"]
    assert stress["M-NoLoop2"]["pass_rate"] < stress["M-Full"]["pass_rate"]
    assert stress["B1"]["pass_rate"] < stress["M-Full"]["pass_rate"]

    # Budget estimator sanity check (0 network calls)
    rep_cases, stress_cases = select_cases_for_split(bundle["benchmark"], split="smoke", include_stress=False)
    budget = estimate_api_budget(
        rep_cases=rep_cases,
        stress_cases=stress_cases,
        systems=("B0", "B1", "B2", "M-Full"),
        live_llm=True,
        judge_enabled=True,
        include_noise=False,
        calibrate_judge=True,
        calibration_data=bundle["calibration"],
    )
    assert budget["estimated_gemini_calls"] > 0
    assert budget["estimated_judge_calls"] > 0

    # Markdown report rendering contains every required section
    md = render_markdown_report(report)
    assert "Lớp A — Kiểm Định Kỹ Thuật Bắt Buộc" in md
    assert "Lớp B — Benchmark Chất Lượng Tư Vấn" in md
    assert "Net Loop Impact" in md
    assert "Diagnostic Stress Suite" in md
    assert "Failure Breakdown" in md
    assert "Giới Hạn Phương Pháp" in md


def test_single_prompt_baseline_and_telemetry_probe_mock(
    migrated_database: tuple[object, object],
) -> None:
    """Verify SinglePromptGeminiBaseline exposes fabricated IDs in Layer A and TelemetryProbe catches silent fallback & 429 aborts."""
    _, engine = migrated_database
    bundle = load_benchmark_bundle()
    wardrobes = bundle["wardrobes"]["wardrobes"]
    smoke_cases = [c for c in bundle["benchmark"]["representative_cases"] if c["id"] in {"r01", "r03"}][:2]

    # Single-prompt LLM returns a fabricated item_id on r01 -> Layer A must catch grounding violation!
    def _mock_single_prompt(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        text = body["contents"][0]["parts"][0]["text"]
        if "phỏng vấn" in text:
            payload = {
                "status": "ok",
                "outfits": [
                    {
                        "rank": 1,
                        "item_ids": ["f_top_01", "f_bot_01", "fabricated_shoe_999"],
                        "explanation_vi": "Phối [Áo sơ mi] trắng, [Quần tây] đen và [Giày fake].",
                    }
                ],
            }
        else:
            payload = {
                "status": "ok",
                "outfits": [
                    {
                        "rank": 1,
                        "item_ids": ["f_top_03", "f_bot_04", "f_ftw_01"],
                        "explanation_vi": "Phối [Áo thun] trắng, [Quần short] khaki và [Giày sneaker] trắng.",
                    }
                ],
            }
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
        )

    with Session(engine) as session:
        raw_to_db = seed_case_user(
            session,
            run_user_id="u_b2_mock_test",
            wardrobe_specs=wardrobes["female_realistic_30"],
            profile_spec=None,
            wear_history=[],
            fixed_now=__import__("datetime").datetime(2026, 11, 19, 2, 0, tzinfo=__import__("datetime").timezone.utc),
        )
        db_to_raw = {v: k for k, v in raw_to_db.items()}
        sp_client = httpx.Client(transport=httpx.MockTransport(_mock_single_prompt))
        res = run_single_prompt_gemini_baseline(
            session=session,
            run_user_id="u_b2_mock_test",
            case=smoke_cases[0],
            db_to_raw=db_to_raw,
            api_key="fake-key",
            model="gemini-test",
            http_client=sp_client,
        )
        from tests.evaluation.benchmark.metrics import verify_layer_a_for_case

        la = verify_layer_a_for_case(
            session=session,
            run_user_id="u_b2_mock_test",
            request_id="req_sp",
            system_id="B2",
            case=smoke_cases[0],
            result=res,
            check_persistence=False,
        )
        assert la.passed is False
        assert any("fabricated_shoe_999" in v for v in la.violations)

    # TelemetryLLMProbe detects hallucinated batch explanation fallback & aborts after 3 HTTP failures
    class _FallbackProvider:
        def extract_context(self, **kwargs: Any) -> dict[str, Any]:
            return {
                "occasion": "interview",
                "time_of_day": "morning",
                "weather_condition": "cool",
                "target_formality_range": [4, 5],
                "weather_source": "default",
                "needs_clarification": False,
                "confidence": 0.9,
            }

        def generate_outfit_explanations(self, *, outfits: list[dict[str, Any]], **kwargs: Any) -> list[str]:
            # Hallucinates an external item [Túi Gucci giả] -> coordinator must drop & fall back deterministically
            return ["Phối [Áo sơ mi] trắng, [Quần tây] đen, [Giày cao gót] đen cùng [Túi Gucci giả]." for _ in outfits]

    probe_fallback = TelemetryLLMProbe(_FallbackProvider())
    rep_fb = run_benchmark(
        bundle={
            "benchmark": {
                **bundle["benchmark"],
                "representative_cases": [smoke_cases[0]],
            },
            "wardrobes": bundle["wardrobes"],
            "calibration": bundle["calibration"],
        },
        systems=("M-Full",),
        split="all",
        include_stress=False,
        live_llm=True,
        llm_provider_override=probe_fallback,
        engine_override=engine,
    )
    m_b4 = rep_fb["representative_summary"]["M-Full"]["layer_b"]["b4_explanation"]
    assert m_b4["explanation_llm_accepted_rate"] == 0.0  # Silent fallback caught accurately!

    class _Always429Provider:
        def extract_context(self, **kwargs: Any) -> dict[str, Any]:
            req = httpx.Request("POST", "https://example.com")
            resp = httpx.Response(429, request=req)
            raise httpx.HTTPStatusError("rate limited", request=req, response=resp)

    probe_abort = TelemetryLLMProbe(_Always429Provider(), max_consecutive_failures=3)
    for _ in range(2):
        try:
            probe_abort.extract_context(query="x", location=None, current_date=__import__("datetime").date(2026, 11, 19))
        except httpx.HTTPStatusError:
            pass
    try:
        probe_abort.extract_context(query="x", location=None, current_date=__import__("datetime").date(2026, 11, 19))
        raise AssertionError("Expected AbortedLiveRunError on 3rd consecutive failure")
    except AbortedLiveRunError:
        pass


def test_cross_family_judge_bidirectional_bias_calibration_and_cache(tmp_path: Path) -> None:
    """Verify cross-family bias warning, bidirectional consistency, disk cache deduplication, and calibration."""
    # 1. Bias warning triggers on gemini judge model, not on cross-family gpt/claude models
    gemini_judge = CrossFamilyJudgeClient(JudgeConfig(provider="openai_compatible", model="gemini-2.5-pro"))
    assert gemini_judge.same_family_bias is True

    # 2. Mock OpenAI-compatible cross-family judge checking calibration & bidirectional comparison + cache
    call_counter = 0

    def _is_bad_option(context_block: str, option_block: str) -> bool:
        if "Áo ba lỗ" in option_block or "Dép" in option_block or "Áo măng tô" in option_block:
            return True
        if "Thắt lưng da cá sấu" in option_block or "Áo Hoodie" in option_block:
            return True
        if "không mặc màu đen" in context_block and "màu=black" in option_block:
            return True
        if "trời mưa" in context_block and "Đầm dạ hội" in option_block:
            return True
        if ("phỏng vấn" in context_block or "đám cưới" in context_block) and "Quần short" in option_block:
            return True
        return False

    def _mock_judge_http(request: httpx.Request) -> httpx.Response:
        nonlocal call_counter
        call_counter += 1
        body = json.loads(request.content.decode("utf-8"))
        user_msg = body["messages"][1]["content"]
        if "Phương án 1" in user_msg and "Phương án 2" in user_msg:
            head, rest = user_msg.split("--- Phương án 1 ---", 1)
            part1, part2 = rest.split("--- Phương án 2 ---", 1)
            p1_bad = _is_bad_option(head, part1)
            p2_bad = _is_bad_option(head, part2)
            if not p1_bad and p2_bad:
                w = "1"
            elif p1_bad and not p2_bad:
                w = "2"
            else:
                w = "tie"
            ans = {"winner": w, "reason_vi": "Đúng ngữ cảnh và phối hợp lý."}
        else:
            is_bad = _is_bad_option(user_msg, user_msg)
            score = 1.5 if is_bad else 4.5
            ans = {
                "occasion_formality": score,
                "weather_comfort_function": score,
                "aesthetic_harmony": score,
                "explanation_usefulness": score,
                "rationale_vi": "Đánh giá mock.",
            }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ans)}}]})

    cache = JsonlResultCache(tmp_path / "judge_cache.jsonl")
    judge = CrossFamilyJudgeClient(
        JudgeConfig(provider="openai_compatible", base_url="https://mock.local/v1", api_key="k", model="gpt-4.1-mini"),
        cache=cache,
        http_client=httpx.Client(transport=httpx.MockTransport(_mock_judge_http)),
    )
    assert judge.same_family_bias is False

    bundle = load_benchmark_bundle()
    cal_data = bundle["calibration"]
    cal_res = run_judge_calibration(judge, cal_data)
    assert cal_res["pointwise_accuracy"] == 1.0
    assert cal_res["pairwise_accuracy"] == 1.0
    assert cal_res["position_consistency_rate"] == 1.0

    # Reload cache from disk in a fresh Judge instance -> repeated calibration makes ZERO HTTP calls!
    calls_before_reload = call_counter
    judge_cached = CrossFamilyJudgeClient(
        JudgeConfig(provider="openai_compatible", base_url="https://mock.local/v1", api_key="k", model="gpt-4.1-mini"),
        cache=JsonlResultCache(tmp_path / "judge_cache.jsonl"),
        http_client=httpx.Client(transport=httpx.MockTransport(_mock_judge_http)),
    )
    cal_res_2 = run_judge_calibration(judge_cached, cal_data)
    assert call_counter == calls_before_reload
    assert judge_cached.api_calls == 0
    assert judge_cached.cache_hits == len(cal_data["pointwise_samples"]) + 2 * len(cal_data["pairwise_samples"])
    assert cal_res_2["pointwise_accuracy"] == 1.0


def test_aborted_live_run_error_is_not_swallowed_by_context_or_explanation_fallbacks(
    migrated_database: tuple[object, object],
):
    """AbortedLiveRunError must propagate past context_agent and coordinator fallbacks and mark run_complete=False."""
    _, engine = migrated_database

    class _AlwaysFailingProvider:
        def __init__(self) -> None:
            self.calls = 0

        def extract_context(self, **kwargs):
            self.calls += 1
            raise RuntimeError("Simulated 429 quota exceeded")

        def generate_outfit_explanations(self, **kwargs):
            self.calls += 1
            raise RuntimeError("Simulated 429 quota exceeded")

    failing_provider = _AlwaysFailingProvider()
    bundle = load_benchmark_bundle()
    report = run_benchmark(
        bundle=bundle,
        split="dev",
        systems=["M-Full"],
        include_stress=False,
        llm_provider_override=failing_provider,
        engine_override=engine,
    )
    assert report["metadata"]["run_complete"] is False
    assert report["metadata"]["aborted_reason"] is not None
    assert "consecutive provider failures" in report["metadata"]["aborted_reason"]
    # Stopped right at default max_consecutive_failures=3 instead of running all 20 dev cases
    assert failing_provider.calls == 3


def test_judge_config_from_env_isolates_provider_keys_and_base_urls(monkeypatch: pytest.MonkeyPatch):
    """JudgeConfig.from_env must never send OPENAI_API_KEY to Anthropic/Gemini and must use provider-specific base URLs."""
    monkeypatch.delenv("BENCH_JUDGE_PROVIDER", raising=False)
    monkeypatch.delenv("BENCH_JUDGE_BASE_URL", raising=False)
    monkeypatch.delenv("BENCH_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("BENCH_JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-only")

    anth = JudgeConfig.from_env(provider="anthropic")
    assert anth.base_url == "https://api.anthropic.com/v1"
    assert anth.api_key == ""  # Never falls back to OPENAI_API_KEY

    gem = JudgeConfig.from_env(provider="gemini")
    assert gem.base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert gem.api_key == ""  # Never falls back to OPENAI_API_KEY
    assert gem.model.startswith("gemini")

    oai = JudgeConfig.from_env(provider="openai_compatible")
    assert oai.base_url == "https://api.openai.com/v1"
    assert oai.api_key == "sk-openai-only"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-real")
    assert JudgeConfig.from_env(provider="anthropic").api_key == "sk-ant-real"
    assert JudgeConfig.from_env(provider="gemini").api_key == "gm-real"


def test_disable_personalization_ablation_skips_saved_avoid_and_recent_wear_penalty(
    migrated_database: tuple[object, object],
):
    """M-NoPersonalization must bypass both wardrobe_agent's _apply_saved_avoid_filter and recent wear penalty."""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from app.agents.stylist_graph import execute_stylist_recommendation
    from app.models.entities import User, UserPreference, WardrobeCategory, WardrobeItem
    from app.services.retrieval_document_service import refresh_retrieval_document

    _, engine = migrated_database
    fixed_now = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
    user_id = f"user_nopers_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.add(
            UserPreference(
                user_id=user_id,
                styles=["casual"],
                color_palettes=["neutral"],
                priorities=["comfort"],
                avoid_colors=["white"],  # Saved profile avoid color
            )
        )
        session.flush()

        # Best-scoring shirt is white AND worn 12h ago; alternative shirt is poor formal/color match
        items = [
            WardrobeItem(
                id="top-white-worn",
                user_id=user_id,
                category=WardrobeCategory.TOP,
                sub_category="shirt",
                primary_color="white",
                pattern="solid",
                material="cotton",
                style="formal",
                fit="regular",
                formality_level=5,
                comfort_level=5,
                weather_suitability=["cool", "warm"],
                functional_flags=["work"],
                last_worn_at=fixed_now - timedelta(hours=12),
                is_user_confirmed=True,
                is_active=True,
            ),
            WardrobeItem(
                id="top-orange-alt",
                user_id=user_id,
                category=WardrobeCategory.TOP,
                sub_category="shirt",
                primary_color="orange",
                pattern="floral",
                material="cotton",
                style="streetwear",
                fit="oversized",
                formality_level=4,
                comfort_level=2,
                weather_suitability=["cool", "warm"],
                functional_flags=[],
                is_user_confirmed=True,
                is_active=True,
            ),
            WardrobeItem(
                id="bot-black",
                user_id=user_id,
                category=WardrobeCategory.BOTTOM,
                sub_category="trousers",
                primary_color="black",
                pattern="solid",
                material="wool",
                style="formal",
                fit="regular",
                formality_level=5,
                comfort_level=4,
                weather_suitability=["cool", "warm"],
                functional_flags=["work"],
                is_user_confirmed=True,
                is_active=True,
            ),
            WardrobeItem(
                id="shoe-black",
                user_id=user_id,
                category=WardrobeCategory.FOOTWEAR,
                sub_category="oxford",
                primary_color="black",
                pattern="solid",
                material="leather",
                style="formal",
                fit="regular",
                formality_level=5,
                comfort_level=4,
                weather_suitability=["cool", "warm"],
                functional_flags=["work"],
                is_user_confirmed=True,
                is_active=True,
            ),
        ]
        for it in items:
            session.add(it)
        session.flush()
        for it in items:
            refresh_retrieval_document(session, it)
        session.commit()

        # With personalization enabled: saved avoid_colors=['white'] filters out top-white-worn!
        with_pers = execute_stylist_recommendation(
            {
                "request_id": "req-pers-on",
                "user_id": user_id,
                "user_query": "Đi phỏng vấn sáng nay mặc gì?",
                "enable_agent_loops": False,
                "disable_personalization": False,
            },
            session=session,
            clock=lambda: fixed_now,
        )
        assert with_pers["errors"] == []
        top1_pers_ids = {it.item_id for it in with_pers["ranked_outfits"][0].items}
        assert "top-orange-alt" in top1_pers_ids

        # With disable_personalization=True: NEITHER saved avoid NOR 48h wear penalty applies -> top-white-worn wins with 0 wear penalty!
        no_pers = execute_stylist_recommendation(
            {
                "request_id": "req-pers-off",
                "user_id": user_id,
                "user_query": "Đi phỏng vấn sáng nay mặc gì?",
                "enable_agent_loops": False,
                "disable_personalization": True,
            },
            session=session,
            clock=lambda: fixed_now,
        )
        assert no_pers["errors"] == []
        top1_nopers_ids = {it.item_id for it in no_pers["ranked_outfits"][0].items}
        assert "top-white-worn" in top1_nopers_ids
        assert all(n.conflict_type != "RECENT_WEAR_VS_BEST_FIT" for n in no_pers["conflict_notes"])
