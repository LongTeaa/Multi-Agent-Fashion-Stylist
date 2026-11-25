"""Offline simulation: do 1-5 star ratings move recommendations toward a user's taste?

Simulated users with a hidden taste (colour and style preferences) chat with the real
API (`POST /stylist/chat`) and rate the top-ranked outfit (`PUT /outfits/{id}/rating`)
with the stars their taste implies. A paired control user receives the same requests
but never rates. At checkpoints the evaluation queries are re-run for both users and
the recommendations are scored against the hidden taste and against the benchmark's
context assertions (formality, functional flags, required items), so a stronger taste
signal cannot hide a loss of context fit.

Everything runs in an isolated temporary database with deterministic providers: no
network, no LLM, no weather API. The application's learning rule (per-feature EMA,
alpha 0.30, active from five ratings) is used unchanged.

`--learned-share` runs a sensitivity analysis without changing the application. The
preference score is `0.35 style + 0.25 palette + 0.20 priority + 0.20 learned + fit`.
The simulated users have no onboarding choices, so style, palette and priority are all
the neutral 0.5; giving the learned term a share `s` instead of 0.20 is then exactly
`0.5 + s * (affinity - 0.5)`, which the script obtains by scaling the learned affinity's
deviation from 0.5 by `s / 0.20` for the duration of the run.

Usage (from the repository root):
    python backend/scripts/simulate_rating_personalization.py --out <summary.json>
    python backend/scripts/simulate_rating_personalization.py --learned-share 0.2 0.4 0.6 --out <summary.json>
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any
from uuid import NAMESPACE_URL, uuid5

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

MAJOR_SLOTS = {"top", "bottom", "dress", "outerwear", "footwear"}
CHECKPOINTS = (0, 5, 10, 15, 20)
CURRENT_LEARNED_SHARE = 0.20
# Benchmark assertions that can be checked from a chat response; loop-round and
# explanation assertions need graph internals and are left to the benchmark itself.
CHECKABLE_ASSERTIONS = {
    "min_outfits", "max_outfits", "top1_must_include_items", "top1_must_exclude_items",
    "top1_must_include_categories", "top1_must_not_exact_item_set", "top1_min_avg_formality",
    "top1_max_avg_formality", "top1_requires_any_functional_flags", "top1_requires_outerwear",
}

# Hidden tastes. Each item scores the mean of its colour and style preference in [-1, 1];
# an outfit scores the mean over its major items; stars = clamp(round(3 + 2 * score), 1, 5).
PERSONAS: dict[str, dict[str, dict[str, float]]] = {
    "dark_minimal": {
        "color": {"black": 1, "navy": 1, "grey": 1, "charcoal": 1,
                  "white": -1, "cream": -1, "beige": -1, "khaki": -1, "pink": -1, "yellow": -1, "light_blue": -1},
        "style": {"minimalist": 1, "formal": 0.5, "streetwear": -1, "vintage": -1},
    },
    "light_casual": {
        "color": {"white": 1, "cream": 1, "beige": 1, "khaki": 1, "light_blue": 1, "pink": 1, "yellow": 1,
                  "black": -1, "navy": -1, "grey": -1, "charcoal": -1},
        "style": {"casual": 1, "streetwear": 1, "formal": -1},
    },
    "earthy": {
        "color": {"brown": 1, "beige": 1, "olive": 1, "khaki": 1, "camel": 1, "burgundy": 1,
                  "black": -1, "white": -1, "grey": -1},
        "style": {"vintage": 1, "casual": 0.5, "smart_casual": 0.5, "streetwear": -1},
    },
}
WARDROBES = ("female_realistic_30", "male_realistic_27")


def _configure_offline_environment(db_path: Path) -> None:
    os.environ.update(
        DATABASE_URL=f"sqlite:///{db_path.as_posix()}",
        CONTEXT_PROVIDER="fallback",
        WEATHER_PROVIDER="disabled",
        ENABLE_LLM_EXPLANATIONS="false",
        IMAGE_PROVIDER="disabled",
        TRYON_PROVIDER="disabled",
        VISION_PROVIDER="fake",
        DETECTOR_BACKEND="fake",
        DETECTOR_FALLBACK_BACKEND="none",
        GEMINI_API_KEY="",
        GEMINI_API_KEYS="",
        OBJECT_STORAGE_BACKEND="local",
    )


def stars_for(persona: dict[str, dict[str, float]], items: list[dict[str, Any]]) -> int:
    scores = []
    for item in items:
        parts = [persona["color"].get(str(item.get("primary_color", "")).lower(), 0.0),
                 persona["style"].get(str(item.get("style", "")).lower(), 0.0)]
        scores.append(sum(parts) / len(parts))
    score = sum(scores) / len(scores) if scores else 0.0
    return max(1, min(5, round(3 + 2 * score)))


def _ndcg_at_3(stars: list[int]) -> float:
    gains = [s - 1 for s in stars[:3]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sum(g / math.log2(i + 2) for i, g in enumerate(sorted(gains, reverse=True)))
    return dcg / ideal if ideal else 1.0


def _metrics(per_query: list[tuple[list[int], bool]]) -> dict[str, float]:
    answered = [(s, ok) for s, ok in per_query if s]
    n = len(answered)
    if not n:
        return {"queries": 0}
    top1 = [s[0] for s, _ in answered]
    rr = [next((1 / (i + 1) for i, v in enumerate(s[:3]) if v >= 4), 0.0) for s, _ in answered]
    return {
        "queries": n,
        "top1_mean_stars": round(sum(top1) / n, 4),
        "hit_at_1": round(sum(v >= 4 for v in top1) / n, 4),
        "mrr_at_3": round(sum(rr) / n, 4),
        "ndcg_at_3": round(sum(_ndcg_at_3(s) for s, _ in answered) / n, 4),
        "top3_liked_share": round(sum(sum(v >= 4 for v in s[:3]) / len(s[:3]) for s, _ in answered) / n, 4),
        "context_assertion_pass": round(sum(ok for _, ok in answered) / n, 4),
    }


def _sign_test(diffs: list[float]) -> dict[str, Any]:
    pos, neg = sum(d > 0 for d in diffs), sum(d < 0 for d in diffs)
    n, k = pos + neg, min(pos, neg)
    p = min(1.0, 2 * sum(math.comb(n, j) for j in range(k + 1)) / 2**n) if n else 1.0
    return {"better": pos, "worse": neg, "equal": len(diffs) - n, "p_two_sided": round(p, 4)}


def _scaled_affinity(original: Callable[..., float], share: float) -> Callable[..., float]:
    factor = share / CURRENT_LEARNED_SHARE

    def scaled(*args: Any, **kwargs: Any) -> float:
        return 0.5 + factor * (original(*args, **kwargs) - 0.5)

    return scaled


def _run_share(share: float, client: Any, now: datetime, wardrobes: dict[str, Any], bench: dict[str, Any]) -> dict[str, Any]:
    from sqlmodel import Session

    from app.agents import personalization_agent
    from app.core.database import get_engine
    from tests.evaluation.benchmark.metrics import check_case_functional_assertions
    from tests.evaluation.benchmark.systems import seed_case_user

    original = personalization_agent.calculate_learned_affinity
    personalization_agent.calculate_learned_affinity = _scaled_affinity(original, share)  # type: ignore[assignment]
    try:
        results: dict[str, Any] = {}
        paired_top1: list[float] = []
        paired_guard: list[float] = []
        for wardrobe_id in WARDROBES:
            specs = wardrobes[wardrobe_id]
            cases = sorted(
                (c for c in bench["representative_cases"]
                 if c.get("wardrobe_id") == wardrobe_id and c.get("expected_status") == "ok"),
                key=lambda c: c["id"],
            )
            train, evaluation = cases[0::2], cases[1::2]
            for persona_id, persona in PERSONAS.items():
                users: dict[str, tuple[str, dict[str, dict[str, Any]]]] = {}
                with Session(get_engine()) as session:
                    for condition in ("rated", "control"):
                        user_id = str(uuid5(NAMESPACE_URL, f"rating-sim/{share}/{wardrobe_id}/{persona_id}/{condition}"))
                        raw_to_db = seed_case_user(
                            session, run_user_id=user_id, wardrobe_specs=specs,
                            profile_spec={"styles": []}, wear_history=[], fixed_now=now,
                        )
                        by_db = {db: next(s for s in specs if s["id"] == raw) for raw, db in raw_to_db.items()}
                        users[condition] = (user_id, by_db)
                    session.commit()

                def chat(condition: str, case: dict[str, Any]) -> tuple[str | None, list[int], bool]:
                    user_id, by_db = users[condition]
                    res = client.post("/api/v1/stylist/chat", headers={"X-User-Id": user_id},
                                      json={"query": case["query"], "location": case.get("location")})
                    res.raise_for_status()
                    data = res.json()["data"]
                    recs = data["recommendations"]
                    stars = [stars_for(persona, [by_db[i["item_id"]] for i in r["items"]
                                                 if i.get("slot") in MAJOR_SLOTS and i["item_id"] in by_db])
                             for r in recs]
                    outfits = [{
                        "explanation_vi": r.get("explanation_vi", ""),
                        "items": [{**by_db.get(i["item_id"], {}), "raw_id": by_db.get(i["item_id"], {}).get("id"),
                                   "slot": i.get("slot")} for i in r["items"]],
                    } for r in recs]
                    checkable = {**case, "assertions": {k: v for k, v in (case.get("assertions") or {}).items()
                                                        if k in CHECKABLE_ASSERTIONS}}
                    status = "clarification" if data.get("needs_clarification") else "ok"
                    failures = check_case_functional_assertions(checkable, {"status": status, "outfits": outfits})
                    return (recs[0]["outfit_id"] if recs else None), stars, not failures

                curve: dict[str, dict[str, Any]] = {"rated": {}, "control": {}}
                final_eval: dict[str, list[tuple[list[int], bool]]] = {}
                ratings_done, train_index = 0, 0
                for checkpoint in CHECKPOINTS:
                    while ratings_done < checkpoint:
                        case = train[train_index % len(train)]
                        train_index += 1
                        outfit_id, stars, _ = chat("rated", case)
                        chat("control", case)
                        if outfit_id is None:
                            continue
                        res = client.put(f"/api/v1/outfits/{outfit_id}/rating",
                                         headers={"X-User-Id": users["rated"][0]},
                                         json={"stars": stars[0], "source": "manual"})
                        res.raise_for_status()
                        ratings_done += 1
                    for condition in ("rated", "control"):
                        per_query = [chat(condition, case)[1:] for case in evaluation]
                        curve[condition][str(checkpoint)] = _metrics(per_query)
                        final_eval[condition] = per_query
                for (r_stars, r_ok), (c_stars, c_ok) in zip(final_eval["rated"], final_eval["control"]):
                    if r_stars and c_stars:
                        paired_top1.append(r_stars[0] - c_stars[0])
                        paired_guard.append(int(r_ok) - int(c_ok))
                profile = client.get("/api/v1/user/profile", headers={"X-User-Id": users["rated"][0]})
                profile.raise_for_status()
                profile_data = profile.json()["data"]
                results[f"{wardrobe_id}/{persona_id}"] = {
                    "train_queries": len(train), "eval_queries": len(evaluation), "curve": curve,
                    "ratings_count": profile_data.get("ratings_count"),
                    "learned_weights": (profile_data.get("feature_weights") or {}).get("weights"),
                }
    finally:
        personalization_agent.calculate_learned_affinity = original  # type: ignore[assignment]

    def _pooled(condition: str, checkpoint: str) -> dict[str, float]:
        rows = [r["curve"][condition][checkpoint] for r in results.values()]
        keys = [k for k in rows[0] if k != "queries"]
        total = sum(r["queries"] for r in rows)
        return {"queries": total, **{k: round(sum(r[k] * r["queries"] for r in rows) / total, 4) for k in keys}}

    return {
        "learned_share": share,
        "max_composite_shift": {p: round(w * share * 0.5, 4) for p, w in
                                (("formal", 0.10), ("comfort", 0.15), ("active", 0.10), ("balanced", 0.20))},
        "pooled": {c: {str(k): _pooled(c, str(k)) for k in CHECKPOINTS} for c in ("rated", "control")},
        "final_paired_top1_rated_minus_control": _sign_test(paired_top1),
        "final_paired_context_assertion_rated_minus_control": _sign_test(paired_guard),
        "per_user": results,
    }


def run(out: Path, shares: list[float]) -> dict[str, Any]:
    tmp = Path(tempfile.mkdtemp(prefix="rating-sim-"))
    _configure_offline_environment(tmp / "sim.db")

    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient

    from app.core.config import get_settings
    from app.core.database import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

    from app.main import app

    fixtures = REPOSITORY_ROOT / "data" / "fixtures"
    wardrobes = json.loads((fixtures / "stylist_benchmark_wardrobes_v1.json").read_text(encoding="utf-8"))["wardrobes"]
    bench = json.loads((fixtures / "multi_agent_benchmark_v1.json").read_text(encoding="utf-8"))
    client = TestClient(app)
    now = datetime.now(timezone.utc)

    summary = {
        "method": {
            "personas": PERSONAS, "wardrobes": list(WARDROBES), "checkpoints_ratings": list(CHECKPOINTS),
            "rated_outfit": "rank 1 of each training request", "providers": "deterministic, offline",
            "stars": "clamp(round(3 + 2 * mean item score), 1, 5) over major items",
            "context_assertions": sorted(CHECKABLE_ASSERTIONS),
            "current_learned_share": CURRENT_LEARNED_SHARE,
        },
        "runs": [_run_share(share, client, now, wardrobes, bench) for share in shares],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--learned-share", type=float, nargs="+", default=[CURRENT_LEARNED_SHARE],
                        help="Learned-affinity share(s) of the preference score; 0.20 is the application value")
    args = parser.parse_args(argv)
    if any(not 0.0 <= s <= 1.0 for s in args.learned_share):
        parser.error("--learned-share values must lie in [0, 1]")
    summary = run(args.out, args.learned_share)
    for r in summary["runs"]:
        print(json.dumps({"share": r["learned_share"], "rated_20": r["pooled"]["rated"]["20"],
                          "control_20": r["pooled"]["control"]["20"],
                          "paired_top1": r["final_paired_top1_rated_minus_control"],
                          "paired_context": r["final_paired_context_assertion_rated_minus_control"]},
                         ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
