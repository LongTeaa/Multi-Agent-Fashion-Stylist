"""Independent Layer-A invariant verification and Layer-B quality metrics."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
import random
import re
from statistics import quantiles
from typing import Any, Sequence

from sqlmodel import Session, select

from app.agents.coordinator import (
    _FORBIDDEN_EXPLANATION_PHRASES,
    validate_outfit_completeness,
)
from app.agents.wardrobe_agent import format_localized_item_name
from app.models.entities import (
    OutfitRecommendation,
    OutfitSlotRole,
    WardrobeCategory,
    WardrobeItem,
)
from app.services.garment_taxonomy import classify


CORE_ROLES = {
    OutfitSlotRole.TOP,
    OutfitSlotRole.BOTTOM,
    OutfitSlotRole.DRESS,
    OutfitSlotRole.FOOTWEAR,
}

_SLOT_ROLE_TO_CAT = {
    "top": WardrobeCategory.TOP,
    "bottom": WardrobeCategory.BOTTOM,
    "dress": WardrobeCategory.DRESS,
    "footwear": WardrobeCategory.FOOTWEAR,
    "outerwear": WardrobeCategory.OUTERWEAR,
    "accessory": WardrobeCategory.ACCESSORY,
}

_COLORS_VI = {
    "white": "trắng",
    "black": "đen",
    "grey": "xám",
    "gray": "xám",
    "navy": "xanh navy",
    "navy blue": "xanh navy",
    "blue": "xanh dương",
    "brown": "nâu",
    "beige": "be",
    "green": "xanh lá",
    "red": "đỏ",
    "cream": "kem",
    "khaki": "khaki",
    "pink": "hồng",
    "burgundy": "đỏ đô",
}


def wilson_ci_95(successes: int, total: int) -> tuple[float, float]:
    """Return 95% Wilson score confidence interval (low, high) in [0.0, 1.0]."""
    if total <= 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = successes / total
    denom = 1.0 + (z * z) / total
    center = (p + (z * z) / (2.0 * total)) / denom
    half = (z * math.sqrt((p * (1.0 - p) + (z * z) / (4.0 * total)) / total)) / denom
    return (round(max(0.0, center - half), 4), round(min(1.0, center + half), 4))


def bootstrap_mean_ci_95(
    values: Sequence[float],
    *,
    n_boot: int = 1000,
    seed: int = 20261119,
) -> tuple[float, float]:
    """Return 95% percentile bootstrap confidence interval for the mean."""
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        val = round(float(values[0]), 4)
        return (val, val)
    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    low_idx = int(0.025 * (n_boot - 1))
    high_idx = int(0.975 * (n_boot - 1))
    return (round(means[low_idx], 4), round(means[high_idx], 4))


def latency_percentiles_ms(durations_ms: Sequence[float]) -> dict[str, float]:
    """Compute p50 and p95 latency in milliseconds."""
    if not durations_ms:
        return {"mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0}
    ordered = sorted(float(d) for d in durations_ms)
    n = len(ordered)
    mean_ms = sum(ordered) / n
    if n == 1:
        val = round(ordered[0], 2)
        return {"mean_ms": val, "p50_ms": val, "p95_ms": val}
    p50 = quantiles(ordered, n=100)[49]
    p95 = quantiles(ordered, n=100)[94]
    return {
        "mean_ms": round(mean_ms, 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
    }


def core_item_ids(items: Sequence[dict[str, Any]]) -> frozenset[str]:
    """Return canonical core item identifiers (raw_id preferred for cross-user comparisons)."""
    return frozenset(
        str(it.get("raw_id") or it.get("item_id") or "")
        for it in items
        if str(it.get("slot") or it.get("slot_role") or "") in {"top", "bottom", "dress", "footwear"}
    )


def compute_top3_core_diversity(outfits: Sequence[dict[str, Any]]) -> float | None:
    """Compute 1 - mean pairwise Jaccard overlap across recommended core signatures."""
    if len(outfits) < 2:
        return None
    sigs = [core_item_ids(o.get("items", [])) for o in outfits]
    overlaps: list[float] = []
    for i in range(len(sigs)):
        for j in range(i + 1, len(sigs)):
            union = sigs[i] | sigs[j]
            ov = (len(sigs[i] & sigs[j]) / len(union)) if union else 1.0
            overlaps.append(ov)
    if not overlaps:
        return None
    return round(1.0 - (sum(overlaps) / len(overlaps)), 4)


def _allowed_brackets_for_db_item(db_item: WardrobeItem) -> set[str]:
    loc_name = format_localized_item_name(db_item)
    _, garment = classify(db_item.category, loc_name)
    label = garment.label if garment else loc_name
    allowed = {f"[{label.strip().lower()}]", f"[{loc_name.strip().lower()}]"}
    if db_item.sub_category:
        _, sub_g = classify(db_item.category, db_item.sub_category)
        if sub_g:
            allowed.add(f"[{sub_g.label.strip().lower()}]")
    color = db_item.primary_color.strip().lower()
    color_label = _COLORS_VI.get(color, color)
    if color_label and color_label != "unknown":
        allowed.add(f"[{label.strip().lower()} {color_label}]")
    for col_vi in (*_COLORS_VI.values(), "khaki", "kaki", "kem"):
        raw_lower = loc_name.strip().lower()
        if raw_lower.endswith(f" {col_vi}"):
            base_only = raw_lower[: -len(col_vi)].strip()
            if base_only:
                allowed.add(f"[{base_only}]")
    return allowed


def _build_lightweight_slot_for_completeness(slot_role_str: str, item_id: str) -> Any:
    """Create a minimal object matching validate_outfit_completeness expectations."""
    from types import SimpleNamespace

    return SimpleNamespace(slot_role=OutfitSlotRole(slot_role_str), item_id=item_id)


@dataclass
class LayerAResult:
    total_outfits: int = 0
    valid_grounding_outfits: int = 0
    valid_structure_outfits: int = 0
    factual_explanations: int = 0
    must_avoid_checked_outfits: int = 0
    must_avoid_compliant_outfits: int = 0
    bounded_and_persist_passed: bool = True
    violations: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations


def verify_layer_a_for_case(
    *,
    session: Session,
    run_user_id: str,
    request_id: str,
    system_id: str,
    case: dict[str, Any],
    result: dict[str, Any],
    check_persistence: bool = True,
) -> LayerAResult:
    """Verify Layer-A mandatory technical invariants independently against DB rows."""
    res = LayerAResult()
    status = str(result.get("status", "error"))
    outfits: list[dict[str, Any]] = list(result.get("outfits", []))
    is_graph_system = system_id in {
        "B1",
        "M-Full",
        "M-NoLoop1",
        "M-NoLoop2",
        "M-NoLoops",
        "M-NoPersonalization",
    }

    if is_graph_system:
        relax_round = int(result.get("relaxation_round", 0))
        crit_round = int(result.get("critique_round", 0))
        trace_len = len(result.get("agent_trace", []))
        if relax_round > 2 or crit_round > 1 or trace_len > 15:
            res.bounded_and_persist_passed = False
            res.violations.append(
                f"Bounded termination violated: relax={relax_round}, crit={crit_round}, trace={trace_len}"
            )

    if check_persistence and is_graph_system:
        db_recs = session.exec(
            select(OutfitRecommendation).where(
                OutfitRecommendation.user_id == run_user_id,
                OutfitRecommendation.request_id == request_id,
            )
        ).all()
        rec_ids = list(result.get("recommendation_ids", []))
        if status == "ok":
            if len(db_recs) != len(outfits) or set(rec_ids) != {r.id for r in db_recs}:
                res.bounded_and_persist_passed = False
                res.violations.append(
                    f"Persistence mismatch: db_recs={len(db_recs)}, outfits={len(outfits)}, rec_ids={len(rec_ids)}"
                )
        else:
            if len(db_recs) != 0:
                res.bounded_and_persist_passed = False
                res.violations.append(
                    f"Non-ok status '{status}' persisted {len(db_recs)} DB rows"
                )

    if status != "ok":
        return res

    if not (1 <= len(outfits) <= 3):
        res.violations.append(f"Expected 1..3 outfits on status=ok, got {len(outfits)}")

    assertions = case.get("assertions") or {}
    avoid_colors = {str(c).lower().strip() for c in assertions.get("must_avoid_colors", [])}
    avoid_subs = {str(s).lower().strip() for s in assertions.get("must_avoid_subcategories", [])}
    has_must_avoid = bool(avoid_colors or avoid_subs)

    db_items_map = {
        row.id: row
        for row in session.exec(
            select(WardrobeItem).where(WardrobeItem.user_id == run_user_id)
        ).all()
    }

    for outfit in outfits:
        res.total_outfits += 1
        items: list[dict[str, Any]] = list(outfit.get("items", []))
        rank = outfit.get("rank", "?")

        # 1. Grounding on DB
        grounding_ok = bool(items)
        matched_db_rows: list[WardrobeItem] = []
        light_slots: list[Any] = []
        structure_ok = True
        for it in items:
            iid = str(it.get("item_id", ""))
            slot_str = str(it.get("slot") or it.get("slot_role") or "")
            db_row = db_items_map.get(iid)
            if (
                db_row is None
                or not db_row.is_active
                or not db_row.is_user_confirmed
                or db_row.deleted_at is not None
            ):
                grounding_ok = False
                res.violations.append(f"Rank {rank}: invalid or missing DB item_id '{iid}'")
            else:
                expected_cat = _SLOT_ROLE_TO_CAT.get(slot_str)
                if expected_cat is None or db_row.category != expected_cat:
                    grounding_ok = False
                    res.violations.append(
                        f"Rank {rank}: item '{iid}' category={db_row.category} mismatch slot='{slot_str}'"
                    )
                matched_db_rows.append(db_row)

            try:
                light_slots.append(_build_lightweight_slot_for_completeness(slot_str, iid))
            except ValueError:
                structure_ok = False

        if grounding_ok:
            res.valid_grounding_outfits += 1

        # 2. Structure completeness
        if structure_ok:
            comp_ok, comp_err = validate_outfit_completeness(light_slots)
            if not comp_ok:
                structure_ok = False
                res.violations.append(f"Rank {rank}: invalid structure ({comp_err})")
        if structure_ok:
            res.valid_structure_outfits += 1

        # 3. Must-avoid compliance
        if has_must_avoid:
            res.must_avoid_checked_outfits += 1
            avoid_violated = False
            for db_row in matched_db_rows:
                c1 = db_row.primary_color.lower().strip()
                c2 = (db_row.secondary_color or "").lower().strip()
                sub = db_row.sub_category.lower().strip()
                if c1 in avoid_colors or (c2 and c2 in avoid_colors):
                    avoid_violated = True
                    res.violations.append(
                        f"Rank {rank}: item '{db_row.id}' violates must_avoid color"
                    )
                if sub in avoid_subs or (sub == "sandal" and "sandals" in avoid_subs) or (sub == "jean" and "jeans" in avoid_subs):
                    avoid_violated = True
                    res.violations.append(
                        f"Rank {rank}: item '{db_row.id}' violates must_avoid sub_category '{sub}'"
                    )
            if not avoid_violated:
                res.must_avoid_compliant_outfits += 1

        # 4. Explanation factuality (strict bracket check + forbidden phrases)
        exp_text = str(outfit.get("explanation_vi") or "").strip()
        exp_ok = len(exp_text) >= 10
        lowered = exp_text.lower()
        if any(phrase in lowered for phrase in _FORBIDDEN_EXPLANATION_PHRASES):
            exp_ok = False
            res.violations.append(f"Rank {rank}: explanation contains forbidden subjective claim")

        if matched_db_rows and grounding_ok:
            allowed_groups = [_allowed_brackets_for_db_item(row) for row in matched_db_rows]
            all_allowed = set().union(*allowed_groups) if allowed_groups else set()
            found_brackets = {f"[{m.strip().lower()}]" for m in re.findall(r"\[([^\[\]]+)\]", exp_text)}
            if found_brackets and not found_brackets.issubset(all_allowed):
                exp_ok = False
                res.violations.append(
                    f"Rank {rank}: explanation hallucinated brackets {sorted(found_brackets - all_allowed)}"
                )
            for grp in allowed_groups:
                if not any(tok in lowered for tok in grp):
                    # Allow fallback check: single-prompt LLM may write bracketed item IDs or names; missing canonical bracket counts as factuality gap
                    exp_ok = False
                    res.violations.append(
                        f"Rank {rank}: explanation omits canonical garment bracket {sorted(grp)[0]}"
                    )
                    break
        elif not grounding_ok:
            exp_ok = False

        if exp_ok:
            res.factual_explanations += 1

    return res


def check_case_functional_assertions(
    case: dict[str, Any],
    result: dict[str, Any],
) -> list[str]:
    """Evaluate case-level status, trace milestones, and functional assertions."""
    failures: list[str] = []
    expected_status = case.get("expected_status", "ok")
    actual_status = result.get("status")
    if actual_status != expected_status:
        failures.append(f"Expected status='{expected_status}', got '{actual_status}' (err={result.get('error_code')})")
        return failures

    if expected_status == "error" and case.get("expected_error"):
        if result.get("error_code") != case.get("expected_error"):
            failures.append(
                f"Expected error_code='{case.get('expected_error')}', got '{result.get('error_code')}'"
            )

    assertions = case.get("assertions") or {}
    outfits = list(result.get("outfits", []))
    min_o = assertions.get("min_outfits")
    max_o = assertions.get("max_outfits")
    if min_o is not None and len(outfits) < int(min_o):
        failures.append(f"Expected >= {min_o} outfits, got {len(outfits)}")
    if max_o is not None and len(outfits) > int(max_o):
        failures.append(f"Expected <= {max_o} outfits, got {len(outfits)}")

    if "max_relaxation_round" in assertions:
        if int(result.get("relaxation_round", 0)) > int(assertions["max_relaxation_round"]):
            failures.append(
                f"relaxation_round={result.get('relaxation_round')} > max {assertions['max_relaxation_round']}"
            )

    if "expected_critique_round" in assertions:
        if int(result.get("critique_round", 0)) != int(assertions["expected_critique_round"]):
            failures.append(
                f"critique_round={result.get('critique_round')} != expected {assertions['expected_critique_round']}"
            )

    if "expected_relaxation_actions" in assertions:
        actual_actions = {s.get("action") for s in result.get("active_relaxations", [])}
        for req_action in assertions["expected_relaxation_actions"]:
            if req_action not in actual_actions:
                failures.append(f"Missing expected relaxation action '{req_action}' (got {sorted(actual_actions)})")

    if "expected_conflict_types" in assertions:
        actual_conflicts = {c.get("conflict_type") for c in result.get("conflict_notes", [])}
        for req_c in assertions["expected_conflict_types"]:
            if req_c not in actual_conflicts:
                failures.append(f"Missing expected conflict_type '{req_c}' (got {sorted(actual_conflicts)})")

    expected_trace = case.get("expected_trace_events") or []
    if expected_trace:
        actual_events = [str(ev.get("event_type", "")) for ev in result.get("agent_trace", [])]
        pos = 0
        for ev in actual_events:
            if pos < len(expected_trace) and ev == expected_trace[pos]:
                pos += 1
        if pos < len(expected_trace):
            failures.append(
                f"Trace missing milestone '{expected_trace[pos]}' in sequence {actual_events}"
            )

    if outfits:
        top1 = outfits[0]
        top1_ids = {str(it.get("raw_id") or it.get("item_id") or "") for it in top1.get("items", [])}
        top1_cats = {str(it.get("slot") or it.get("slot_role") or "") for it in top1.get("items", [])}

        for req_id in assertions.get("top1_must_include_items", []):
            if req_id not in top1_ids:
                failures.append(f"Top 1 missing item '{req_id}' (got {sorted(top1_ids)})")
        for excl_id in assertions.get("top1_must_exclude_items", []):
            if excl_id in top1_ids:
                failures.append(f"Top 1 included forbidden item '{excl_id}'")
        for req_cat in assertions.get("top1_must_include_categories", []):
            if req_cat not in top1_cats:
                failures.append(f"Top 1 missing category '{req_cat}' (got {sorted(top1_cats)})")

        not_exact = assertions.get("top1_must_not_exact_item_set") or []
        if not_exact:
            target_set = {str(x) for x in not_exact}
            if target_set.issubset(top1_ids):
                failures.append(f"Top 1 repeated recently worn exact outfit {sorted(target_set)}")

        must_contain_any = assertions.get("explanation_must_contain_any") or []
        if must_contain_any:
            exp_low = str(top1.get("explanation_vi", "")).lower()
            if not any(phrase.lower() in exp_low for phrase in must_contain_any):
                failures.append(
                    f"Top 1 explanation missing any of {must_contain_any}"
                )

    return failures


def compute_context_metrics(
    cases: Sequence[dict[str, Any]],
    results_by_case: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute B1 Context Understanding exact field accuracy, Macro-F1, and Gemini usage rate."""
    fields = (
        "occasion",
        "time_of_day",
        "weather_condition",
        "target_formality_range",
        "needs_clarification",
    )
    field_hits: dict[str, int] = defaultdict(int)
    field_totals: dict[str, int] = defaultdict(int)
    clar_tp = clar_fp = clar_fn = clar_tn = 0
    gemini_used_count = 0
    llm_eligible_cases = 0

    for case in cases:
        cid = str(case["id"])
        expected = case.get("expected_context") or {}
        res = results_by_case.get(cid)
        if not expected or not res:
            continue

        ctx_used = res.get("context_used")
        if ctx_used in {"gemini", "rules_fallback"}:
            llm_eligible_cases += 1
            if ctx_used == "gemini":
                gemini_used_count += 1

        ctx = res.get("context") or {}
        for f in fields:
            if f not in expected:
                continue
            field_totals[f] += 1
            if ctx.get(f) == expected[f]:
                field_hits[f] += 1

        if "needs_clarification" in expected:
            exp_clar = bool(expected["needs_clarification"])
            act_clar = bool(ctx.get("needs_clarification"))
            if exp_clar and act_clar:
                clar_tp += 1
            elif not exp_clar and act_clar:
                clar_fp += 1
            elif exp_clar and not act_clar:
                clar_fn += 1
            else:
                clar_tn += 1

    total_checks = sum(field_totals.values())
    total_hits = sum(field_hits.values())
    micro_acc = round(total_hits / total_checks, 4) if total_checks else None
    per_field = {
        f: round(field_hits[f] / field_totals[f], 4) if field_totals[f] else None
        for f in fields
    }
    prec = clar_tp / (clar_tp + clar_fp) if (clar_tp + clar_fp) else (1.0 if clar_tp == 0 and clar_fn == 0 else 0.0)
    rec = clar_tp / (clar_tp + clar_fn) if (clar_tp + clar_fn) else 1.0
    clar_f1 = round((2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0, 4)
    clar_total = clar_tp + clar_fp + clar_fn + clar_tn
    clar_acc = round((clar_tp + clar_tn) / clar_total, 4) if clar_total else None

    return {
        "micro_field_accuracy": micro_acc,
        "hits": total_hits,
        "total_checks": total_checks,
        "per_field_accuracy": per_field,
        "clarification_accuracy": clar_acc,
        "clarification_f1": clar_f1,
        "context_llm_used_rate": round(gemini_used_count / llm_eligible_cases, 4) if llm_eligible_cases else None,
        "context_llm_used_count": f"{gemini_used_count}/{llm_eligible_cases}" if llm_eligible_cases else "N/A",
    }


def compute_ndcg_at_3(ranked_scores: Sequence[float], ideal_pool: Sequence[float] | None = None) -> float:
    """Compute normalized discounted cumulative gain @3 from 1..5 judge scores."""
    if not ranked_scores:
        return 0.0
    top3 = [max(1.0, float(s)) for s in ranked_scores[:3]]
    dcg = sum((2.0 ** (s - 1.0) - 1.0) / math.log2(idx + 2) for idx, s in enumerate(top3))
    ideal_source = sorted([max(1.0, float(s)) for s in (ideal_pool or top3)], reverse=True)[:3]
    # Pad up to len(top3) with max theoretical score 5.0 if pool is smaller than top3
    while len(ideal_source) < len(top3):
        ideal_source.append(5.0)
    idcg = sum((2.0 ** (s - 1.0) - 1.0) / math.log2(idx + 2) for idx, s in enumerate(ideal_source[: len(top3)]))
    return round(min(1.0, dcg / idcg), 4) if idcg > 0 else 0.0


def compute_spearman_rho(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Compute Spearman rank correlation coefficient without external dependencies."""
    if len(xs) != len(ys) or len(xs) < 2:
        return None

    def _ranks(vals: Sequence[float]) -> list[float]:
        indexed = sorted(enumerate(vals), key=lambda p: p[1])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(indexed):
            j = i
            while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[indexed[k][0]] = avg_rank
            i = j + 1
        return ranks

    rx = _ranks(xs)
    ry = _ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den_x = math.sqrt(sum((a - mx) ** 2 for a in rx))
    den_y = math.sqrt(sum((b - my) ** 2 for b in ry))
    if den_x == 0 or den_y == 0:
        return None
    return round(num / (den_x * den_y), 4)


def compute_net_loop_impact(
    cases: Sequence[dict[str, Any]],
    full_results: dict[str, dict[str, Any]],
    ablated_results: dict[str, dict[str, Any]],
    *,
    full_case_pass: dict[str, bool],
    ablated_case_pass: dict[str, bool],
    full_ndcg: dict[str, float] | None = None,
    ablated_ndcg: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Compare M-Full against an ablated variant across every case to quantify improved vs degraded cases."""
    improved_ids: list[str] = []
    degraded_ids: list[str] = []
    unchanged_ids: list[str] = []

    for case in cases:
        cid = str(case["id"])
        if cid not in full_results or cid not in ablated_results:
            continue
        f_pass = bool(full_case_pass.get(cid, False))
        a_pass = bool(ablated_case_pass.get(cid, False))
        f_status = full_results[cid].get("status")
        a_status = ablated_results[cid].get("status")

        score_diff = 0.0
        if full_ndcg is not None and ablated_ndcg is not None and cid in full_ndcg and cid in ablated_ndcg:
            score_diff = full_ndcg[cid] - ablated_ndcg[cid]

        if (f_pass and not a_pass) or (case.get("expected_status") == "ok" and f_status == "ok" and a_status == "error") or score_diff >= 0.03:
            improved_ids.append(cid)
        elif (not f_pass and a_pass) or (case.get("expected_status") == "ok" and f_status == "error" and a_status == "ok") or score_diff <= -0.03:
            degraded_ids.append(cid)
        else:
            unchanged_ids.append(cid)

    total = len(improved_ids) + len(degraded_ids) + len(unchanged_ids)
    return {
        "total_compared": total,
        "improved_count": len(improved_ids),
        "unchanged_count": len(unchanged_ids),
        "degraded_count": len(degraded_ids),
        "net_gain": len(improved_ids) - len(degraded_ids),
        "improved_case_ids": improved_ids,
        "degraded_case_ids": degraded_ids,
    }
