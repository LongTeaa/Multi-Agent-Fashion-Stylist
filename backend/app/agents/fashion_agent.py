from __future__ import annotations

from datetime import datetime
from typing import Any
from app.agents.fashion_scoring import (
    calculate_composite_fashion_score,
    count_recently_worn_items,
    outfit_tie_breaker_key,
)
from app.agents.state import (
    EvaluatedOutfit,
    OutfitItemSlot,
    StylistContext,
    StylistGraphState,
)
from app.models.entities import OutfitSlotRole

MAX_CATEGORY_POOL = 15
MAX_GENERATED_COMBINATIONS = 500
TOP_K_OUTFITS = 5
NO_COMPLETE_OUTFIT_ERROR = "NO_COMPLETE_OUTFIT"
NO_COMPLETE_OUTFIT_WARNING = "Không thể ghép được bộ trang phục hoàn chỉnh từ các món đồ trong tủ đồ."

ROLE_ORDER: dict[OutfitSlotRole, int] = {
    OutfitSlotRole.TOP: 0,
    OutfitSlotRole.DRESS: 0,
    OutfitSlotRole.BOTTOM: 1,
    OutfitSlotRole.FOOTWEAR: 2,
    OutfitSlotRole.OUTERWEAR: 3,
    OutfitSlotRole.ACCESSORY: 4,
}


def _generate_top_bottom_combos(
    tops: list[OutfitItemSlot],
    bottoms: list[OutfitItemSlot],
    footwear: list[OutfitItemSlot],
    outerwear: list[OutfitItemSlot],
    accessories: list[OutfitItemSlot],
    limit: int,
) -> list[list[OutfitItemSlot]]:
    """Helper to generate top + bottom + footwear combinations up to limit."""
    combos: list[list[OutfitItemSlot]] = []
    for top in tops:
        for bottom in bottoms:
            for shoe in footwear:
                if len(combos) >= limit:
                    return combos
                combos.append([top, bottom, shoe])

                for out in outerwear:
                    if len(combos) >= limit:
                        return combos
                    combos.append([top, bottom, shoe, out])

                    for acc in accessories:
                        if len(combos) >= limit:
                            return combos
                        combos.append([top, bottom, shoe, out, acc])

                for acc in accessories:
                    if len(combos) >= limit:
                        return combos
                    combos.append([top, bottom, shoe, acc])
    return combos


def _generate_dress_combos(
    dresses: list[OutfitItemSlot],
    footwear: list[OutfitItemSlot],
    outerwear: list[OutfitItemSlot],
    accessories: list[OutfitItemSlot],
    limit: int,
) -> list[list[OutfitItemSlot]]:
    """Helper to generate dress + footwear combinations up to limit."""
    combos: list[list[OutfitItemSlot]] = []
    for dress in dresses:
        for shoe in footwear:
            if len(combos) >= limit:
                return combos
            combos.append([dress, shoe])

            for out in outerwear:
                if len(combos) >= limit:
                    return combos
                combos.append([dress, shoe, out])

                for acc in accessories:
                    if len(combos) >= limit:
                        return combos
                    combos.append([dress, shoe, out, acc])

            for acc in accessories:
                if len(combos) >= limit:
                    return combos
                combos.append([dress, shoe, acc])
    return combos


def generate_outfit_combinations(
    candidate_pool: dict[str, list[OutfitItemSlot]],
) -> list[list[OutfitItemSlot]]:
    """Generate valid outfit candidate combinations from candidate pools.
    
    Enforces Phase Invariants:
    - Valid outfit is either:
      1. top + bottom + footwear (optional outerwear, optional accessory)
      2. dress + footwear (optional outerwear, optional accessory)
    - Must never combine dress with top or bottom.
    - Accessories cannot make an incomplete outfit complete.
    - Category pools capped at 15. Total combinations capped at 500.
    - Fair branch quota with dynamic redistribution:
      Guarantees dress branch up to 150 combinations (preventing starvation by large top+bottom pools).
      Any unused quota from one branch is dynamically redistributed to the other branch,
      maximizing exploration up to the 500 cap.
    """
    tops = candidate_pool.get("tops", [])[:MAX_CATEGORY_POOL]
    bottoms = candidate_pool.get("bottoms", [])[:MAX_CATEGORY_POOL]
    dresses = candidate_pool.get("dresses", [])[:MAX_CATEGORY_POOL]
    footwear = candidate_pool.get("footwear", [])[:MAX_CATEGORY_POOL]
    outerwear = candidate_pool.get("outerwear", [])[:MAX_CATEGORY_POOL]
    accessories = candidate_pool.get("accessories", [])[:MAX_CATEGORY_POOL]

    has_branch_1 = bool(tops and bottoms and footwear)
    has_branch_2 = bool(dresses and footwear)

    if not has_branch_1 and not has_branch_2:
        return []

    if has_branch_1 and not has_branch_2:
        all_combinations = _generate_top_bottom_combos(
            tops, bottoms, footwear, outerwear, accessories, MAX_GENERATED_COMBINATIONS
        )
    elif has_branch_2 and not has_branch_1:
        all_combinations = _generate_dress_combos(
            dresses, footwear, outerwear, accessories, MAX_GENERATED_COMBINATIONS
        )
    else:
        # Both branches are viable:
        # Step 1: Generate dress combinations up to reserved dress quota (150)
        branch_2_combos = _generate_dress_combos(
            dresses, footwear, outerwear, accessories, 150
        )
        # Step 2: Top+bottom branch receives the remainder of the 500 quota (at least 350)
        quota_branch_1 = MAX_GENERATED_COMBINATIONS - len(branch_2_combos)
        branch_1_combos = _generate_top_bottom_combos(
            tops, bottoms, footwear, outerwear, accessories, quota_branch_1
        )

        # Step 3: If top+bottom branch used less than its quota and dress branch hit its 150 cap,
        # allow dress branch to expand up to the remaining unused capacity.
        total_used = len(branch_1_combos) + len(branch_2_combos)
        if total_used < MAX_GENERATED_COMBINATIONS and len(branch_2_combos) == 150:
            extra_dress_limit = MAX_GENERATED_COMBINATIONS - len(branch_1_combos)
            branch_2_combos = _generate_dress_combos(
                dresses, footwear, outerwear, accessories, extra_dress_limit
            )

        all_combinations = branch_1_combos + branch_2_combos

    # Sort items within each combination for deterministic combination_id
    sorted_combinations: list[list[OutfitItemSlot]] = []
    for combo in all_combinations:
        sorted_combo = sorted(combo, key=lambda item: (ROLE_ORDER.get(item.slot_role, 99), item.item_id))
        sorted_combinations.append(sorted_combo)

    return sorted_combinations


def evaluate_and_rank_combinations(
    combinations: list[list[OutfitItemSlot]],
    context: StylistContext | None = None,
    top_k: int = TOP_K_OUTFITS,
    reference_time: datetime | None = None,
    recent_window_hours: int = 48,
) -> tuple[list[EvaluatedOutfit], list[str]]:
    """Score every combination, apply deterministic tie-breaking with recent wear data, and return top-k."""
    evaluated_outfits: list[EvaluatedOutfit] = []
    all_warnings: list[str] = []

    for combo in combinations:
        combo_id = "+".join(item.item_id for item in combo)
        score, component_scores, warnings = calculate_composite_fashion_score(combo, context)
        all_warnings.extend(warnings)

        evaluated = EvaluatedOutfit(
            items=combo,
            fashion_score=score,
            component_scores=component_scores,
            combination_id=combo_id,
        )
        evaluated_outfits.append(evaluated)

    # Sort deterministically using tie-breaker key:
    # (-fashion_score, -weather_score, recent_wear_count, combination_id)
    # recent_wear_count counts items worn within recent_window_hours using last_worn_at
    evaluated_outfits.sort(
        key=lambda o: outfit_tie_breaker_key(
            o,
            recent_wear_count=count_recently_worn_items(
                o.items,
                reference_time=reference_time,
                recent_window_hours=recent_window_hours,
            ),
        )
    )

    unique_warnings = list(dict.fromkeys(all_warnings))
    return evaluated_outfits[:top_k], unique_warnings


def fashion_agent_node(state: StylistGraphState) -> dict[str, Any]:
    """LangGraph node execution function for the Fashion Agent.
    
    Consumes candidate_pool, generates combinations, scores them,
    and populates evaluated_outfits.
    """
    context = state.get("context")
    candidate_pool = state.get("candidate_pool", {})

    # If clarification is requested or context is missing, return empty evaluated_outfits
    if context is None or context.needs_clarification:
        return {"evaluated_outfits": []}

    existing_errors = list(state.get("errors", []))
    existing_warnings = list(state.get("warnings", []))

    combinations = generate_outfit_combinations(candidate_pool)

    if not combinations:
        return {
            "evaluated_outfits": [],
            "errors": existing_errors + [NO_COMPLETE_OUTFIT_ERROR],
            "warnings": existing_warnings + [NO_COMPLETE_OUTFIT_WARNING],
        }

    ref_time = state.get("reference_time")
    top_evaluated, warnings = evaluate_and_rank_combinations(
        combinations, context, reference_time=ref_time
    )

    return {
        "evaluated_outfits": top_evaluated,
        "warnings": existing_warnings + warnings,
    }
