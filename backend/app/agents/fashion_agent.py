from __future__ import annotations

from collections.abc import Sequence
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)
from app.agents.fashion_scoring import (
    calculate_composite_fashion_score,
    count_recently_worn_items,
    outfit_tie_breaker_key,
)
from app.agents.state import (
    AgentTraceEvent,
    CritiqueSignal,
    EvaluatedOutfit,
    GarmentConstraint,
    OutfitItemSlot,
    RelaxAction,
    RelaxationRequest,
    RelaxationStep,
    SlotName,
    StylistContext,
    StylistGraphState,
    is_relaxation_loop_enabled,
)
from app.agents.wardrobe_agent import RELAX_COLOR_FAMILIES, SUBCATEGORY_EQUIVALENTS
from app.models.entities import OutfitSlotRole, WardrobeCategory

MAX_CATEGORY_POOL = 15
MAX_GENERATED_COMBINATIONS = 500
TOP_K_OUTFITS = 5
MAX_EVALUATED_OUTFITS = 50
MAX_RELAXATION_ROUNDS = 2
NO_COMPLETE_OUTFIT_ERROR = "NO_COMPLETE_OUTFIT"
NO_COMPLETE_OUTFIT_WARNING = "Không thể ghép được bộ trang phục hoàn chỉnh từ các món đồ trong tủ đồ."

CATEGORY_TO_SLOT_NAME: dict[WardrobeCategory, SlotName] = {
    WardrobeCategory.TOP: "tops",
    WardrobeCategory.BOTTOM: "bottoms",
    WardrobeCategory.DRESS: "dresses",
    WardrobeCategory.FOOTWEAR: "footwear",
    WardrobeCategory.OUTERWEAR: "outerwear",
    WardrobeCategory.ACCESSORY: "accessories",
}

ROLE_ORDER: dict[OutfitSlotRole, int] = {
    OutfitSlotRole.TOP: 0,
    OutfitSlotRole.DRESS: 0,
    OutfitSlotRole.BOTTOM: 1,
    OutfitSlotRole.FOOTWEAR: 2,
    OutfitSlotRole.OUTERWEAR: 3,
    OutfitSlotRole.ACCESSORY: 4,
}


_SUBCATEGORY_ALIASES = {
    "jean": "jeans",
    "sneaker": "sneakers",
    "sandal": "sandals",
}


def _normalized_value(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return _SUBCATEGORY_ALIASES.get(normalized, normalized)


def constraint_matches_item(
    constraint: GarmentConstraint,
    item: OutfitItemSlot,
    active_relaxations: Sequence[RelaxationStep] | None = None,
) -> bool:
    """Return whether one item satisfies every populated constraint field, accounting for active relaxations."""
    # INVARIANT: category is NEVER relaxed.
    if constraint.category is not None and item.category != constraint.category:
        return False

    steps = [s for s in (active_relaxations or ()) if s.category == item.category]

    if constraint.sub_category is not None:
        target_sub = _normalized_value(constraint.sub_category)
        item_sub = _normalized_value(item.sub_category)
        # Generic 'dress' constraint accepts specific dress taxonomy subtypes (formal_dress, midi_dress, ...)
        if not (constraint.category == WardrobeCategory.DRESS and target_sub == "dress" and item.category == WardrobeCategory.DRESS):
            allowed_subs = {target_sub}
            for s in steps:
                if s.action == "subcategory_equivalent" and _normalized_value(s.original_value) == target_sub:
                    allowed_subs.update(_normalized_value(v) for v in s.relaxed_values)
            if item_sub not in allowed_subs:
                return False

    if constraint.color is not None:
        target_col = _normalized_value(constraint.color)
        colors = {_normalized_value(item.primary_color)}
        if item.secondary_color:
            colors.add(_normalized_value(item.secondary_color))
        allowed_colors = {target_col}
        for s in steps:
            if s.action == "color_family" and _normalized_value(s.original_value) == target_col:
                allowed_colors.update(_normalized_value(v) for v in s.relaxed_values)
        if not (colors & allowed_colors):
            return False

    if constraint.material is not None:
        target_mat = _normalized_value(constraint.material)
        material_relaxed = any(
            s.action == "material_relax" and _normalized_value(s.original_value) == target_mat
            for s in steps
        )
        if not material_relaxed and _normalized_value(item.material) != target_mat:
            return False

    return True


def outfit_satisfies_explicit_constraints(
    items: list[OutfitItemSlot],
    context: StylistContext,
    active_relaxations: Sequence[RelaxationStep] | None = None,
) -> bool:
    """Enforce query-level must-have (with active relaxations) and strict must-avoid bindings."""
    if any(
        not any(constraint_matches_item(constraint, item, active_relaxations) for item in items)
        for constraint in context.structured_must_have
    ):
        return False
    # INVARIANT: structured_must_avoid is NEVER relaxed.
    if any(
        any(constraint_matches_item(constraint, item, None) for item in items)
        for constraint in context.structured_must_avoid
    ):
        return False
    return True


def _has_direct_avoid_conflict(
    constraint: GarmentConstraint,
    avoid_constraints: Sequence[GarmentConstraint],
) -> tuple[bool, bool]:
    """Return whether constraint color or sub_category is directly banned by structured_must_avoid."""
    color_banned = False
    sub_banned = False
    c_col = _normalized_value(constraint.color) if constraint.color is not None else None
    c_sub = _normalized_value(constraint.sub_category) if constraint.sub_category is not None else None
    for avoid in avoid_constraints:
        cat_match = avoid.category is None or constraint.category is None or avoid.category == constraint.category
        if not cat_match:
            continue
        if c_col is not None and avoid.color is not None and _normalized_value(avoid.color) == c_col:
            if avoid.sub_category is None or (c_sub is not None and _normalized_value(avoid.sub_category) == c_sub):
                color_banned = True
        if c_sub is not None and avoid.sub_category is not None and _normalized_value(avoid.sub_category) == c_sub:
            if avoid.color is None:
                sub_banned = True
    return color_banned, sub_banned


def diagnose_bottleneck(
    candidate_pool: dict[str, list[OutfitItemSlot]],
    combinations: list[list[OutfitItemSlot]],
    context: StylistContext,
    relaxation_round: int,
    active_relaxations: Sequence[RelaxationStep] | None = None,
) -> RelaxationRequest | None:
    """Diagnose an unsatisfiable constraint bottleneck and propose one bounded RelaxationRequest."""
    if relaxation_round >= MAX_RELAXATION_ROUNDS or not context.structured_must_have:
        return None

    applied = {
        (s.category, s.action, _normalized_value(s.original_value))
        for s in (active_relaxations or ())
    }

    # Case 1: combinations is empty (a required slot failed strict must_have in retrieval_service).
    # If no structured_must_have locks that empty slot, the user's wardrobe truly lacks the category -> return None.
    if not combinations:
        blocked_slots: list[SlotName] = []
        blocked_constraints: list[GarmentConstraint] = []
        allowed_actions: list[RelaxAction] = []

        for c in context.structured_must_have:
            if c.category is None:
                continue
            slot_name = CATEGORY_TO_SLOT_NAME[c.category]
            if candidate_pool.get(slot_name):
                continue

            _, sub_conflict = _has_direct_avoid_conflict(c, context.structured_must_avoid)
            added_for_c = False
            if c.material is not None and (c.category, "material_relax", _normalized_value(c.material)) not in applied:
                if "material_relax" not in allowed_actions:
                    allowed_actions.append("material_relax")
                added_for_c = True
            # Only widen sub_category when no material constraint is pending relaxation,
            # preserving exact garment subtype (e.g. linen shirt -> cotton shirt before polo).
            if c.sub_category is not None and not added_for_c and not sub_conflict:
                norm_sub = _normalized_value(c.sub_category)
                raw_sub = c.sub_category.strip().lower()
                has_equiv = (
                    (c.category, norm_sub) in SUBCATEGORY_EQUIVALENTS
                    or (c.category, raw_sub) in SUBCATEGORY_EQUIVALENTS
                )
                if has_equiv and (c.category, "subcategory_equivalent", norm_sub) not in applied:
                    if "subcategory_equivalent" not in allowed_actions:
                        allowed_actions.append("subcategory_equivalent")
                    added_for_c = True

            if added_for_c:
                blocked_slots.append(slot_name)
                blocked_constraints.append(c)

        if not blocked_slots or not allowed_actions:
            return None

        return RelaxationRequest(
            issue_code="MISSING_SLOT",
            bottleneck_slots=list(dict.fromkeys(blocked_slots)),
            blocked_constraints=blocked_constraints,
            allowed_actions=allowed_actions,
            reason_vi="Không tìm thấy đúng kiểu dáng/chất liệu yêu cầu trong tủ đồ, đề xuất tìm kiểu tương đương cùng nhóm.",
        )

    # Case 2: combinations exist, but all failed outfit_satisfies_explicit_constraints.
    unsatisfied_constraints = [
        c
        for c in context.structured_must_have
        if not any(
            any(constraint_matches_item(c, item, active_relaxations) for item in combo)
            for combo in combinations
        )
    ]
    if not unsatisfied_constraints:
        return None

    bottleneck_slots: list[SlotName] = []
    blocked_constraints: list[GarmentConstraint] = []
    allowed_actions: list[RelaxAction] = []

    for c in unsatisfied_constraints:
        if c.category is None:
            continue
        slot_name = CATEGORY_TO_SLOT_NAME[c.category]
        # Only relax if this category actually has candidates; never jump top+bottom <-> dress.
        if not candidate_pool.get(slot_name):
            continue

        added_for_c = False
        color_conflict, sub_conflict = _has_direct_avoid_conflict(c, context.structured_must_avoid)
        slot_items = candidate_pool[slot_name]
        # Check whether an item in slot already satisfies sub_category (and material) so we only
        # relax what is actually blocking instead of firing unnecessary subcategory relaxations.
        has_sub_match = c.sub_category is None or any(
            _normalized_value(it.sub_category) == _normalized_value(c.sub_category)
            for it in slot_items
        )
        has_mat_match = c.material is None or any(
            _normalized_value(it.material) == _normalized_value(c.material)
            for it in slot_items
        )

        if c.color is not None and not color_conflict and has_sub_match and has_mat_match:
            norm_col = _normalized_value(c.color)
            if norm_col in RELAX_COLOR_FAMILIES and (c.category, "color_family", norm_col) not in applied:
                if "color_family" not in allowed_actions:
                    allowed_actions.append("color_family")
                added_for_c = True
        if c.material is not None and not has_mat_match and (c.category, "material_relax", _normalized_value(c.material)) not in applied:
            if "material_relax" not in allowed_actions:
                allowed_actions.append("material_relax")
            added_for_c = True
        if c.sub_category is not None and not sub_conflict and not has_sub_match:
            norm_sub = _normalized_value(c.sub_category)
            raw_sub = c.sub_category.strip().lower()
            has_equiv = (
                (c.category, norm_sub) in SUBCATEGORY_EQUIVALENTS
                or (c.category, raw_sub) in SUBCATEGORY_EQUIVALENTS
            )
            if has_equiv and (c.category, "subcategory_equivalent", norm_sub) not in applied:
                if "subcategory_equivalent" not in allowed_actions:
                    allowed_actions.append("subcategory_equivalent")
                added_for_c = True

        # Fallback if exact sub+color+mat combination still blocks (e.g. matching sub_category items have wrong color AND wrong material)
        if not added_for_c:
            if c.color is not None and not color_conflict:
                norm_col = _normalized_value(c.color)
                if norm_col in RELAX_COLOR_FAMILIES and (c.category, "color_family", norm_col) not in applied:
                    if "color_family" not in allowed_actions:
                        allowed_actions.append("color_family")
                    added_for_c = True
            if c.material is not None and (c.category, "material_relax", _normalized_value(c.material)) not in applied:
                if "material_relax" not in allowed_actions:
                    allowed_actions.append("material_relax")
                added_for_c = True
            if c.sub_category is not None and not sub_conflict:
                norm_sub = _normalized_value(c.sub_category)
                raw_sub = c.sub_category.strip().lower()
                has_equiv = (
                    (c.category, norm_sub) in SUBCATEGORY_EQUIVALENTS
                    or (c.category, raw_sub) in SUBCATEGORY_EQUIVALENTS
                )
                if has_equiv and (c.category, "subcategory_equivalent", norm_sub) not in applied:
                    if "subcategory_equivalent" not in allowed_actions:
                        allowed_actions.append("subcategory_equivalent")
                    added_for_c = True

        if added_for_c:
            bottleneck_slots.append(slot_name)
            blocked_constraints.append(c)

    if not bottleneck_slots or not allowed_actions:
        return None

    return RelaxationRequest(
        issue_code="CONSTRAINT_UNSATISFIED",
        bottleneck_slots=list(dict.fromkeys(bottleneck_slots)),
        blocked_constraints=blocked_constraints,
        allowed_actions=allowed_actions,
        reason_vi="Tủ đồ chưa có món khớp chính xác đồng thời mọi thuộc tính yêu cầu, đề xuất nới lỏng màu sắc hoặc kiểu tương đương.",
    )


def _balanced_product(pools: list[list[OutfitItemSlot]]) -> list[list[OutfitItemSlot]]:
    """Bijective diagonal enumeration; early budgets visit every category pool."""
    from math import prod
    if any(not pool for pool in pools):
        return []
    cores: list[list[OutfitItemSlot]] = []
    for index in range(prod(len(pool) for pool in pools)):
        remaining, offset, items = index, 0, []
        for pool in pools:
            position = (remaining % len(pool) + offset) % len(pool)
            remaining //= len(pool)
            offset += position
            items.append(pool[position])
        cores.append(items)
    return cores


def _with_balanced_layers(cores: list[list[OutfitItemSlot]], outerwear: list[OutfitItemSlot],
                          accessories: list[OutfitItemSlot], limit: int) -> list[list[OutfitItemSlot]]:
    variants = [[]] + [[item] for item in outerwear] + [[item] for item in accessories]
    variants += [[outer, accessory] for outer in outerwear for accessory in accessories]
    combos: list[list[OutfitItemSlot]] = []
    for round_index in range(len(variants)):
        for index, core in enumerate(cores):
            if len(combos) >= limit:
                return combos
            combos.append(core + variants[(index + round_index) % len(variants)])
    return combos


def _generate_top_bottom_combos(
    tops: list[OutfitItemSlot], bottoms: list[OutfitItemSlot], footwear: list[OutfitItemSlot],
    outerwear: list[OutfitItemSlot], accessories: list[OutfitItemSlot], limit: int,
) -> list[list[OutfitItemSlot]]:
    return _with_balanced_layers(_balanced_product([tops, bottoms, footwear]), outerwear, accessories, limit)


def _generate_dress_combos(
    dresses: list[OutfitItemSlot], footwear: list[OutfitItemSlot],
    outerwear: list[OutfitItemSlot], accessories: list[OutfitItemSlot], limit: int,
) -> list[list[OutfitItemSlot]]:
    return _with_balanced_layers(_balanced_product([dresses, footwear]), outerwear, accessories, limit)


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
    active_relaxations: Sequence[RelaxationStep] | None = None,
    critique: CritiqueSignal | None = None,
) -> tuple[list[EvaluatedOutfit], list[str]]:
    """Score every combination, apply deterministic tie-breaking with recent wear data, and return top-k."""
    evaluated_outfits: list[EvaluatedOutfit] = []
    all_warnings: list[str] = []

    soft_avoid_ids = set(critique.soft_avoid_item_ids) if critique else set()
    req_func_tags = {t.lower().strip() for t in critique.require_functional_tags} if critique else set()

    for combo in combinations:
        if context is not None and not outfit_satisfies_explicit_constraints(
            combo, context, active_relaxations=active_relaxations
        ):
            continue
        combo_id = "+".join(item.item_id for item in combo)
        score, component_scores, warnings = calculate_composite_fashion_score(combo, context)
        all_warnings.extend(warnings)

        aesthetic_score = component_scores.get("aesthetic_score", score)
        if context is not None:
            from app.agents.context_scoring import (
                calculate_context_composite_score,
                calculate_functional_fit,
                calculate_weather_comfort_fit,
            )

            shortlist_score, _ = calculate_context_composite_score(
                formality_fit=component_scores["formality_score"],
                weather_comfort_fit=calculate_weather_comfort_fit(combo, context.weather_condition, context.environment),
                functional_fit=calculate_functional_fit(combo, context.target_functional_tags),
                aesthetic_score=aesthetic_score,
                personal_fit=0.5,
                weight_profile=context.weight_profile,
            )
            if soft_avoid_ids:
                avoid_hits = sum(1 for item in combo if item.item_id in soft_avoid_ids)
                if avoid_hits:
                    shortlist_score = max(0.0, shortlist_score - 0.15 * avoid_hits)
            if req_func_tags:
                combo_flags = {f.lower().strip() for item in combo for f in item.functional_flags}
                if req_func_tags & combo_flags:
                    shortlist_score = min(1.0, shortlist_score + 0.10)
            component_scores["context_shortlist_score"] = round(shortlist_score, 4)
        evaluated = EvaluatedOutfit(
            items=combo,
            fashion_score=aesthetic_score,
            component_scores=component_scores,
            combination_id=combo_id,
        )
        evaluated_outfits.append(evaluated)

    # Sort deterministically using tie-breaker key:
    # (-fashion_score, -weather_score, recent_wear_count, combination_id)
    # recent_wear_count counts items worn within recent_window_hours using last_worn_at
    evaluated_outfits.sort(
        key=lambda o: ((-o.component_scores["context_shortlist_score"],) if context is not None else ()) + outfit_tie_breaker_key(
            o,
            recent_wear_count=count_recently_worn_items(
                o.items,
                reference_time=reference_time,
                recent_window_hours=recent_window_hours,
            ),
        )
    )

    unique_warnings = list(dict.fromkeys(all_warnings))
    from app.agents.outfit_diversity import core_signature

    filtered_for_critique = evaluated_outfits
    if soft_avoid_ids:
        non_avoided = [
            o for o in filtered_for_critique if not any(item.item_id in soft_avoid_ids for item in o.items)
        ]
        if non_avoided:
            filtered_for_critique = non_avoided
    if req_func_tags:
        functional_matched = [
            o
            for o in filtered_for_critique
            if req_func_tags & {f.lower().strip() for item in o.items for f in item.functional_flags}
        ]
        if functional_matched:
            filtered_for_critique = functional_matched

    unique_outfits: list[EvaluatedOutfit] = []
    seen: set[frozenset[str]] = set()
    for outfit in filtered_for_critique:
        signature = core_signature(outfit.items)
        if signature not in seen:
            seen.add(signature)
            unique_outfits.append(outfit)

    return unique_outfits[:top_k], unique_warnings


def fashion_agent_node(state: StylistGraphState) -> dict[str, Any]:
    """LangGraph node execution function for the Fashion Agent.

    Consumes candidate_pool, generates combinations, scores them,
    and populates evaluated_outfits (or emits a RelaxationRequest on bottlenecks).
    """
    context = state.get("context")
    candidate_pool = state.get("candidate_pool", {})

    # If clarification is requested or context is missing, return empty evaluated_outfits
    if context is None or context.needs_clarification:
        return {"evaluated_outfits": []}

    existing_errors = list(state.get("errors", []))
    existing_warnings = list(state.get("warnings", []))
    existing_trace = list(state.get("agent_trace", []))
    enable_loops = is_relaxation_loop_enabled(state)
    relaxation_round = int(state.get("relaxation_round", 0))
    active_relaxations = list(state.get("active_relaxations", []))
    critique = state.get("critique")

    combinations = generate_outfit_combinations(candidate_pool)

    if not combinations:
        if enable_loops:
            relax_req = diagnose_bottleneck(
                candidate_pool,
                [],
                context,
                relaxation_round,
                active_relaxations=active_relaxations,
            )
            if relax_req is not None:
                trace_event = AgentTraceEvent(
                    round=relaxation_round,
                    sender="fashion",
                    receiver="wardrobe",
                    event_type="RELAXATION_REQUESTED",
                    summary_vi=relax_req.reason_vi,
                )
                return {
                    "evaluated_outfits": [],
                    "relaxation_request": relax_req,
                    "critique": None,
                    "agent_trace": existing_trace + [trace_event],
                }
        logger.warning("No complete combinations from candidate pool: %s", {k: len(v) for k, v in candidate_pool.items()})
        return {
            "evaluated_outfits": [],
            "relaxation_request": None,
            "critique": None,
            "errors": existing_errors + [NO_COMPLETE_OUTFIT_ERROR],
            "warnings": existing_warnings + [NO_COMPLETE_OUTFIT_WARNING],
        }

    ref_time = state.get("reference_time")
    top_evaluated, warnings = evaluate_and_rank_combinations(
        combinations,
        context,
        top_k=MAX_EVALUATED_OUTFITS,
        reference_time=ref_time,
        active_relaxations=active_relaxations,
        critique=critique,
    )

    if not top_evaluated:
        if enable_loops:
            relax_req = diagnose_bottleneck(
                candidate_pool,
                combinations,
                context,
                relaxation_round,
                active_relaxations=active_relaxations,
            )
            if relax_req is not None:
                trace_event = AgentTraceEvent(
                    round=relaxation_round,
                    sender="fashion",
                    receiver="wardrobe",
                    event_type="RELAXATION_REQUESTED",
                    summary_vi=relax_req.reason_vi,
                )
                return {
                    "evaluated_outfits": [],
                    "relaxation_request": relax_req,
                    "critique": None,
                    "agent_trace": existing_trace + [trace_event],
                }
        logger.warning("0 evaluated out of %d combos", len(combinations))
        return {
            "evaluated_outfits": [],
            "relaxation_request": None,
            "critique": None,
            "errors": existing_errors + [NO_COMPLETE_OUTFIT_ERROR],
            "warnings": existing_warnings + [NO_COMPLETE_OUTFIT_WARNING],
        }

    trace_event = AgentTraceEvent(
        round=relaxation_round,
        sender="fashion",
        receiver="personalization",
        event_type="EVALUATED_OUTFITS_PRODUCED",
        summary_vi=f"Đã chấm điểm và lọc ra {len(top_evaluated)} bộ trang phục ứng viên.",
    )
    return {
        "evaluated_outfits": top_evaluated,
        "warnings": existing_warnings + warnings,
        "relaxation_request": None,
        "critique": None,
        "agent_trace": existing_trace + [trace_event],
    }
