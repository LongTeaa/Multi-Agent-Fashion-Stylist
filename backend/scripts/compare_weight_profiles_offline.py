"""Offline benchmark with the comfort/active weight profiles before and after PR #21.

Runs the two-layer multi-agent benchmark twice without network access (no live LLM,
weather or judge): once with the current `WEIGHT_PROFILES`, once with the comfort and
active profiles that mirrored the advisor's travel example (personal weight 0). Writes
a JSON summary of the deterministic metrics per system.

Usage (from the repository root):
    python backend/scripts/compare_weight_profiles_offline.py --out <summary.json>
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Never let a local .env turn this offline comparison into provider calls.
os.environ.update(CONTEXT_PROVIDER="fallback", WEATHER_PROVIDER="disabled", ENABLE_LLM_EXPLANATIONS="false")

from app.agents import context_scoring  # noqa: E402
from tests.evaluation.benchmark.runner import (  # noqa: E402
    DEFAULT_BENCHMARK_PATH,
    DEFAULT_CALIBRATION_PATH,
    load_benchmark_bundle,
    run_benchmark,
)

PRE_PR21_PROFILES: dict[str, dict[str, float]] = {
    "comfort": {"weather_comfort": 0.55, "aesthetic": 0.15, "functional": 0.20, "personal": 0.00, "formality": 0.10},
    "active": {"functional": 0.30, "weather_comfort": 0.45, "personal": 0.00, "aesthetic": 0.15, "formality": 0.10},
}
SYSTEMS = ("B0", "B1", "M-Full", "M-NoLoop1", "M-NoLoop2", "M-NoPersonalization")


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for system, row in report["representative_summary"].items():
        b3 = row["layer_b"]["b3_personalization"]
        out[system] = {
            "layer_a": row["layer_a"]["case_pass_ratio"],
            "functional_pass": row["functional"]["pass_ratio"],
            "dev_pass": row["split_breakdown"]["dev"]["pass_ratio"],
            "holdout_pass": row["split_breakdown"]["holdout"]["pass_ratio"],
            "context_micro_accuracy": row["layer_b"]["b1_context"]["micro_field_accuracy"],
            "profile_differentiation": b3["profile_differentiation_ratio"],
            "contrastive_pair_diff": b3["contrastive_pair_diff_ratio"],
            "recent_wear_avoid": b3["recent_wear_avoid_ratio"],
            "top3_core_diversity": b3["top3_core_diversity"],
            "stress_pass": (report.get("stress_summary") or {}).get(system, {}).get("pass_ratio"),
        }
    return out


def _run() -> dict[str, Any]:
    bundle = load_benchmark_bundle(
        benchmark_path=DEFAULT_BENCHMARK_PATH, wardrobes_path=None, calibration_path=DEFAULT_CALIBRATION_PATH
    )
    report = run_benchmark(
        bundle=bundle, systems=SYSTEMS, split="all", include_stress=True, include_noise=False,
        live_llm=False, live_weather=False, judge=None, calibrate_judge=False,
    )
    return {"dataset_version": report["metadata"].get("dataset_version"), "systems": _summary(report)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    current = copy.deepcopy(context_scoring.WEIGHT_PROFILES)
    result: dict[str, Any] = {
        "profiles": {"current": {k: current[k] for k in PRE_PR21_PROFILES}, "pre_pr21": PRE_PR21_PROFILES},
        "current": _run(),
    }
    try:
        context_scoring.WEIGHT_PROFILES.update(copy.deepcopy(PRE_PR21_PROFILES))
        result["pre_pr21"] = _run()
    finally:
        context_scoring.WEIGHT_PROFILES.clear()
        context_scoring.WEIGHT_PROFILES.update(current)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
