"""End-to-end benchmark orchestration, API budget estimator, and wardrobe DB exporter."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Sequence

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import create_database_engine
from app.core.dependencies import get_context_llm_provider, get_weather_provider
from app.models.entities import WardrobeItem
from tests.evaluation.benchmark.judge import (
    CrossFamilyJudgeClient,
    run_judge_calibration,
)
from tests.evaluation.benchmark.metrics import (
    bootstrap_mean_ci_95,
    check_case_functional_assertions,
    compute_context_metrics,
    compute_ndcg_at_3,
    compute_net_loop_impact,
    compute_top3_core_diversity,
    core_item_ids,
    latency_percentiles_ms,
    verify_layer_a_for_case,
    wilson_ci_95,
)
from tests.evaluation.benchmark.systems import (
    SYSTEM_REGISTRY,
    AbortedLiveRunError,
    SystemConfig,
    TelemetryLLMProbe,
    run_multi_agent_system,
    run_random_valid_baseline,
    run_single_prompt_gemini_baseline,
    seed_case_user,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = REPOSITORY_ROOT / "backend"
FIXTURE_DIR = REPOSITORY_ROOT / "data" / "fixtures"
DEFAULT_BENCHMARK_PATH = FIXTURE_DIR / "multi_agent_benchmark_v1.json"
DEFAULT_WARDROBES_PATH = FIXTURE_DIR / "stylist_benchmark_wardrobes_v1.json"
DEFAULT_CALIBRATION_PATH = FIXTURE_DIR / "judge_calibration_v1.json"


def _git_commit_short() -> str:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip() or "unknown"
    except Exception:
        return "unknown"


def load_benchmark_bundle(
    benchmark_path: Path = DEFAULT_BENCHMARK_PATH,
    wardrobes_path: Path | None = None,
    calibration_path: Path = DEFAULT_CALIBRATION_PATH,
) -> dict[str, Any]:
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    resolved_wardrobes = wardrobes_path or (benchmark_path.parent / str(benchmark["wardrobes_fixture"]))
    wardrobes = json.loads(resolved_wardrobes.read_text(encoding="utf-8"))
    calibration = (
        json.loads(calibration_path.read_text(encoding="utf-8"))
        if calibration_path.is_file()
        else None
    )
    return {
        "benchmark": benchmark,
        "wardrobes": wardrobes,
        "calibration": calibration,
    }


def select_cases_for_split(
    benchmark: dict[str, Any],
    *,
    split: str = "all",
    include_stress: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_rep = list(benchmark.get("representative_cases", []))
    if split == "dev":
        rep_cases = [c for c in all_rep if c.get("split") == "dev"]
    elif split == "holdout":
        rep_cases = [c for c in all_rep if c.get("split") == "holdout"]
    elif split == "smoke":
        rep_cases = [c for c in all_rep if c.get("smoke")]
    elif split == "all":
        rep_cases = all_rep
    else:
        raise ValueError(f"Unsupported split: '{split}'")

    stress_cases = list(benchmark.get("stress_cases", [])) if include_stress else []
    return rep_cases, stress_cases


def estimate_api_budget(
    *,
    rep_cases: Sequence[dict[str, Any]],
    stress_cases: Sequence[dict[str, Any]],
    systems: Sequence[str],
    live_llm: bool,
    judge_enabled: bool,
    include_noise: bool,
    calibrate_judge: bool,
    calibration_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimate Gemini chatbot calls and Cross-Family Judge calls before hitting the network."""
    n_rep = len(rep_cases)
    n_stress = len(stress_cases)
    n_total = n_rep + n_stress + (n_rep if include_noise else 0)
    ok_cases = sum(1 for c in [*rep_cases, *stress_cases] if c.get("expected_status") == "ok")
    if include_noise:
        ok_cases += sum(1 for c in rep_cases if c.get("expected_status") == "ok")

    gemini_calls = 0
    for sys_id in systems:
        cfg = SYSTEM_REGISTRY.get(sys_id)
        if cfg is None:
            continue
        if cfg.kind == "single_prompt" and live_llm:
            gemini_calls += n_total
        elif cfg.kind == "multi_agent" and sys_id != "B1" and live_llm:
            # 1 context extraction + ~1 batch explanation (when status=ok)
            gemini_calls += n_total + ok_cases

    judge_calls = 0
    if judge_enabled:
        if calibrate_judge and calibration_data:
            judge_calls += len(calibration_data.get("pointwise_samples", []))
            judge_calls += 2 * len(calibration_data.get("pairwise_samples", []))
        # Pointwise (~2.5 outfits/case, ~45% cross-system dedup overlap) + bidirectional pairs vs M-Full
        unique_outfit_factor = max(1.0, len(systems) * 2.5 * 0.55)
        judge_calls += int(round(ok_cases * unique_outfit_factor))
        if "M-Full" in systems:
            opponents = [s for s in systems if s in {"B0", "B1", "B2", "M-NoLoops"}]
            judge_calls += ok_cases * len(opponents) * 2

    return {
        "systems": list(systems),
        "representative_cases": n_rep,
        "stress_cases": n_stress,
        "noise_cases": n_rep if include_noise else 0,
        "live_llm": live_llm,
        "judge_enabled": judge_enabled,
        "estimated_gemini_calls": gemini_calls,
        "estimated_judge_calls": judge_calls,
        "estimated_total_api_calls": gemini_calls + judge_calls,
    }


def export_wardrobe_from_db(
    *,
    database_url: str,
    user_id: str,
    out_path: Path,
    wardrobe_key: str | None = None,
) -> int:
    """Export confirmed active wardrobe items of one user from a local DB into benchmark JSON."""
    engine = create_database_engine(database_url)
    try:
        with Session(engine) as session:
            rows = session.exec(
                select(WardrobeItem).where(
                    WardrobeItem.user_id == user_id,
                    WardrobeItem.is_active.is_(True),
                    WardrobeItem.is_user_confirmed.is_(True),
                    WardrobeItem.deleted_at.is_(None),
                )
            ).all()
    finally:
        engine.dispose()

    exported = []
    for idx, row in enumerate(rows, start=1):
        exported.append(
            {
                "id": f"exp_{idx:03d}_{row.id[:8]}",
                "source_db_id": row.id,
                "category": row.category.value,
                "sub_category": row.sub_category,
                "primary_color": row.primary_color,
                "secondary_color": row.secondary_color,
                "pattern": row.pattern,
                "material": row.material,
                "style": row.style,
                "fit": row.fit,
                "formality_level": row.formality_level,
                "comfort_level": row.comfort_level,
                "silhouette_level": row.silhouette_level,
                "length": row.length,
                "weather_suitability": list(row.weather_suitability),
                "functional_flags": list(row.functional_flags),
                "free_text_tags": list(row.free_text_tags),
            }
        )

    payload = {
        "dataset_version": "exported-db-wardrobe-v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_user_id": user_id,
        "wardrobes": {wardrobe_key or f"db_{user_id[:8]}": exported},
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(exported)


def _create_isolated_temp_engine(tmp_dir: Path) -> Engine:
    db_path = (tmp_dir / "benchmark.db").as_posix()
    url = f"sqlite:///{db_path}"
    orig = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
        engine = create_database_engine(url)
    finally:
        if orig is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = orig
        get_settings.cache_clear()
    return engine


def _format_profile_summary_for_judge(
    profile_id: str | None,
    profile_spec: dict[str, Any] | None,
) -> str:
    """Format full profile preferences for LLM Judge so it can judge taste and avoid rules."""
    if not profile_id or not profile_spec:
        return "không có"
    parts: list[str] = []
    if profile_spec.get("styles"):
        parts.append(f"phong_cách={','.join(profile_spec['styles'])}")
    if profile_spec.get("color_palettes"):
        parts.append(f"bảng_màu={','.join(profile_spec['color_palettes'])}")
    if profile_spec.get("priorities"):
        parts.append(f"ưu_tiên={','.join(profile_spec['priorities'])}")
    if profile_spec.get("avoid_colors"):
        parts.append(f"tránh_màu={','.join(profile_spec['avoid_colors'])}")
    if profile_spec.get("avoid_styles"):
        parts.append(f"tránh_phong_cách={','.join(profile_spec['avoid_styles'])}")
    if profile_spec.get("fit_preferences"):
        parts.append(f"dáng={','.join(profile_spec['fit_preferences'])}")
    learned = (profile_spec.get("learned_feature_weights") or {}).get("weights") or {}
    if learned:
        learned_str = ", ".join(f"{k}:{v:+.1f}" for k, v in sorted(learned.items()))
        parts.append(f"trọng_số_học=({learned_str})")
    return f"{profile_id} ({'; '.join(parts)})" if parts else str(profile_id)


def _aggregate_system_summary(
    *,
    system_id: str,
    cases: Sequence[dict[str, Any]],
    results_by_case: dict[str, dict[str, Any]],
    layer_a_by_case: dict[str, Any],
    func_fail_by_case: dict[str, list[str]],
    judge_case_ndcg: dict[str, float],
    judge_top1_scores: dict[str, float],
    judge_all_outfit_scores: list[float],
    judge_usefulness_scores: list[float],
) -> dict[str, Any]:
    n_cases = len(results_by_case)
    la_passed = sum(1 for la in layer_a_by_case.values() if la.passed)
    tot_outfits = sum(la.total_outfits for la in layer_a_by_case.values())
    tot_ground = sum(la.valid_grounding_outfits for la in layer_a_by_case.values())
    tot_struct = sum(la.valid_structure_outfits for la in layer_a_by_case.values())
    tot_fact = sum(la.factual_explanations for la in layer_a_by_case.values())
    tot_bracket = sum(la.canonical_bracket_outfits for la in layer_a_by_case.values())
    tot_avoid_chk = sum(la.must_avoid_checked_outfits for la in layer_a_by_case.values())
    tot_avoid_ok = sum(la.must_avoid_compliant_outfits for la in layer_a_by_case.values())
    tot_bounded_ok = sum(1 for la in layer_a_by_case.values() if la.bounded_and_persist_passed)

    func_passed = sum(1 for cid, fails in func_fail_by_case.items() if not fails and layer_a_by_case[cid].passed)

    # B1 Context
    b1_metrics = compute_context_metrics(cases, results_by_case)

    # B2 Judge quality
    ndcg_vals = [judge_case_ndcg[cid] for cid in results_by_case if cid in judge_case_ndcg]
    top1_vals = [judge_top1_scores[cid] for cid in results_by_case if cid in judge_top1_scores]
    hit_at_1 = (
        round(sum(1 for s in top1_vals if s >= 4.0) / len(top1_vals), 4)
        if top1_vals
        else None
    )
    unacc_rate = (
        round(sum(1 for s in judge_all_outfit_scores if s <= 2.0) / len(judge_all_outfit_scores), 4)
        if judge_all_outfit_scores
        else None
    )

    # B3 Personalization & Diversity
    diversities = [
        d
        for res in results_by_case.values()
        if res.get("status") == "ok" and (d := compute_top3_core_diversity(res.get("outfits", []))) is not None
    ]
    prof_groups: dict[str, list[frozenset[str]]] = defaultdict(list)
    contrastive_groups: dict[str, list[frozenset[str]]] = defaultdict(list)
    wear_cases = 0
    wear_avoided = 0
    for case in cases:
        cid = str(case["id"])
        res = results_by_case.get(cid)
        if not res or res.get("status") != "ok" or not res.get("outfits"):
            continue
        top1_core = core_item_ids(res["outfits"][0].get("items", []))
        pg = case.get("profile_sensitivity_group")
        if pg:
            prof_groups[str(pg)].append(top1_core)
        cp = case.get("contrastive_pair_id")
        if cp:
            contrastive_groups[str(cp)].append(top1_core)
        if case.get("wear_history"):
            wear_cases += 1
            hist_set = {str(x) for x in case["wear_history"][0].get("item_ids", [])}
            if not hist_set.issubset({str(it.get("raw_id") or it.get("item_id")) for it in res["outfits"][0].get("items", [])}):
                wear_avoided += 1

    prof_pairs = 0
    prof_diff = 0
    for sigs in prof_groups.values():
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                prof_pairs += 1
                if sigs[i] != sigs[j]:
                    prof_diff += 1

    contrast_pairs = 0
    contrast_diff = 0
    for sigs in contrastive_groups.values():
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                contrast_pairs += 1
                if sigs[i] != sigs[j]:
                    contrast_diff += 1

    # B4 Explanations
    llm_exp_total = 0
    llm_exp_accepted = 0
    for res in results_by_case.values():
        for o in res.get("outfits", []):
            src = o.get("explanation_source")
            if src in {"gemini_batch", "gemini_single", "deterministic_fallback", "single_prompt_llm"}:
                llm_exp_total += 1
                if src in {"gemini_batch", "gemini_single", "single_prompt_llm"}:
                    llm_exp_accepted += 1

    # B5 Cost & Latency + False Loop Rate
    latencies = [float(res.get("latency_ms", 0.0)) for res in results_by_case.values()]
    calls = [int(res.get("llm_calls", 0)) for res in results_by_case.values()]
    tokens = [int(res.get("estimated_tokens", 0)) for res in results_by_case.values()]

    split_breakdown: dict[str, Any] = {}
    for sp in ("dev", "holdout"):
        sp_cases = [str(c["id"]) for c in cases if c.get("split") == sp and str(c["id"]) in results_by_case]
        sp_pass = sum(1 for cid in sp_cases if not func_fail_by_case[cid] and layer_a_by_case[cid].passed)
        sp_ndcg = [judge_case_ndcg[cid] for cid in sp_cases if cid in judge_case_ndcg]
        split_breakdown[sp] = {
            "pass_ratio": f"{sp_pass}/{len(sp_cases)}",
            "pass_rate": round(sp_pass / len(sp_cases), 4) if sp_cases else None,
            "ndcg_at_3": round(sum(sp_ndcg) / len(sp_ndcg), 4) if sp_ndcg else None,
        }

    return {
        "system_id": system_id,
        "cases_evaluated": n_cases,
        "layer_a": {
            "case_pass_ratio": f"{la_passed}/{n_cases}",
            "case_pass_rate": round(la_passed / n_cases, 4) if n_cases else 0.0,
            "valid_item_grounding_rate": round(tot_ground / tot_outfits, 4) if tot_outfits else 1.0,
            "outfit_structure_validity_rate": round(tot_struct / tot_outfits, 4) if tot_outfits else 1.0,
            "must_avoid_compliance_rate": round(tot_avoid_ok / tot_avoid_chk, 4) if tot_avoid_chk else 1.0,
            "explanation_factuality_rate": round(tot_fact / tot_outfits, 4) if tot_outfits else 1.0,
            "canonical_bracket_rate": round(tot_bracket / tot_outfits, 4) if tot_outfits else 1.0,
            "bounded_and_persist_rate": round(tot_bounded_ok / n_cases, 4) if n_cases else 1.0,
        },
        "functional": {
            "pass_ratio": f"{func_passed}/{n_cases}",
            "pass_rate": round(func_passed / n_cases, 4) if n_cases else 0.0,
            "pass_rate_ci95": list(wilson_ci_95(func_passed, n_cases)),
        },
        "layer_b": {
            "b1_context": b1_metrics,
            "b2_quality": {
                "ndcg_at_3": round(sum(ndcg_vals) / len(ndcg_vals), 4) if ndcg_vals else None,
                "ndcg_at_3_ci95": list(bootstrap_mean_ci_95(ndcg_vals)) if ndcg_vals else None,
                "hit_at_1": hit_at_1,
                "unacceptable_rate": unacc_rate,
            },
            "b3_personalization": {
                "top3_core_diversity": round(sum(diversities) / len(diversities), 4) if diversities else None,
                "profile_differentiation_rate": round(prof_diff / prof_pairs, 4) if prof_pairs else None,
                "profile_differentiation_ratio": f"{prof_diff}/{prof_pairs}" if prof_pairs else "N/A",
                "contrastive_pair_diff_rate": round(contrast_diff / contrast_pairs, 4) if contrast_pairs else None,
                "contrastive_pair_diff_ratio": f"{contrast_diff}/{contrast_pairs}" if contrast_pairs else "N/A",
                "recent_wear_avoid_rate": round(wear_avoided / wear_cases, 4) if wear_cases else None,
                "recent_wear_avoid_ratio": f"{wear_avoided}/{wear_cases}" if wear_cases else "N/A",
            },
            "b4_explanation": {
                "explanation_llm_accepted_rate": round(llm_exp_accepted / llm_exp_total, 4) if llm_exp_total else None,
                "explanation_usefulness_mean": round(sum(judge_usefulness_scores) / len(judge_usefulness_scores), 3) if judge_usefulness_scores else None,
            },
            "b5_cost": {
                "latency_ms": latency_percentiles_ms(latencies),
                "avg_llm_calls": round(sum(calls) / n_cases, 3) if n_cases else 0.0,
                "total_llm_calls": sum(calls),
                "total_estimated_tokens": sum(tokens),
            },
        },
        "split_breakdown": split_breakdown,
    }


def run_benchmark(
    *,
    bundle: dict[str, Any],
    systems: Sequence[str] = ("B0", "B1", "M-Full", "M-NoLoop1", "M-NoLoop2", "M-NoPersonalization"),
    split: str = "all",
    include_stress: bool = True,
    include_noise: bool = False,
    live_llm: bool = False,
    live_weather: bool = False,
    judge: CrossFamilyJudgeClient | None = None,
    calibrate_judge: bool = True,
    llm_provider_override: Any = None,
    weather_provider_override: Any = None,
    single_prompt_http_client: Any = None,
    single_prompt_api_key: str | None = None,
    single_prompt_model: str | None = None,
    engine_override: Engine | None = None,
) -> dict[str, Any]:
    """Execute the full two-layer benchmark on isolated temporary storage/DB and return structured report."""
    benchmark = bundle["benchmark"]
    wardrobes_map = bundle["wardrobes"]["wardrobes"]
    profiles_map = benchmark.get("profiles", {})
    fixed_now = datetime.fromisoformat(str(benchmark["fixed_clock_utc"]).replace("Z", "+00:00")).astimezone(timezone.utc)

    rep_cases, stress_cases = select_cases_for_split(benchmark, split=split, include_stress=include_stress)

    settings = get_settings()
    resolved_llm = llm_provider_override if llm_provider_override is not None else (get_context_llm_provider() if live_llm else None)
    resolved_weather = weather_provider_override if weather_provider_override is not None else (get_weather_provider() if live_weather else None)

    chatbot_model_label = None
    if live_llm:
        chatbot_model_label = single_prompt_model or settings.llm_model or "gemini-configured"

    calibration_report = None
    if judge is not None and calibrate_judge and bundle.get("calibration"):
        calibration_report = run_judge_calibration(judge, bundle["calibration"])

    run_complete = True
    aborted_reason: str | None = None

    def _run_suite_on_engine(engine: Engine, suite_cases: Sequence[dict[str, Any]], *, noise_mode: bool, suite_name: str) -> dict[str, Any]:
        nonlocal run_complete, aborted_reason
        suite_results: dict[str, dict[str, dict[str, Any]]] = {}
        suite_layer_a: dict[str, dict[str, Any]] = {}
        suite_func_fails: dict[str, dict[str, list[str]]] = {}
        failures: list[dict[str, Any]] = []

        for sys_id in systems:
            cfg: SystemConfig = SYSTEM_REGISTRY[sys_id]
            sys_res: dict[str, dict[str, Any]] = {}
            sys_la: dict[str, Any] = {}
            sys_fails: dict[str, list[str]] = {}

            llm_probe = (
                TelemetryLLMProbe(resolved_llm)
                if (resolved_llm is not None and cfg.kind == "multi_agent" and sys_id != "B1")
                else None
            )

            for case in suite_cases:
                cid = str(case["id"])
                run_uid = "u_" + hashlib.sha256(f"{suite_name}:{sys_id}:{cid}".encode("utf-8")).hexdigest()[:32]
                req_id = f"req_{suite_name}_{sys_id}_{cid}"
                wardrobe_specs = list(wardrobes_map[str(case["wardrobe_id"])])
                profile_spec = profiles_map.get(str(case["profile_id"])) if case.get("profile_id") else None
                wear_history = list(case.get("wear_history", []))

                with Session(engine) as session:
                    raw_to_db = seed_case_user(
                        session,
                        run_user_id=run_uid,
                        wardrobe_specs=wardrobe_specs,
                        profile_spec=profile_spec,
                        wear_history=wear_history,
                        fixed_now=fixed_now,
                        noise_mode=noise_mode,
                    )
                    db_to_raw = {v: k for k, v in raw_to_db.items()}

                    try:
                        if cfg.kind == "random":
                            result = run_random_valid_baseline(
                                session=session,
                                run_user_id=run_uid,
                                case=case,
                                db_to_raw=db_to_raw,
                            )
                        elif cfg.kind == "single_prompt":
                            sp_key = single_prompt_api_key or (
                                settings.get_primary_gemini_api_key().get_secret_value()
                                if settings.get_primary_gemini_api_key()
                                else ""
                            )
                            sp_model = single_prompt_model or settings.llm_model or "gemini-2.5-flash"
                            result = run_single_prompt_gemini_baseline(
                                session=session,
                                run_user_id=run_uid,
                                case=case,
                                db_to_raw=db_to_raw,
                                api_key=sp_key,
                                model=sp_model,
                                http_client=single_prompt_http_client,
                            )
                        else:
                            result = run_multi_agent_system(
                                session=session,
                                config=cfg,
                                run_user_id=run_uid,
                                request_id=req_id,
                                case=case,
                                db_to_raw=db_to_raw,
                                fixed_now=fixed_now,
                                llm_probe=llm_probe,
                                weather_provider=resolved_weather,
                            )
                    except AbortedLiveRunError as exc:
                        run_complete = False
                        aborted_reason = str(exc)
                        break

                    la = verify_layer_a_for_case(
                        session=session,
                        run_user_id=run_uid,
                        request_id=req_id,
                        system_id=sys_id,
                        case=case,
                        result=result,
                        check_persistence=(cfg.kind == "multi_agent"),
                    )
                    func_fails = check_case_functional_assertions(case, result)

                    sys_res[cid] = result
                    sys_la[cid] = la
                    sys_fails[cid] = func_fails

                    if not la.passed or func_fails:
                        failures.append(
                            {
                                "suite": suite_name,
                                "system_id": sys_id,
                                "case_id": cid,
                                "query": case["query"],
                                "status": result.get("status"),
                                "error_code": result.get("error_code"),
                                "context_used": result.get("context_used"),
                                "layer_a_violations": la.violations,
                                "functional_failures": func_fails,
                                "agent_trace": result.get("agent_trace", []),
                            }
                        )

            suite_results[sys_id] = sys_res
            suite_layer_a[sys_id] = sys_la
            suite_func_fails[sys_id] = sys_fails
            if not run_complete:
                break

        return {
            "results": suite_results,
            "layer_a": suite_layer_a,
            "func_fails": suite_func_fails,
            "failures": failures,
        }

    with TemporaryDirectory(prefix="multi-agent-bench-") as tmp_dir_str:
        tmp_engine = None
        if engine_override is None:
            tmp_engine = _create_isolated_temp_engine(Path(tmp_dir_str))
            active_engine = tmp_engine
        else:
            active_engine = engine_override

        try:
            rep_exec = _run_suite_on_engine(active_engine, rep_cases, noise_mode=False, suite_name="rep")
            noise_exec = (
                _run_suite_on_engine(active_engine, rep_cases, noise_mode=True, suite_name="noise")
                if include_noise and run_complete
                else None
            )
            stress_exec = (
                _run_suite_on_engine(active_engine, stress_cases, noise_mode=False, suite_name="stress")
                if stress_cases and run_complete
                else None
            )
        finally:
            if tmp_engine is not None:
                tmp_engine.dispose()

    # Optional Cross-Family Judge scoring (Pointwise + Pairwise Bidirectional)
    judge_case_scores: dict[str, dict[str, list[float]]] = defaultdict(dict)  # sys -> cid -> [f_scores]
    judge_top1_scores: dict[str, dict[str, float]] = defaultdict(dict)
    judge_all_scores: dict[str, list[float]] = defaultdict(list)
    judge_useful_scores: dict[str, list[float]] = defaultdict(list)
    judge_case_ndcg: dict[str, dict[str, float]] = defaultdict(dict)
    pairwise_comparisons: dict[str, Any] = {}

    if judge is not None and rep_exec["results"]:
        case_lookup = {str(c["id"]): c for c in rep_cases}
        pool_scores_by_case: dict[str, list[float]] = defaultdict(list)

        for sys_id, sys_res in rep_exec["results"].items():
            for cid, res in sys_res.items():
                if res.get("status") != "ok" or not res.get("outfits"):
                    continue
                case = case_lookup[cid]
                pid = case.get("profile_id")
                prof_summary = _format_profile_summary_for_judge(
                    str(pid) if pid else None,
                    profiles_map.get(str(pid)) if pid else None,
                )
                weather_cond = str((res.get("context") or {}).get("weather_condition") or (case.get("expected_context") or {}).get("weather_condition") or "cool")
                outfit_scores: list[float] = []
                for outfit in res["outfits"]:
                    scored = judge.score_outfit_pointwise(
                        query=str(case["query"]),
                        weather_condition=weather_cond,
                        profile_summary=prof_summary,
                        items=list(outfit.get("items", [])),
                        explanation_vi=str(outfit.get("explanation_vi", "")),
                    )
                    f_score = float(scored["fashion_quality_score"])
                    u_score = float(scored["explanation_usefulness"])
                    outfit["judge_score"] = scored
                    outfit_scores.append(f_score)
                    pool_scores_by_case[cid].append(f_score)
                    judge_all_scores[sys_id].append(f_score)
                    judge_useful_scores[sys_id].append(u_score)
                judge_case_scores[sys_id][cid] = outfit_scores
                judge_top1_scores[sys_id][cid] = outfit_scores[0]

        for sys_id, c_scores in judge_case_scores.items():
            for cid, o_scores in c_scores.items():
                judge_case_ndcg[sys_id][cid] = compute_ndcg_at_3(o_scores, ideal_pool=pool_scores_by_case[cid])

        if "M-Full" in rep_exec["results"]:
            m_res = rep_exec["results"]["M-Full"]
            for opp_id in [s for s in systems if s in {"B0", "B1", "B2", "M-NoLoops"}]:
                opp_res = rep_exec["results"].get(opp_id, {})
                wins = ties = losses = consistent = total_pairs = 0
                for cid, mr in m_res.items():
                    orr = opp_res.get(cid)
                    if not orr or mr.get("status") != "ok" or orr.get("status") != "ok":
                        continue
                    if not mr.get("outfits") or not orr.get("outfits"):
                        continue
                    case = case_lookup[cid]
                    pid = case.get("profile_id")
                    prof_summary = _format_profile_summary_for_judge(
                        str(pid) if pid else None,
                        profiles_map.get(str(pid)) if pid else None,
                    )
                    comp = judge.compare_pair_bidirectional(
                        query=str(case["query"]),
                        weather_condition=str((mr.get("context") or {}).get("weather_condition") or ""),
                        profile_summary=prof_summary,
                        a_items=list(mr["outfits"][0]["items"]),
                        a_exp=str(mr["outfits"][0]["explanation_vi"]),
                        b_items=list(orr["outfits"][0]["items"]),
                        b_exp=str(orr["outfits"][0]["explanation_vi"]),
                    )
                    total_pairs += 1
                    if comp["consistent"]:
                        consistent += 1
                    if comp["winner"] == "A":
                        wins += 1
                    elif comp["winner"] == "B":
                        losses += 1
                    else:
                        ties += 1
                if total_pairs:
                    pairwise_comparisons[opp_id] = {
                        "total_pairs": total_pairs,
                        "wins": wins,
                        "ties": ties,
                        "losses": losses,
                        "win_rate": round(wins / total_pairs, 4),
                        "position_consistency_rate": round(consistent / total_pairs, 4),
                    }

    # Summarize representative systems
    rep_summary: dict[str, Any] = {}
    case_pass_flags: dict[str, dict[str, bool]] = {}
    for sys_id in rep_exec["results"]:
        case_pass_flags[sys_id] = {
            cid: (not rep_exec["func_fails"][sys_id][cid] and rep_exec["layer_a"][sys_id][cid].passed)
            for cid in rep_exec["results"][sys_id]
        }
        rep_summary[sys_id] = _aggregate_system_summary(
            system_id=sys_id,
            cases=rep_cases,
            results_by_case=rep_exec["results"][sys_id],
            layer_a_by_case=rep_exec["layer_a"][sys_id],
            func_fail_by_case=rep_exec["func_fails"][sys_id],
            judge_case_ndcg=judge_case_ndcg.get(sys_id, {}),
            judge_top1_scores=judge_top1_scores.get(sys_id, {}),
            judge_all_outfit_scores=judge_all_scores.get(sys_id, []),
            judge_usefulness_scores=judge_useful_scores.get(sys_id, []),
        )

    # B5 Ablation Net Loop Impact
    ablation_impact: dict[str, Any] = {}
    if "M-Full" in rep_exec["results"]:
        for ab_id, label in (
            ("M-NoLoop1", "Loop 1 (M-Full vs M-NoLoop1)"),
            ("M-NoLoop2", "Loop 2 (M-Full vs M-NoLoop2)"),
            ("M-NoLoops", "Both Loops (M-Full vs M-NoLoops)"),
            ("B1", "Cyclic+LLM vs Rule-DAG (M-Full vs B1)"),
            ("M-NoPersonalization", "Personalization (M-Full vs M-NoPersonalization)"),
        ):
            if ab_id not in rep_exec["results"]:
                continue
            ablation_impact[label] = compute_net_loop_impact(
                rep_cases,
                rep_exec["results"]["M-Full"],
                rep_exec["results"][ab_id],
                full_case_pass=case_pass_flags["M-Full"],
                ablated_case_pass=case_pass_flags[ab_id],
                full_ndcg=judge_case_ndcg.get("M-Full") if judge else None,
                ablated_ndcg=judge_case_ndcg.get(ab_id) if judge else None,
            )

    # Noise Robustness comparison (Pass delta + Top-1 Ranking Stability / Core Jaccard)
    noise_robustness: dict[str, Any] = {}
    if noise_exec is not None:
        for sys_id in noise_exec["results"]:
            clean_s = rep_summary.get(sys_id, {})
            n_cases = len(noise_exec["results"][sys_id])
            n_la = sum(1 for la in noise_exec["layer_a"][sys_id].values() if la.passed)
            n_fn = sum(
                1
                for cid in noise_exec["results"][sys_id]
                if not noise_exec["func_fails"][sys_id][cid] and noise_exec["layer_a"][sys_id][cid].passed
            )
            clean_res_map = rep_exec["results"].get(sys_id, {})
            noisy_res_map = noise_exec["results"][sys_id]
            compared_ok = 0
            exact_same = 0
            jaccards: list[float] = []
            for cid, nres in noisy_res_map.items():
                cres = clean_res_map.get(cid)
                if not cres or cres.get("status") != "ok" or nres.get("status") != "ok":
                    continue
                if not cres.get("outfits") or not nres.get("outfits"):
                    continue
                c_core = core_item_ids(cres["outfits"][0].get("items", []))
                n_core = core_item_ids(nres["outfits"][0].get("items", []))
                compared_ok += 1
                if c_core == n_core:
                    exact_same += 1
                union = c_core | n_core
                jaccards.append((len(c_core & n_core) / len(union)) if union else 1.0)
            stability_rate = round(exact_same / compared_ok, 4) if compared_ok else None
            flip_rate = round(1.0 - stability_rate, 4) if stability_rate is not None else None
            mean_jaccard = round(sum(jaccards) / len(jaccards), 4) if jaccards else None

            clean_la_r = (clean_s.get("layer_a") or {}).get("case_pass_rate", 0.0)
            clean_fn_r = (clean_s.get("functional") or {}).get("pass_rate", 0.0)
            noisy_fn_r = round(n_fn / n_cases, 4) if n_cases else 0.0
            noise_robustness[sys_id] = {
                "clean_layer_a_rate": clean_la_r,
                "noisy_layer_a_rate": round(n_la / n_cases, 4) if n_cases else 0.0,
                "clean_func_rate": clean_fn_r,
                "noisy_func_rate": noisy_fn_r,
                "delta_func_rate": round(noisy_fn_r - clean_fn_r, 4),
                "top1_compared_cases": compared_ok,
                "top1_exact_stability_rate": stability_rate,
                "top1_flip_rate": flip_rate,
                "top1_mean_core_jaccard": mean_jaccard,
            }

    # Stress summary (strictly separated)
    stress_summary: dict[str, Any] = {}
    if stress_exec is not None:
        for sys_id, sys_res in stress_exec["results"].items():
            n_st = len(sys_res)
            la_st = sum(1 for la in stress_exec["layer_a"][sys_id].values() if la.passed)
            fn_st = sum(
                1
                for cid in sys_res
                if not stress_exec["func_fails"][sys_id][cid] and stress_exec["layer_a"][sys_id][cid].passed
            )
            loop1_cnt = sum(1 for r in sys_res.values() if int(r.get("relaxation_round", 0)) > 0)
            loop2_cnt = sum(1 for r in sys_res.values() if int(r.get("critique_round", 0)) > 0)
            stress_summary[sys_id] = {
                "layer_a_ratio": f"{la_st}/{n_st}",
                "pass_ratio": f"{fn_st}/{n_st}",
                "pass_rate": round(fn_st / n_st, 4) if n_st else 0.0,
                "loop1_count": loop1_cnt,
                "loop2_count": loop2_cnt,
            }

    all_failures = list(rep_exec["failures"])
    if stress_exec is not None:
        all_failures.extend(stress_exec["failures"])

    n_dev = sum(1 for c in rep_cases if c.get("split") == "dev")
    n_hold = sum(1 for c in rep_cases if c.get("split") == "holdout")
    threats = [
        "Tủ đồ chuẩn (30 món nữ, 27 món nam) mô phỏng cấu trúc và tỷ lệ nhãn 'unknown' thực tế; khuyến nghị xuất thêm dữ liệu từ DB người dùng thực qua --export-wardrobe-from-db sau khi hoàn tất nạp 58 ảnh demo.",
        "Điểm chất lượng thời trang (Lớp B B2/B4) được chấm bởi LLM-as-a-Judge thay cho hội đồng chuyên gia dệt may chấm tay 100%; cần luôn kiểm tra cùng kết quả Calibration, Human-vs-Judge Spearman và Position Consistency.",
        f"Quy mô mẫu {len(rep_cases)} kịch bản ({n_dev} dev / {n_hold} holdout) phù hợp kiểm chứng đồ án nhưng độ rộng khoảng tin cậy 95% (Wilson/Bootstrap CI) và mẫu số từng nhóm con vẫn cần được trình bày song song với tỷ lệ phần trăm.",
    ]
    if judge is not None and judge.same_family_bias:
        threats.insert(
            0,
            "CẢNH BÁO: Giám khảo hiện đang dùng model cùng họ Gemini với chatbot -> có rủi ro tự ưu ái (Self-Enhancement Bias).",
        )

    return {
        "metadata": {
            "dataset_version": benchmark.get("dataset_version"),
            "wardrobes_version": bundle["wardrobes"].get("dataset_version"),
            "rule_version": benchmark.get("rule_version"),
            "split": split,
            "representative_case_count": len(rep_cases),
            "stress_case_count": len(stress_cases),
            "execution_mode": "live_llm" if live_llm else "offline_deterministic",
            "live_llm": live_llm,
            "live_weather": live_weather,
            "judge_enabled": judge is not None,
            "chatbot_model": chatbot_model_label,
            "judge_model": judge.config.model if judge is not None else None,
            "judge_provider": judge.config.provider if judge is not None else None,
            "same_family_judge_bias": judge.same_family_bias if judge is not None else False,
            "judge_api_calls": judge.api_calls if judge is not None else 0,
            "judge_cache_hits": judge.cache_hits if judge is not None else 0,
            "git_commit": _git_commit_short(),
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "run_complete": run_complete,
            "aborted_reason": aborted_reason,
        },
        "judge_calibration": calibration_report,
        "representative_summary": rep_summary,
        "pairwise_comparisons": pairwise_comparisons,
        "ablation_impact": ablation_impact,
        "noise_robustness": noise_robustness,
        "stress_summary": stress_summary,
        "failure_breakdown": all_failures,
        "threats_to_validity": threats,
    }
