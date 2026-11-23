"""Offline Quality Gate & mock verification tests for the 2-layer stylist benchmark."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import SecretStr
import pytest
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
    """Verify frozen wardrobes (30F + 27M), 56 representative (38 dev / 18 holdout), 12 stress, and calibration."""
    bundle = load_benchmark_bundle()
    wardrobes = bundle["wardrobes"]["wardrobes"]
    bench = bundle["benchmark"]
    cal = bundle["calibration"]

    assert len(wardrobes["female_realistic_30"]) == 30
    assert len(wardrobes["male_realistic_27"]) == 27

    rep_cases = bench["representative_cases"]
    stress_cases = bench["stress_cases"]
    assert len(rep_cases) == 56
    assert len(stress_cases) == 12

    dev_cases = [c for c in rep_cases if c["split"] == "dev"]
    holdout_cases = [c for c in rep_cases if c["split"] == "holdout"]
    assert len(dev_cases) == 38
    assert len(holdout_cases) == 18

    # Ensure strict split disjointness and non-overlapping queries between dev & holdout
    dev_ids = {c["id"] for c in dev_cases}
    hold_ids = {c["id"] for c in holdout_cases}
    assert dev_ids.isdisjoint(hold_ids)
    dev_queries = {c["query"].strip().lower() for c in dev_cases}
    hold_queries = {c["query"].strip().lower() for c in holdout_cases}
    assert dev_queries.isdisjoint(hold_queries)

    # Every query contains Vietnamese diacritics
    assert all(any(ord(ch) > 127 for ch in c["query"]) for c in rep_cases + stress_cases)

    # Calibration fixture completeness (20 pointwise with human_score + 12 coherent same-query pairwise)
    assert cal is not None
    assert len(cal["pointwise_samples"]) == 20
    assert len(cal["pairwise_samples"]) == 12
    assert all(s.get("human_score") is not None for s in cal["pointwise_samples"])
    assert all(bool(p.get("query")) for p in cal["pairwise_samples"])


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
        include_noise=True,
        live_llm=False,
        live_weather=False,
        judge=None,
        engine_override=engine,
    )

    assert report["metadata"]["run_complete"] is True
    assert report["metadata"]["representative_case_count"] == 56
    assert report["metadata"]["stress_case_count"] == 12

    rep = report["representative_summary"]
    m_full = rep["M-Full"]

    # Layer A mandatory technical invariants must be 100% for M-Full
    assert m_full["layer_a"]["case_pass_rate"] == 1.0
    assert m_full["layer_a"]["valid_item_grounding_rate"] == 1.0
    assert m_full["layer_a"]["outfit_structure_validity_rate"] == 1.0
    assert m_full["layer_a"]["must_avoid_compliance_rate"] == 1.0
    assert m_full["layer_a"]["explanation_factuality_rate"] == 1.0
    assert m_full["layer_a"]["canonical_bracket_rate"] == 1.0
    assert m_full["layer_a"]["bounded_and_persist_rate"] == 1.0

    # B1 context extraction accuracy (colloquial_implicit cases intentionally expose offline rule ceiling)
    assert m_full["layer_b"]["b1_context"]["micro_field_accuracy"] >= 0.78
    assert rep["B0"]["layer_b"]["b1_context"]["micro_field_accuracy"] is None
    m_nopers = rep["M-NoPersonalization"]
    assert (
        m_full["layer_b"]["b3_personalization"]["profile_differentiation_rate"]
        > m_nopers["layer_b"]["b3_personalization"]["profile_differentiation_rate"]
    )
    assert m_nopers["layer_b"]["b3_personalization"]["profile_differentiation_rate"] == 0.0
    assert m_full["layer_b"]["b3_personalization"]["contrastive_pair_diff_rate"] == 1.0
    assert m_full["layer_b"]["b3_personalization"]["recent_wear_avoid_rate"] == 1.0
    assert m_full["functional"]["pass_rate"] >= 0.80

    # Natural Loop 1 ablation gain across realistic wardrobes (r18, r49, r50, r51, r52)
    loop1_imp = report["ablation_impact"]["Loop 1 (M-Full vs M-NoLoop1)"]
    assert loop1_imp["improved_count"] >= 4
    assert loop1_imp["degraded_count"] == 0

    # Noise robustness tracks Top-1 ranking stability & Core Jaccard
    m_noise = report["noise_robustness"]["M-Full"]
    assert m_noise["top1_exact_stability_rate"] is not None
    assert m_noise["top1_mean_core_jaccard"] is not None

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

    # Markdown report rendering contains every required section and new columns
    md = render_markdown_report(report)
    assert "Lớp A — Kiểm Định Kỹ Thuật Bắt Buộc" in md
    assert "Cú pháp [Ngoặc]" in md
    assert "Lớp B — Benchmark Chất Lượng Tư Vấn" in md
    assert "Contrastive (B3)" in md
    assert "Net Loop Impact" in md
    assert "Top-1 Ổn Định (Flip Rate)" in md
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
                        # Plain-text factual explanation without square brackets -> fair Layer A passes factuality while canonical_bracket_outfits == 0
                        "explanation_vi": "Phối Áo thun trắng, Quần short khaki và Giày sneaker trắng gọn nhẹ cho chiều dạo phố.",
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

        # Fair Layer A: plain-text factually grounded B2 explanation passes factuality while canonical_bracket_outfits == 0
        res_plain = run_single_prompt_gemini_baseline(
            session=session,
            run_user_id="u_b2_mock_test",
            case=smoke_cases[1],
            db_to_raw=db_to_raw,
            api_key="fake-key",
            model="gemini-test",
            http_client=sp_client,
        )
        la_plain = verify_layer_a_for_case(
            session=session,
            run_user_id="u_b2_mock_test",
            request_id="req_sp_plain",
            system_id="B2",
            case=smoke_cases[1],
            result=res_plain,
            check_persistence=False,
        )
        assert la_plain.passed is True
        assert la_plain.factual_explanations == 1
        assert la_plain.canonical_bracket_outfits == 0

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

    def _quality_tier(context_block: str, option_block: str) -> int:
        # 0 = bad, 1 = mediocre, 2 = good
        if "Áo ba lỗ" in option_block or "Dép" in option_block or "Áo măng tô" in option_block:
            return 0
        if "Thắt lưng da cá sấu" in option_block or "Áo Hoodie" in option_block:
            return 0
        if "không mặc màu đen" in context_block and "màu=black" in option_block:
            return 0
        if "trời mưa" in context_block and "Đầm dạ hội" in option_block:
            return 0
        if ("phỏng vấn" in context_block or "đám cưới" in context_block) and "Quần short" in option_block:
            return 0
        if (
            "còn hơi nhẹ" in option_block
            or "hơi giản dị" in option_block
            or "quá cứng nhắc" in option_block
            or "thiếu áo khoác chống mưa" in option_block
        ):
            return 1
        return 2

    captured_prompts: list[str] = []

    def _mock_judge_http(request: httpx.Request) -> httpx.Response:
        nonlocal call_counter
        call_counter += 1
        body = json.loads(request.content.decode("utf-8"))
        user_msg = body["messages"][1]["content"]
        captured_prompts.append(user_msg)
        if "Phương án 1" in user_msg and "Phương án 2" in user_msg:
            head, rest = user_msg.split("--- Phương án 1 ---", 1)
            part1, part2 = rest.split("--- Phương án 2 ---", 1)
            t1 = _quality_tier(head, part1)
            t2 = _quality_tier(head, part2)
            if t1 > t2:
                w = "1"
            elif t2 > t1:
                w = "2"
            else:
                w = "tie"
            ans = {"winner": w, "reason_vi": "Đúng ngữ cảnh và phối hợp lý."}
        else:
            tier = _quality_tier(user_msg, user_msg)
            score = {0: 1.5, 1: 3.1, 2: 4.7}[tier]
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
    assert cal_res["human_vs_judge_spearman"] is not None
    assert cal_res["human_vs_judge_spearman"] >= 0.85

    # Verify runner passes rich profile details (styles, avoid_colors) to Judge, not just opaque profile_id
    from tests.evaluation.benchmark.runner import _format_profile_summary_for_judge

    rich_prof = _format_profile_summary_for_judge("formal_polished", bundle["benchmark"]["profiles"]["formal_polished"])
    assert "tránh_màu=orange,yellow" in rich_prof
    assert "tránh_phong_cách=streetwear" in rich_prof

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

        # Even with Loop 2 Critic enabled (as in M-NoPersonalization), disable_personalization=True must NOT
        # trigger ALL_RECENTLY_WORN rerouting on wear history.
        no_pers_with_loops = execute_stylist_recommendation(
            {
                "request_id": "req-pers-off-loops",
                "user_id": user_id,
                "user_query": "Đi phỏng vấn sáng nay mặc gì?",
                "enable_agent_loops": True,
                "enable_critique_loop": True,
                "disable_personalization": True,
            },
            session=session,
            clock=lambda: fixed_now,
        )
        assert no_pers_with_loops["errors"] == []
        assert no_pers_with_loops["critique_round"] == 0
        assert all(ev.event_type != "CRITIQUE_ALL_RECENTLY_WORN" for ev in no_pers_with_loops["agent_trace"])
        assert "top-white-worn" in {it.item_id for it in no_pers_with_loops["ranked_outfits"][0].items}


def test_load_dotenv_defaults_reads_bench_judge_without_overriding_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_load_dotenv_defaults loads unset BENCH_JUDGE_* vars safely without overriding os.environ or loading Gemini keys."""
    from scripts.evaluate_multi_agent_chatbot import _load_dotenv_defaults

    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# Comment line",
                "GEMINI_API_KEY=should-not-touch",
                'BENCH_JUDGE_PROVIDER="openai_compatible"',
                "BENCH_JUDGE_BASE_URL='https://openrouter.ai/api/v1'",
                "BENCH_JUDGE_MODEL=openai/gpt-4.1",
                "BENCH_JUDGE_API_KEY=sk-or-test-123",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("BENCH_JUDGE_PROVIDER", raising=False)
    monkeypatch.delenv("BENCH_JUDGE_BASE_URL", raising=False)
    monkeypatch.setenv("BENCH_JUDGE_MODEL", "explicit-override-model")
    monkeypatch.delenv("BENCH_JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    loaded = _load_dotenv_defaults(env_file)
    assert set(loaded) == {"BENCH_JUDGE_PROVIDER", "BENCH_JUDGE_BASE_URL", "BENCH_JUDGE_API_KEY"}
    assert os.environ["BENCH_JUDGE_PROVIDER"] == "openai_compatible"
    assert os.environ["BENCH_JUDGE_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert os.environ["BENCH_JUDGE_API_KEY"] == "sk-or-test-123"
    assert os.environ["BENCH_JUDGE_MODEL"] == "explicit-override-model"
    assert "GEMINI_API_KEY" not in os.environ


def test_judge_client_retries_on_429_and_503_and_tracks_usage_tokens() -> None:
    """CrossFamilyJudgeClient retries boundedly on 429/503, sends OpenRouter title/max_tokens, and sums usage tokens."""
    attempts = 0
    captured_headers: list[dict[str, str]] = []
    captured_bodies: list[dict[str, Any]] = []
    sleeps: list[float] = []

    def _mock_transport(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        captured_headers.append(dict(request.headers))
        captured_bodies.append(json.loads(request.content.decode("utf-8")))
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "1"})
        if attempts == 2:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "occasion_formality": 4,
                                    "weather_comfort_function": 4,
                                    "aesthetic_harmony": 5,
                                    "explanation_usefulness": 4,
                                    "rationale_vi": "Gọn gàng đúng bối cảnh.",
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 310, "completion_tokens": 45},
            },
        )

    client = CrossFamilyJudgeClient(
        JudgeConfig(
            provider="openai_compatible",
            base_url="https://openrouter.ai/api/v1",
            api_key="or-key",
            model="openai/gpt-4.1",
            max_retries=3,
            initial_backoff_seconds=1.5,
            max_tokens=220,
        ),
        http_client=httpx.Client(transport=httpx.MockTransport(_mock_transport)),
        sleep_fn=sleeps.append,
    )
    res = client.score_outfit_pointwise(
        query="Đi phỏng vấn sáng nay",
        weather_condition="cool",
        profile_summary="không có",
        items=[{"name": "Áo sơ mi", "category": "top", "sub_category": "shirt"}],
        explanation_vi="Phối [Áo sơ mi] cho buổi phỏng vấn.",
    )
    assert attempts == 3
    assert sleeps == [1.0, 3.0]
    assert captured_headers[0].get("x-title") == "Multi-Agent-Fashion-Stylist-Eval"
    assert captured_bodies[0].get("max_tokens") == 220
    assert client.total_prompt_tokens == 310
    assert client.total_completion_tokens == 45
    assert res["fashion_quality_score"] == round((4 + 4 + 5) / 3.0, 4)


def test_run_benchmark_skips_judge_when_aborted(
    migrated_database: tuple[object, object],
) -> None:
    """When run_benchmark aborts mid-run, Judge must NOT be called to score partial results."""
    _, engine = migrated_database
    judge_http_calls = 0

    def _spy_judge_http(request: httpx.Request) -> httpx.Response:
        nonlocal judge_http_calls
        judge_http_calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    class _FailProvider:
        def extract_context(self, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("Simulated outage")

    spy_judge = CrossFamilyJudgeClient(
        JudgeConfig(provider="openai_compatible", base_url="https://mock.local/v1", api_key="k", model="gpt-4.1"),
        http_client=httpx.Client(transport=httpx.MockTransport(_spy_judge_http)),
    )
    bundle = load_benchmark_bundle()
    report = run_benchmark(
        bundle=bundle,
        split="dev",
        systems=["M-Full"],
        include_stress=False,
        live_llm=True,
        llm_provider_override=_FailProvider(),
        judge=spy_judge,
        calibrate_judge=False,
        engine_override=engine,
    )
    assert report["metadata"]["run_complete"] is False
    assert judge_http_calls == 0
    assert spy_judge.api_calls == 0


def test_b2_single_prompt_aborts_after_three_consecutive_provider_errors(
    migrated_database: tuple[object, object],
) -> None:
    """System B2 must abort cleanly after 3 consecutive PROVIDER_ERROR responses."""
    _, engine = migrated_database
    b2_calls = 0

    def _always_429(request: httpx.Request) -> httpx.Response:
        nonlocal b2_calls
        b2_calls += 1
        return httpx.Response(429)

    bundle = load_benchmark_bundle()
    report = run_benchmark(
        bundle=bundle,
        split="dev",
        systems=["B2"],
        include_stress=False,
        live_llm=True,
        single_prompt_http_client=httpx.Client(transport=httpx.MockTransport(_always_429)),
        single_prompt_api_key="test-key",
        single_prompt_model="gemini-test",
        engine_override=engine,
    )
    assert report["metadata"]["run_complete"] is False
    assert "3 consecutive B2 provider failures" in str(report["metadata"]["aborted_reason"])
    assert b2_calls == 3


def test_gemini_context_provider_rotates_key_pool_on_429() -> None:
    """GeminiContextProvider marks rate-limited keys in GeminiKeyPool and rotates immediately without sleeping."""
    from datetime import date
    from app.services.context_providers import GeminiContextProvider
    from app.services.gemini_key_pool import GeminiKeyPool

    seen_keys: list[str] = []
    sleeps: list[float] = []

    def _mock_gemini(request: httpx.Request) -> httpx.Response:
        k = request.headers.get("x-goog-api-key", "")
        seen_keys.append(k)
        if k == "key-11111111":
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps({"occasion": "cafe"})}]}}]},
        )

    pool = GeminiKeyPool([SecretStr("key-11111111"), SecretStr("key-22222222")], cooldown_seconds=60.0)
    provider = GeminiContextProvider(
        model="gemini-test",
        key_pool=pool,
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(_mock_gemini)),
        sleep_fn=sleeps.append,
    )
    parsed = provider.extract_context(query="Đi cafe chiều", location=None, current_date=date(2026, 11, 22))
    assert parsed["occasion"] == "cafe"
    assert seen_keys == ["key-11111111", "key-22222222"]
    assert pool.is_cooling(SecretStr("key-11111111")) is True
    assert sleeps == []


def test_judge_receives_canonical_expected_weather_not_system_extracted_weather(
    migrated_database: tuple[object, object],
) -> None:
    """Judge must always receive expected_context weather (or 'không nêu rõ'), never system-predicted weather."""
    _, engine = migrated_database
    bundle = load_benchmark_bundle()
    r01 = next(c for c in bundle["benchmark"]["representative_cases"] if c["id"] == "r01")

    case_hot = {
        **r01,
        "id": "r01_hot",
        "expected_context": {"occasion": "interview", "weather_condition": "hot"},
    }
    case_unset = {
        **r01,
        "id": "r01_unset",
        "expected_context": {"occasion": "interview"},
    }

    class _WrongWeatherLLM:
        def extract_context(self, **kwargs: Any) -> dict[str, Any]:
            # Intentionally misclassify weather as 'cold' to prove Judge does not inherit system bias
            return {
                "occasion": "interview",
                "time_of_day": "morning",
                "weather_condition": "cold",
                "target_formality_range": [4, 5],
                "weather_source": "default",
                "needs_clarification": False,
                "confidence": 0.9,
            }

        def generate_outfit_explanations(self, *, outfits: list[dict[str, Any]], **kwargs: Any) -> list[str]:
            return [
                "Phối " + ", ".join(o["items_description"]) + " gọn gàng cho buổi phỏng vấn."
                for o in outfits
            ]

    captured_prompts: list[str] = []

    def _capture_judge(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        user_msg = body["messages"][1]["content"]
        captured_prompts.append(user_msg)
        if "Phương án 1" in user_msg:
            ans = {"winner": "1", "reason_vi": "Đạt yêu cầu."}
        else:
            ans = {
                "occasion_formality": 4,
                "weather_comfort_function": 4,
                "aesthetic_harmony": 4,
                "explanation_usefulness": 4,
                "rationale_vi": "Hợp lý.",
            }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ans)}}]})

    judge = CrossFamilyJudgeClient(
        JudgeConfig(provider="openai_compatible", base_url="https://mock.local/v1", api_key="k", model="gpt-4.1"),
        http_client=httpx.Client(transport=httpx.MockTransport(_capture_judge)),
    )
    run_benchmark(
        bundle={
            "benchmark": {**bundle["benchmark"], "representative_cases": [case_hot, case_unset]},
            "wardrobes": bundle["wardrobes"],
            "calibration": bundle["calibration"],
        },
        systems=("B0", "M-Full"),
        split="all",
        include_stress=False,
        live_llm=True,
        llm_provider_override=_WrongWeatherLLM(),
        judge=judge,
        calibrate_judge=False,
        engine_override=engine,
    )

    assert len(captured_prompts) > 0
    assert any("Thời tiết/bối cảnh ghi nhận: hot" in p for p in captured_prompts)
    assert any("Thời tiết/bối cảnh ghi nhận: không nêu rõ" in p for p in captured_prompts)
    assert all("Thời tiết/bối cảnh ghi nhận: cold" not in p for p in captured_prompts)
    assert all("Thời tiết: cold" not in p for p in captured_prompts)


def test_cached_llm_wrapper_and_b2_cache_deduplicate_live_calls(
    migrated_database: tuple[object, object],
    tmp_path: Path,
) -> None:
    """llm_cache.jsonl deduplicates both M-Full CachedLLMWrapper and B2 single-prompt calls across repeated runs."""
    _, engine = migrated_database
    bundle = load_benchmark_bundle()
    r01 = next(c for c in bundle["benchmark"]["representative_cases"] if c["id"] == "r01")
    mini_bundle = {
        "benchmark": {**bundle["benchmark"], "representative_cases": [r01]},
        "wardrobes": bundle["wardrobes"],
        "calibration": bundle["calibration"],
    }

    m_live_calls = 0
    b2_live_calls = 0

    class _CountingMFullProvider:
        def extract_context(self, **kwargs: Any) -> dict[str, Any]:
            nonlocal m_live_calls
            m_live_calls += 1
            return {
                "occasion": "interview",
                "time_of_day": "morning",
                "weather_condition": "cool",
                "target_formality_range": [4, 5],
                "weather_source": "default",
                "needs_clarification": False,
                "confidence": 0.95,
            }

        def generate_outfit_explanations(self, *, outfits: list[dict[str, Any]], **kwargs: Any) -> list[str]:
            nonlocal m_live_calls
            m_live_calls += 1
            return [
                "Phối " + ", ".join(o["items_description"]) + " đúng chuẩn phỏng vấn sáng."
                for o in outfits
            ]

    def _counting_b2_http(request: httpx.Request) -> httpx.Response:
        nonlocal b2_live_calls
        b2_live_calls += 1
        payload = {
            "status": "ok",
            "outfits": [
                {
                    "rank": 1,
                    "item_ids": ["f_top_01", "f_bot_01", "f_ftw_02"],
                    "explanation_vi": "Phối [Áo sơ mi] trắng, [Quần tây] đen và [Giày búp bê] đen cho phỏng vấn.",
                }
            ],
        }
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
        )

    cache_file = tmp_path / "llm_cache.jsonl"
    report1 = run_benchmark(
        bundle=mini_bundle,
        systems=("B2", "M-Full"),
        split="all",
        include_stress=False,
        live_llm=True,
        llm_provider_override=_CountingMFullProvider(),
        single_prompt_http_client=httpx.Client(transport=httpx.MockTransport(_counting_b2_http)),
        single_prompt_api_key="test-key",
        single_prompt_model="gemini-test",
        llm_cache=JsonlResultCache(cache_file),
        engine_override=engine,
    )
    assert m_live_calls == 2
    assert b2_live_calls == 1
    assert report1["metadata"]["llm_cache_hits"] == 0

    report2 = run_benchmark(
        bundle=mini_bundle,
        systems=("B2", "M-Full"),
        split="all",
        include_stress=False,
        live_llm=True,
        llm_provider_override=_CountingMFullProvider(),
        single_prompt_http_client=httpx.Client(transport=httpx.MockTransport(_counting_b2_http)),
        single_prompt_api_key="test-key",
        single_prompt_model="gemini-test",
        llm_cache=JsonlResultCache(cache_file),
    )
    assert m_live_calls == 2  # Zero new M-Full live calls!
    assert b2_live_calls == 1  # Zero new B2 live calls!
    assert report2["metadata"]["llm_cache_hits"] == 3
    m_b4 = report2["representative_summary"]["M-Full"]["layer_b"]["b4_explanation"]
    assert m_b4["explanation_llm_accepted_rate"] == 1.0


def test_blind_calibration_html_build_and_human_scoring_pipeline(tmp_path: Path) -> None:
    """Blind calibration review HTML leaks no ground-truth labels and scoring computes real human-vs-judge Spearman."""
    from scripts.judge_calibration_human_review import (
        build_blind_calibration_package,
        load_human_ratings,
        score_human_vs_judge,
    )

    pkg = build_blind_calibration_package(out_dir=tmp_path)
    assert pkg["sample_count"] == 20
    html_text = Path(pkg["review_html"]).read_text(encoding="utf-8")
    for forbidden in ("cal_good", "cal_bad", "cal_mid", "mediocre", "human_score"):
        assert forbidden not in html_text

    manifest = json.loads(Path(pkg["manifest_path"]).read_text(encoding="utf-8"))
    bundle = load_benchmark_bundle()
    cal_data = bundle["calibration"]
    samples_by_id = {str(s["id"]): s for s in cal_data["pointwise_samples"]}

    ratings_dir = tmp_path / "ratings"
    ratings_dir.mkdir(parents=True, exist_ok=True)
    for idx, rater in enumerate(("Rater One", "Rater Two", "Rater Three")):
        entries = []
        for blind_id, sample_id in manifest["blind_to_sample"].items():
            label = samples_by_id[sample_id]["label"]
            base_score = 5 if label == "good" else (3 if label == "mediocre" else 1)
            occ = max(1, min(5, base_score - (1 if idx == 1 and label == "good" else 0)))
            wea = base_score
            aes = max(1, min(5, base_score + (1 if idx == 2 and label == "bad" else 0)))
            exp = base_score
            entries.append(
                {
                    "blind_id": blind_id,
                    "occasion_formality": occ,
                    "weather_comfort_function": wea,
                    "aesthetic_harmony": aes,
                    "explanation_usefulness": exp,
                    "fashion_quality_score": round((occ + wea + aes) / 3.0, 4),
                }
            )
        (ratings_dir / f"calibration_ratings_{idx}.json").write_text(
            json.dumps({"rater_name": rater, "ratings": entries}, ensure_ascii=False),
            encoding="utf-8",
        )

    judge_cal_path = tmp_path / "judge_cal.json"
    judge_cal_path.write_text(
        json.dumps(
            {
                "judge_model": "openai/gpt-4.1",
                "judge_provider": "openai_compatible",
                "details": [
                    {
                        "id": str(s["id"]),
                        "label": str(s["label"]),
                        "fashion_quality_score": float(s["human_score"]),
                    }
                    for s in cal_data["pointwise_samples"]
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    out_json = tmp_path / "summary.json"
    out_md = tmp_path / "summary.md"
    scored = score_human_vs_judge(
        ratings_dir=ratings_dir,
        manifest_path=Path(pkg["manifest_path"]),
        judge_calibration_json=judge_cal_path,
        out_json=out_json,
        out_md=out_md,
    )
    assert scored["rater_count"] == 3
    assert scored["inter_rater_spearman_mean"] is not None and scored["inter_rater_spearman_mean"] >= 0.85
    assert scored["human_vs_judge_spearman"] is not None and scored["human_vs_judge_spearman"] >= 0.85
    assert out_json.is_file() and out_md.is_file()

    # Verify run_judge_calibration marks real blind human raters cleanly
    def _mock_judge_cal(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        msg = body["messages"][1]["content"]
        if "Phương án 1" in msg:
            ans = {"winner": "1", "reason_vi": "Tốt hơn."}
        else:
            is_bad = "Áo ba lỗ" in msg or "Dép" in msg or "Áo măng tô" in msg or "da cá sấu" in msg or "Hoodie" in msg or "không mặc màu đen" in msg or "Đầm dạ hội" in msg or "Quần short" in msg
            sc = 1.5 if is_bad else 4.7
            ans = {
                "occasion_formality": sc,
                "weather_comfort_function": sc,
                "aesthetic_harmony": sc,
                "explanation_usefulness": sc,
                "rationale_vi": "OK.",
            }
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(ans)}}]})

    loaded = load_human_ratings(ratings_dir=ratings_dir, manifest_path=Path(pkg["manifest_path"]))
    cal_judge = CrossFamilyJudgeClient(
        JudgeConfig(provider="openai_compatible", base_url="https://mock.local/v1", api_key="k", model="openai/gpt-4.1"),
        http_client=httpx.Client(transport=httpx.MockTransport(_mock_judge_cal)),
    )
    cal_res = run_judge_calibration(cal_judge, cal_data, human_ratings_by_id=loaded["human_ratings_by_id"])
    assert cal_res["human_score_source"] == "blind_human_raters"
    assert cal_res["real_human_rater_count"] == 3
    assert cal_res["human_vs_judge_spearman"] is not None
    assert cal_res["rubric_reference_spearman"] is not None


def test_judge_config_and_client_support_reasoning_effort_for_gpt61_terra(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reasoning Judge models (e.g., openai/gpt-6.1-terra) get reasoning.effort, safe max_tokens, and distinct cache keys."""
    monkeypatch.setenv("BENCH_JUDGE_PROVIDER", "openai_compatible")
    monkeypatch.setenv("BENCH_JUDGE_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.setenv("BENCH_JUDGE_MODEL", "openai/gpt-6.1-terra")
    monkeypatch.setenv("BENCH_JUDGE_API_KEY", "or-key")
    monkeypatch.setenv("BENCH_JUDGE_REASONING_EFFORT", "low")
    monkeypatch.delenv("BENCH_JUDGE_MAX_TOKENS", raising=False)

    cfg_low = JudgeConfig.from_env()
    assert cfg_low.model == "openai/gpt-6.1-terra"
    assert cfg_low.reasoning_effort == "low"
    assert cfg_low.max_tokens == 1024

    monkeypatch.setenv("BENCH_JUDGE_REASONING_EFFORT", "none")
    cfg_none = JudgeConfig.from_env()
    assert cfg_none.reasoning_effort == "none"
    assert cfg_none.max_tokens == 220

    seen_payloads: list[dict[str, Any]] = []

    def _mock_terra(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "occasion_formality": 4,
                                    "weather_comfort_function": 5,
                                    "aesthetic_harmony": 4,
                                    "explanation_usefulness": 4,
                                    "rationale_vi": "Chuẩn mực.",
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 280, "completion_tokens": 90},
            },
        )

    cache = JsonlResultCache(tmp_path / "judge_cache.jsonl")
    transport = httpx.Client(transport=httpx.MockTransport(_mock_terra))

    client_low = CrossFamilyJudgeClient(cfg_low, cache=cache, http_client=transport)
    client_low.score_outfit_pointwise(
        query="Đi cafe chiều",
        weather_condition="cool",
        profile_summary="không có",
        items=[{"name": "Áo polo", "category": "top", "sub_category": "polo"}],
        explanation_vi="Phối [Áo polo] gọn gàng.",
    )
    assert seen_payloads[0]["reasoning"] == {"effort": "low"}
    assert seen_payloads[0]["max_tokens"] == 1024

    # Different reasoning effort must NOT collide on the same cache key
    client_none = CrossFamilyJudgeClient(cfg_none, cache=cache, http_client=transport)
    client_none.score_outfit_pointwise(
        query="Đi cafe chiều",
        weather_condition="cool",
        profile_summary="không có",
        items=[{"name": "Áo polo", "category": "top", "sub_category": "polo"}],
        explanation_vi="Phối [Áo polo] gọn gàng.",
    )
    assert len(seen_payloads) == 2
    assert seen_payloads[1]["reasoning"] == {"effort": "none"}
    assert seen_payloads[1]["max_tokens"] == 220


def test_gemini_context_provider_sends_thinking_level_for_gemini3_and_parses_json_retry_delay() -> None:
    """Gemini 3 models send thinkingLevel='low' and 429 JSON RetryInfo.retryDelay avoids pointless 60s/18h waits."""
    from datetime import date
    from app.services.context_providers import GeminiContextProvider
    from app.services.gemini_key_pool import GeminiKeyPool

    seen_payloads: list[dict[str, Any]] = []
    seen_keys: list[str] = []
    sleeps: list[float] = []

    def _mock_gemini(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers.get("x-goog-api-key", ""))
        seen_payloads.append(json.loads(request.content.decode("utf-8")))
        if seen_keys[-1] == "key-exhausted":
            return httpx.Response(
                429,
                json={
                    "error": {
                        "code": 429,
                        "status": "RESOURCE_EXHAUSTED",
                        "details": [
                            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "65185s"}
                        ],
                    }
                },
            )
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps({"occasion": "interview"})}]}}]},
        )

    pool = GeminiKeyPool([SecretStr("key-exhausted"), SecretStr("key-healthy-2")], cooldown_seconds=60.0)
    provider = GeminiContextProvider(
        model="gemini-3.6-flash",
        key_pool=pool,
        max_retries=2,
        client=httpx.Client(transport=httpx.MockTransport(_mock_gemini)),
        sleep_fn=sleeps.append,
    )
    out = provider.extract_context(query="Phỏng vấn sáng nay", location=None, current_date=date(2026, 11, 22))
    assert out["occasion"] == "interview"
    assert seen_payloads[0]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert seen_keys == ["key-exhausted", "key-healthy-2"]
    assert sleeps == []
    status = pool.get_pool_status()
    exhausted_stat = next(s for s in status["keys"] if s["is_cooling"])
    assert exhausted_stat["cooldown_remaining_seconds"] > 3600.0

    # When ALL keys are daily-exhausted (>120s cooldown), fail fast with 0 sleep instead of sleeping 18 hours
    all_dead_sleeps: list[float] = []
    all_dead_pool = GeminiKeyPool([SecretStr("key-exhausted"), SecretStr("key-exhausted-2")], cooldown_seconds=60.0)

    def _all_429(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "details": [{"retryDelay": "65185s"}],
                }
            },
        )

    dead_provider = GeminiContextProvider(
        model="gemini-3.6-flash",
        key_pool=all_dead_pool,
        max_retries=3,
        client=httpx.Client(transport=httpx.MockTransport(_all_429)),
        sleep_fn=all_dead_sleeps.append,
    )
    with pytest.raises(RuntimeError):
        dead_provider.extract_context(query="Phỏng vấn sáng nay", location=None, current_date=date(2026, 11, 22))
    assert all_dead_sleeps == []


def test_b2_single_prompt_sends_thinking_level_for_gemini3_and_rotates_past_daily_429(
    migrated_database: tuple[object, object],
) -> None:
    """B2 Single-Prompt configures thinkingLevel='low' for Gemini 3 and skips daily-exhausted keys immediately."""
    _, engine = migrated_database
    from datetime import datetime, timezone
    from app.services.gemini_key_pool import GeminiKeyPool

    bundle = load_benchmark_bundle()
    r01 = next(c for c in bundle["benchmark"]["representative_cases"] if c["id"] == "r01")
    seen_keys: list[str] = []
    seen_payloads: list[dict[str, Any]] = []
    sleeps: list[float] = []

    def _mock_b2(request: httpx.Request) -> httpx.Response:
        k = request.headers.get("x-goog-api-key", "")
        seen_keys.append(k)
        seen_payloads.append(json.loads(request.content.decode("utf-8")))
        if k == "key-daily-dead":
            return httpx.Response(
                429,
                json={"error": {"details": [{"retryDelay": "65185s"}]}},
            )
        payload = {
            "status": "ok",
            "outfits": [
                {
                    "rank": 1,
                    "item_ids": ["f_top_01", "f_bot_01", "f_ftw_02"],
                    "explanation_vi": "Phối [Áo sơ mi] trắng, [Quần tây] đen và [Giày búp bê] đen cho phỏng vấn.",
                }
            ],
        }
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
        )

    pool = GeminiKeyPool([SecretStr("key-daily-dead"), SecretStr("key-live-ok")], cooldown_seconds=60.0)
    with Session(engine) as session:
        raw_to_db = seed_case_user(
            session,
            run_user_id="u_b2_gemini3_test",
            wardrobe_specs=bundle["wardrobes"]["wardrobes"]["female_realistic_30"],
            profile_spec=None,
            wear_history=[],
            fixed_now=datetime(2026, 11, 22, 2, 0, tzinfo=timezone.utc),
        )
        db_to_raw = {v: k for k, v in raw_to_db.items()}
        res = run_single_prompt_gemini_baseline(
            session=session,
            run_user_id="u_b2_gemini3_test",
            case=r01,
            db_to_raw=db_to_raw,
            api_key="",
            model="gemini-3.6-flash",
            http_client=httpx.Client(transport=httpx.MockTransport(_mock_b2)),
            key_pool=pool,
            max_retries=2,
            sleep_fn=sleeps.append,
        )
    assert res["status"] == "ok"
    assert seen_payloads[0]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert seen_keys == ["key-daily-dead", "key-live-ok"]
    assert sleeps == []


def test_telemetry_probe_does_not_reset_consecutive_failures_on_cache_hits(tmp_path: Path) -> None:
    """Cached context hits must not mask consecutive live explanation provider failures."""
    from datetime import date
    from tests.evaluation.benchmark.systems import CachedLLMWrapper

    class _ToggleFailProvider:
        explanation_prompt_version = "v2"

        def __init__(self) -> None:
            self.fail_explanations = False

        def extract_context(self, *, query: str, location: str | None, current_date: date) -> dict[str, Any]:
            return {"occasion": "daily_work", "query": query}

        def generate_outfit_explanations(self, **kwargs: Any) -> list[str]:
            if self.fail_explanations:
                raise RuntimeError("Simulated daily 429 quota")
            return ["ok"]

    cache = JsonlResultCache(tmp_path / "llm_cache.jsonl")
    provider = _ToggleFailProvider()
    wrapper = CachedLLMWrapper(provider, cache=cache, provider_name="gemini", model_name="gemini-3.6-flash")
    probe = TelemetryLLMProbe(wrapper, max_consecutive_failures=3)

    # Pre-populate 3 cached extract_context entries
    for idx in range(3):
        wrapper.extract_context(query=f"Đi làm ngày {idx}", location="Hà Nội", current_date=date(2026, 11, 20))

    provider.fail_explanations = True
    for idx in range(2):
        with pytest.raises(RuntimeError):
            probe.generate_outfit_explanations(
                outfits=[{"items_description": ["[Áo sơ mi]"]}],
                occasion="daily_work",
                weather_condition="cool",
                target_formality_range=[3, 4],
                conflict_notes=[],
            )
        assert probe.consecutive_failures == idx + 1
        # Interleaved cache hit must NOT reset consecutive_failures
        probe.extract_context(query=f"Đi làm ngày {idx}", location="Hà Nội", current_date=date(2026, 11, 20))
        assert probe.consecutive_failures == idx + 1

    with pytest.raises(AbortedLiveRunError):
        probe.generate_outfit_explanations(
            outfits=[{"items_description": ["[Áo sơ mi]"]}],
            occasion="daily_work",
            weather_condition="cool",
            target_formality_range=[3, 4],
            conflict_notes=[],
        )


def test_cached_llm_wrapper_versions_explanation_key_without_invalidating_context_key(tmp_path: Path) -> None:
    """Changing explanation_prompt_version invalidates only explanation cache keys, keeping extract_context hits."""
    from datetime import date
    from tests.evaluation.benchmark.systems import CachedLLMWrapper

    class _VersionedProvider:
        def __init__(self, version: str) -> None:
            self.explanation_prompt_version = version

        def extract_context(self, *, query: str, location: str | None, current_date: date) -> dict[str, Any]:
            return {"occasion": "cafe", "version": self.explanation_prompt_version}

        def generate_outfit_explanations(self, **kwargs: Any) -> list[str]:
            return [f"explanation-{self.explanation_prompt_version}"]

    cache_file = tmp_path / "llm_cache.jsonl"
    w_v1 = CachedLLMWrapper(
        _VersionedProvider("v1"),
        cache=JsonlResultCache(cache_file),
        provider_name="gemini",
        model_name="gemini-3.6-flash",
    )
    w_v1.extract_context(query="Đi cafe chiều nay", location=None, current_date=date(2026, 11, 20))
    w_v1.generate_outfit_explanations(
        outfits=[{"items_description": ["[Áo thun]"]}],
        occasion="cafe",
        weather_condition="cool",
        target_formality_range=[1, 3],
        conflict_notes=[],
    )
    assert w_v1.live_calls == 2

    w_v2 = CachedLLMWrapper(
        _VersionedProvider("v2"),
        cache=JsonlResultCache(cache_file),
        provider_name="gemini",
        model_name="gemini-3.6-flash",
    )
    ctx = w_v2.extract_context(query="Đi cafe chiều nay", location=None, current_date=date(2026, 11, 20))
    assert ctx["version"] == "v1"
    assert w_v2.cache_hits == 1
    assert w_v2.live_calls == 0

    exps = w_v2.generate_outfit_explanations(
        outfits=[{"items_description": ["[Áo thun]"]}],
        occasion="cafe",
        weather_condition="cool",
        target_formality_range=[1, 3],
        conflict_notes=[],
    )
    assert exps == ["explanation-v2"]
    assert w_v2.live_calls == 1


def test_gemini_explanation_prompts_prohibit_unbacked_functional_claims() -> None:
    """Single and batch Gemini explanation prompts explicitly prohibit unbacked thermal/functional claims."""
    from app.services.context_providers import EXPLANATION_PROMPT_VERSION, GeminiContextProvider

    sent_prompts: list[str] = []

    def _mock_gemini(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        prompt_text = body["contents"][0]["parts"][0]["text"]
        sent_prompts.append(prompt_text)
        if len(sent_prompts) == 1:
            payload: dict[str, Any] = {"explanation_vi": "Phối [Áo sơ mi trắng] gọn gàng."}
        else:
            payload = {"explanations": ["Phối [Áo sơ mi trắng] gọn gàng."]}
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]},
        )

    provider = GeminiContextProvider(
        api_key=SecretStr("test-key"),
        model="gemini-3.6-flash",
        client=httpx.Client(transport=httpx.MockTransport(_mock_gemini)),
    )
    assert provider.explanation_prompt_version == EXPLANATION_PROMPT_VERSION == "v2"

    provider.generate_outfit_explanation(
        items_description=["[Áo sơ mi trắng]"],
        occasion="daily_work",
        weather_condition="cool",
        target_formality_range=[3, 4],
        composite_score=0.9,
        applied_preferences=[],
        relaxation_notes=[],
        conflict_notes=[],
    )
    provider.generate_outfit_explanations(
        outfits=[{"items_description": ["[Áo sơ mi trắng]"], "composite_score": 0.9}],
        occasion="daily_work",
        weather_condition="cool",
        target_formality_range=[3, 4],
        conflict_notes=[],
    )
    assert len(sent_prompts) == 2
    for prompt in sent_prompts:
        for banned_claim in ("giữ ấm", "chống thấm", "thoáng khí"):
            assert banned_claim in prompt


def test_metrics_allowed_brackets_matches_coordinator_extended_colors() -> None:
    """Layer-A metrics allow extended Vietnamese color labels and raw primary_color brackets."""
    from app.models.entities import WardrobeItem
    from tests.evaluation.benchmark.metrics import _allowed_brackets_for_db_item

    jeans = WardrobeItem(
        id="i1",
        user_id="u1",
        category=WardrobeCategory.BOTTOM,
        sub_category="jeans",
        primary_color="denim_blue",
        pattern="solid",
        material="denim",
        style="casual",
        fit="regular",
        formality_level=2,
        comfort_level=4,
        weather_suitability=["cool"],
    )
    shirt = WardrobeItem(
        id="i2",
        user_id="u1",
        category=WardrobeCategory.TOP,
        sub_category="shirt",
        primary_color="light_blue",
        pattern="solid",
        material="cotton",
        style="smart_casual",
        fit="regular",
        formality_level=4,
        comfort_level=4,
        weather_suitability=["cool"],
    )
    chinos = WardrobeItem(
        id="i3",
        user_id="u1",
        category=WardrobeCategory.BOTTOM,
        sub_category="chinos",
        primary_color="olive",
        pattern="solid",
        material="cotton",
        style="smart_casual",
        fit="regular",
        formality_level=3,
        comfort_level=4,
        weather_suitability=["cool"],
    )

    assert {"[quần jeans xanh denim]", "[quần jeans denim_blue]"} <= _allowed_brackets_for_db_item(jeans)
    assert {"[áo sơ mi xanh nhạt]", "[áo sơ mi light_blue]"} <= _allowed_brackets_for_db_item(shirt)
    assert {"[quần chinos ô-liu]", "[quần chinos olive]"} <= _allowed_brackets_for_db_item(chinos)
