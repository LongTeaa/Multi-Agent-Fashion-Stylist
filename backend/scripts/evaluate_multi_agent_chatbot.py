"""CLI runner for the two-layer Multi-Agent Fashion Stylist Chatbot benchmark."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import get_settings
from tests.evaluation.benchmark.judge import (
    CrossFamilyJudgeClient,
    JsonlResultCache,
    JudgeConfig,
    run_judge_calibration,
)
from tests.evaluation.benchmark.reporting import render_markdown_report, save_report_files
from tests.evaluation.benchmark.runner import (
    DEFAULT_BENCHMARK_PATH,
    DEFAULT_CALIBRATION_PATH,
    estimate_api_budget,
    export_wardrobe_from_db,
    load_benchmark_bundle,
    run_benchmark,
    select_cases_for_split,
)
from tests.evaluation.benchmark.systems import SYSTEM_REGISTRY


def _load_dotenv_defaults(
    env_path: Path | None = None,
    *,
    extra_keys: Sequence[str] = (),
) -> list[str]:
    """Load safe benchmark judge keys from .env into os.environ only when unset (never prints values)."""
    target = env_path or (REPOSITORY_ROOT / ".env")
    if not target.is_file():
        return []
    allowed_exact = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", *extra_keys}
    loaded: list[str] = []
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if not (key.startswith("BENCH_JUDGE_") or key in allowed_exact):
            continue
        val = val.strip()
        if len(val) >= 2 and ((val[0] == val[-1] == '"') or (val[0] == val[-1] == "'")):
            val = val[1:-1]
        if val and key not in os.environ:
            os.environ[key] = val
            loaded.append(key)
    return loaded


def _parse_systems(raw: str) -> list[str]:
    items = [s.strip() for s in raw.split(",") if s.strip()]
    unknown = [s for s in items if s not in SYSTEM_REGISTRY]
    if unknown:
        raise ValueError(
            f"Unknown systems {unknown}. Valid choices: {sorted(SYSTEM_REGISTRY.keys())}"
        )
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_BENCHMARK_PATH)
    parser.add_argument("--wardrobes", type=Path, default=None)
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION_PATH)
    parser.add_argument(
        "--systems",
        type=str,
        default="B0,B1,M-Full,M-NoLoop1,M-NoLoop2,M-NoPersonalization",
        help=f"Comma-separated systems from {sorted(SYSTEM_REGISTRY.keys())}",
    )
    parser.add_argument(
        "--split",
        choices=("dev", "holdout", "smoke", "all"),
        default="all",
    )
    parser.add_argument("--include-stress", action="store_true")
    parser.add_argument("--include-noise", action="store_true")
    parser.add_argument("--live-llm", action="store_true")
    parser.add_argument("--live-weather", action="store_true")
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--calibrate-judge-only", action="store_true")
    parser.add_argument("--no-calibrate", action="store_true")
    parser.add_argument("--judge-provider", choices=("openai_compatible", "anthropic", "gemini"), default=None)
    parser.add_argument("--judge-base-url", type=str, default=None)
    parser.add_argument("--judge-model", type=str, default=None)
    parser.add_argument("--judge-reasoning-effort", choices=("none", "low", "medium", "high"), default=None)
    parser.add_argument("--judge-api-key-env", type=str, default="BENCH_JUDGE_API_KEY")
    parser.add_argument("--human-ratings-dir", type=Path, default=None, help="Directory of exported blind rater JSON files for human_vs_judge_spearman")
    parser.add_argument(
        "--human-manifest",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "private-judge-calibration-review" / "blind_manifest.json",
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--llm-delay-seconds", type=float, default=0.0)
    parser.add_argument("--explanation-timeout", type=float, default=30.0)
    parser.add_argument("--no-llm-cache", action="store_true")
    parser.add_argument("--dry-run-budget", action="store_true")
    parser.add_argument("--export-wardrobe-from-db", type=str, default=None, metavar="USER_ID")
    parser.add_argument("--database-url", type=str, default=None)
    parser.add_argument("--out", type=Path, default=None, help="Output path for --export-wardrobe-from-db")
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--report-md", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _load_dotenv_defaults(extra_keys=(args.judge_api_key_env,))

    # Utility mode: export confirmed items of one DB user into frozen benchmark JSON
    if args.export_wardrobe_from_db:
        if args.out is None:
            parser.error("--out is required when using --export-wardrobe-from-db")
        db_url = args.database_url or get_settings().database_url
        count = export_wardrobe_from_db(
            database_url=db_url,
            user_id=args.export_wardrobe_from_db,
            out_path=args.out,
        )
        print(json.dumps({"exported_items": count, "out": str(args.out)}, ensure_ascii=False))
        return 0

    bundle = load_benchmark_bundle(
        benchmark_path=args.dataset,
        wardrobes_path=args.wardrobes,
        calibration_path=args.calibration,
    )
    systems = _parse_systems(args.systems)
    rep_cases, stress_cases = select_cases_for_split(
        bundle["benchmark"],
        split=args.split,
        include_stress=args.include_stress,
    )

    # Dry-run budget estimation (0 network calls)
    if args.dry_run_budget:
        budget = estimate_api_budget(
            rep_cases=rep_cases,
            stress_cases=stress_cases,
            systems=systems,
            live_llm=args.live_llm,
            judge_enabled=args.judge or args.calibrate_judge_only,
            include_noise=args.include_noise,
            calibrate_judge=not args.no_calibrate,
            calibration_data=bundle.get("calibration"),
        )
        print(json.dumps(budget, ensure_ascii=False, indent=2))
        return 0

    settings = get_settings()
    if args.live_llm and settings.context_provider != "gemini":
        parser.error("--live-llm requires CONTEXT_PROVIDER=gemini in configuration/.env")
    if "B2" in systems and not args.live_llm:
        parser.error("System B2 (Single-Prompt Gemini) requires --live-llm")
    if args.live_weather and settings.weather_provider not in {"openmeteo", "openweather"}:
        parser.error("--live-weather requires a configured WEATHER_PROVIDER")

    judge_client: CrossFamilyJudgeClient | None = None
    if args.judge or args.calibrate_judge_only:
        j_cfg = JudgeConfig.from_env(
            provider=args.judge_provider,
            base_url=args.judge_base_url,
            model=args.judge_model,
            api_key_env=args.judge_api_key_env,
            reasoning_effort=args.judge_reasoning_effort,
        )
        if not j_cfg.api_key and "localhost" not in j_cfg.base_url and "127.0.0.1" not in j_cfg.base_url:
            parser.error(
                f"Judge API key missing. Set {args.judge_api_key_env} (or BENCH_JUDGE_API_KEY) "
                "or point --judge-base-url to a local server such as http://localhost:11434/v1."
            )
        cache_path = (args.cache_dir / "judge_cache.jsonl") if args.cache_dir else None
        judge_client = CrossFamilyJudgeClient(j_cfg, cache=JsonlResultCache(cache_path))

    human_ratings_by_id: dict[str, list[float]] | None = None
    if args.human_ratings_dir is not None:
        if not args.human_manifest.is_file():
            parser.error(f"Human blind manifest not found: {args.human_manifest}")
        from scripts.judge_calibration_human_review import load_human_ratings

        human_ratings_by_id = load_human_ratings(
            ratings_dir=args.human_ratings_dir,
            manifest_path=args.human_manifest,
        )["human_ratings_by_id"]

    if args.calibrate_judge_only:
        assert judge_client is not None
        cal = run_judge_calibration(
            judge_client,
            bundle["calibration"],
            human_ratings_by_id=human_ratings_by_id,
        )
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps(cal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(cal, ensure_ascii=False, indent=2))
        return 0

    llm_cache = (
        JsonlResultCache(args.cache_dir / "llm_cache.jsonl")
        if (args.cache_dir is not None and not args.no_llm_cache)
        else None
    )

    report = run_benchmark(
        bundle=bundle,
        systems=systems,
        split=args.split,
        include_stress=args.include_stress,
        include_noise=args.include_noise,
        live_llm=args.live_llm,
        live_weather=args.live_weather,
        judge=judge_client,
        calibrate_judge=not args.no_calibrate,
        llm_cache=llm_cache,
        llm_delay_seconds=args.llm_delay_seconds,
        explanation_timeout_seconds=args.explanation_timeout,
        human_ratings_by_id=human_ratings_by_id,
    )
    save_report_files(report, report_json=args.report_json, report_md=args.report_md)

    if args.report_md is None:
        print(render_markdown_report(report))
    else:
        print(
            json.dumps(
                {
                    "run_complete": report["metadata"]["run_complete"],
                    "systems": list(report["representative_summary"].keys()),
                    "report_json": str(args.report_json) if args.report_json else None,
                    "report_md": str(args.report_md),
                },
                ensure_ascii=False,
            )
        )
    return 0 if report["metadata"]["run_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
