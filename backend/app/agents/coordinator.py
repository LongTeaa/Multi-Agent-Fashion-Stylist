from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
import logging
from typing import Any
from sqlmodel import Session, select

from app.agents.state import (
    AgentTraceEvent,
    ConflictNote,
    CritiqueSignal,
    OutfitItemSlot,
    RankedOutfit,
    RelaxationStep,
    StylistContext,
    StylistGraphState,
)
from app.agents.fashion_agent import (
    _normalized_value,
    outfit_satisfies_explicit_constraints,
)
from app.agents.fashion_scoring import count_recently_worn_items
from app.core.database import get_engine
from app.models.entities import (
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    WardrobeCategory,
    WardrobeItem,
    new_uuid,
    utc_now,
)
from app.services.outfit_persistence import COORDINATOR_RULE_VERSION, persist_outfit_recommendations

logger = logging.getLogger(__name__)

# Constants & Error Codes
COORDINATOR_STATE_INVALID = "COORDINATOR_STATE_INVALID"
GROUNDING_VALIDATION_FAILED = "GROUNDING_VALIDATION_FAILED"
COORDINATOR_PERSISTENCE_ERROR = "COORDINATOR_PERSISTENCE_ERROR"


ROLE_TO_CATEGORY: dict[OutfitSlotRole, WardrobeCategory] = {
    OutfitSlotRole.TOP: WardrobeCategory.TOP,
    OutfitSlotRole.BOTTOM: WardrobeCategory.BOTTOM,
    OutfitSlotRole.DRESS: WardrobeCategory.DRESS,
    OutfitSlotRole.FOOTWEAR: WardrobeCategory.FOOTWEAR,
    OutfitSlotRole.OUTERWEAR: WardrobeCategory.OUTERWEAR,
    OutfitSlotRole.ACCESSORY: WardrobeCategory.ACCESSORY,
}

from app.agents.personalization_agent import PALETTE_VI_MAP, PRIORITY_VI_MAP
from app.services.profile_service import COLOR_PALETTES, PRIORITIES, STYLES

CANONICAL_PREFERENCE_TAGS: frozenset[str] = frozenset(
    [f"Phù hợp phong cách {s} đã chọn" for s in STYLES]
    + [f"Bảng màu {PALETTE_VI_MAP[p]} theo sở thích" for p in COLOR_PALETTES if p in PALETTE_VI_MAP]
    + [PRIORITY_VI_MAP[p] for p in PRIORITIES if p in PRIORITY_VI_MAP]
)


# ============================================================================
# 1. INPUT STATE PRE-FLIGHT VALIDATION
# ============================================================================

def validate_coordinator_input_state(state: StylistGraphState) -> tuple[bool, str | None]:
    """Validates that all mandatory fields for the Coordinator exist and are non-empty.

    Prevents database constraint violations by verifying non-null database fields:
    request_id, user_id, user_query, context snapshot, candidate_pool, ranked_outfits,
    and non-null scores on each ranked outfit.
    """
    user_id = state.get("user_id")
    if not user_id or not isinstance(user_id, str):
        return False, "Missing or invalid 'user_id'"

    request_id = state.get("request_id")
    if not request_id or not isinstance(request_id, str):
        return False, "Missing or invalid 'request_id'"

    user_query = state.get("user_query")
    if not user_query or not isinstance(user_query, str):
        return False, "Missing or invalid 'user_query'"

    context = state.get("context")
    if not context or not isinstance(context, StylistContext):
        return False, "Missing or invalid 'context'"

    candidate_pool = state.get("candidate_pool")
    if candidate_pool is None or not isinstance(candidate_pool, dict):
        return False, "Missing or invalid 'candidate_pool'"

    ranked_outfits = state.get("ranked_outfits")
    if ranked_outfits is None or not isinstance(ranked_outfits, list) or len(ranked_outfits) == 0:
        return False, "Missing or empty 'ranked_outfits'"

    if len(ranked_outfits) > 3:
        return False, f"Number of ranked outfits ({len(ranked_outfits)}) exceeds maximum allowed (3)"

    # Enforce strictly consecutive unique ranks: [1], [1, 2], or [1, 2, 3]
    ranks = [outfit.rank for outfit in ranked_outfits]
    expected_ranks = list(range(1, len(ranked_outfits) + 1))
    if ranks != expected_ranks:
        return (
            False,
            f"Outfit ranks must be strictly consecutive starting from 1 {expected_ranks}, got {ranks}",
        )

    # Score and rank validity checks per outfit
    for outfit in ranked_outfits:
        if outfit.fashion_score is None or not (0.0 <= outfit.fashion_score <= 1.0):
            return False, f"Outfit rank {outfit.rank} has invalid fashion_score"
        if outfit.personalization_score is None or not (0.0 <= outfit.personalization_score <= 1.0):
            return False, f"Outfit rank {outfit.rank} has invalid personalization_score"
        if outfit.composite_score is None or not (0.0 <= outfit.composite_score <= 1.0):
            return False, f"Outfit rank {outfit.rank} has invalid composite_score"
        if not outfit.items or len(outfit.items) < 2:
            return False, f"Outfit rank {outfit.rank} has insufficient items"

    return True, None


# ============================================================================
# 2. CANDIDATE POOL CANONICALIZATION & GROUNDING
# ============================================================================

def canonicalize_and_validate_pool(
    ranked_outfits: list[RankedOutfit],
    candidate_pool: dict[str, list[OutfitItemSlot]],
) -> tuple[bool, list[RankedOutfit], str | None]:
    """Validates that every item slot exists in the candidate pool and canonicalizes item slots.

    Replaces each outfit item with the genuine OutfitItemSlot from the pool by (item_id, slot_role).
    Guarantees upstream nodes cannot mutate item properties (name, color, material) to tamper with
    explanations or database persistence.
    """
    # Build lookup table: (item_id, slot_role) -> OutfitItemSlot
    pool_lookup: dict[tuple[str, OutfitSlotRole], OutfitItemSlot] = {}
    for slot_list in candidate_pool.values():
        for slot in slot_list:
            pool_lookup[(slot.item_id, slot.slot_role)] = slot

    canonical_outfits: list[RankedOutfit] = []

    for outfit in ranked_outfits:
        canonical_items: list[OutfitItemSlot] = []
        for item in outfit.items:
            key = (item.item_id, item.slot_role)
            if key not in pool_lookup:
                return (
                    False,
                    [],
                    f"Item '{item.item_id}' with role '{item.slot_role}' is not in candidate pool",
                )
            # Use genuine, canonical slot from pool
            canonical_items.append(pool_lookup[key])

        # Create updated copy with canonical items
        updated_outfit = outfit.model_copy(update={"items": canonical_items})
        canonical_outfits.append(updated_outfit)

    return True, canonical_outfits, None


# ============================================================================
# 3. DATABASE ACTIVE OWNERSHIP VALIDATOR
# ============================================================================

def validate_database_active_ownership(
    session: Session,
    user_id: str,
    items: set[str] | list[OutfitItemSlot],
) -> tuple[bool, str | None]:
    """Verifies that all item IDs exist in the database, belong to user_id, are active, not deleted,
    and have their database category matching the outfit slot role."""
    if not items:
        return False, "No items to validate against database"

    item_slots: list[OutfitItemSlot] = []
    item_ids: set[str] = set()
    for it in items:
        if isinstance(it, OutfitItemSlot):
            item_slots.append(it)
            item_ids.add(it.item_id)
        else:
            item_ids.add(it)

    stmt = select(WardrobeItem).where(
        WardrobeItem.id.in_(item_ids),
        WardrobeItem.user_id == user_id,
        WardrobeItem.is_active.is_(True),
        WardrobeItem.deleted_at.is_(None),
    )
    rows = session.exec(stmt).all()
    found_map = {row.id: row for row in rows}
    missing_ids = item_ids - set(found_map.keys())

    if missing_ids:
        return (
            False,
            f"Items {sorted(missing_ids)} do not exist as active, un-deleted items owned by user '{user_id}'",
        )

    # Cross-verify database category matches the slot role
    for slot in item_slots:
        db_item = found_map[slot.item_id]
        expected_cat = ROLE_TO_CATEGORY.get(slot.slot_role)
        if expected_cat is not None and db_item.category != expected_cat:
            return (
                False,
                f"Item '{slot.item_id}' category in database ({db_item.category}) does not match outfit slot role ({slot.slot_role})",
            )

    return True, None


# ============================================================================
# 4. OUTFIT COMPLETENESS & MUTUAL EXCLUSIVITY INVARIANT
# ============================================================================

def validate_outfit_completeness(
    items: list[OutfitItemSlot],
) -> tuple[bool, str | None]:
    """Enforces strict outfit completeness and slot cardinality invariants.

    Invariants:
    - Footwear count MUST BE exactly 1.
    - Outerwear count <= 1.
    - Accessory count <= 1.
    - Mutually exclusive branches:
        Branch 1 (separates): exactly 1 TOP, exactly 1 BOTTOM, 0 DRESS.
        Branch 2 (one-piece): exactly 1 DRESS, 0 TOP, 0 BOTTOM.
    """
    tops = sum(1 for i in items if i.slot_role == OutfitSlotRole.TOP)
    bottoms = sum(1 for i in items if i.slot_role == OutfitSlotRole.BOTTOM)
    dresses = sum(1 for i in items if i.slot_role == OutfitSlotRole.DRESS)
    footwear = sum(1 for i in items if i.slot_role == OutfitSlotRole.FOOTWEAR)
    outerwear = sum(1 for i in items if i.slot_role == OutfitSlotRole.OUTERWEAR)
    accessories = sum(1 for i in items if i.slot_role == OutfitSlotRole.ACCESSORY)

    if footwear != 1:
        return False, f"Outfit must have exactly 1 footwear, found {footwear}"

    if outerwear > 1:
        return False, f"Outfit cannot have more than 1 outerwear, found {outerwear}"

    if accessories > 1:
        return False, f"Outfit cannot have more than 1 accessory, found {accessories}"

    is_branch_1 = (tops == 1 and bottoms == 1 and dresses == 0)
    is_branch_2 = (dresses == 1 and tops == 0 and bottoms == 0)

    if not (is_branch_1 or is_branch_2):
        if dresses > 0 and (tops > 0 or bottoms > 0):
            return False, "Outfit violates mutual exclusivity: cannot combine dress with top or bottom"
        if dresses == 0 and (tops == 0 or bottoms == 0):
            return False, "Outfit incomplete: missing required top or bottom"
        return False, f"Invalid outfit slot configuration: tops={tops}, bottoms={bottoms}, dresses={dresses}"

    return True, None


# ============================================================================
# 5. DETERMINISTIC GROUNDED VIETNAMESE EXPLANATION GENERATOR
# ============================================================================

_FORBIDDEN_EXPLANATION_PHRASES: tuple[str, ...] = (
    "lý tưởng",
    "rất phù hợp",
    "thoáng mát",
    "mềm mại",
)


def _validate_grounded_llm_explanation(
    candidate_text: str,
    item_allowed_brackets: list[set[str]],
) -> bool:
    """Verify an LLM-generated explanation references only canonical outfit items and avoids forbidden claims."""
    import re

    cleaned = candidate_text.strip()
    if len(cleaned) < 15 or len(cleaned) > 600:
        return False
    lowered = cleaned.lower()
    if any(forbidden in lowered for forbidden in _FORBIDDEN_EXPLANATION_PHRASES):
        return False

    # Every outfit item must have at least one of its canonical [Name] bracket forms present
    for group in item_allowed_brackets:
        if not any(token in lowered for token in group):
            return False

    # No extra [...] bracketed garment names outside the outfit's allowed brackets may be hallucinated
    found_brackets = {f"[{m.strip().lower()}]" for m in re.findall(r"\[([^\[\]]+)\]", cleaned)}
    all_allowed = set().union(*item_allowed_brackets) if item_allowed_brackets else set()
    if not found_brackets.issubset(all_allowed):
        return False

    return True


def generate_grounded_explanation_vi(
    outfit: RankedOutfit,
    context: StylistContext,
    active_relaxations: Sequence[RelaxationStep] | None = None,
    conflict_notes: Sequence[ConflictNote] | None = None,
    llm_provider: Any = None,
) -> str:
    """Generates a grounded Vietnamese explanation for a selected outfit.

    Uses grounded LLM synthesis when an LLM explanation provider is supplied and passes
    strict anti-hallucination validation; otherwise falls back to 100% deterministic template synthesis.

    Strict Invariants:
    - References ONLY canonical items present in this specific outfit.
    - Never hallucinates external garments, colors, or materials.
    - Explains formality alignment without inferring material performance.
    - Reflects applied preferences if present.
    """
    colors = {"white": "trắng", "black": "đen", "grey": "xám", "gray": "xám",
              "navy": "xanh navy", "navy blue": "xanh navy", "blue": "xanh dương",
              "brown": "nâu", "beige": "be", "green": "xanh lá", "red": "đỏ"}
    from app.services.garment_taxonomy import classify, normalize

    parts: list[str] = []
    item_allowed_brackets: list[set[str]] = []
    for item in outfit.items:
        _, garment = classify(item.category, item.name)
        name = garment.label if garment else item.name
        color = item.primary_color.strip().lower()
        color_label = colors.get(color, color)
        color_in_name = f" {normalize(color_label)} " in f" {normalize(name)} "
        color_note = f" màu {color_label}" if color and color != "unknown" and not color_in_name else ""
        allowed_for_item = {f"[{name.strip().lower()}]", f"[{item.name.strip().lower()}]"}
        if item.sub_category:
            _, sub_garment = classify(item.category, item.sub_category)
            if sub_garment:
                allowed_for_item.add(f"[{sub_garment.label.strip().lower()}]")
        if color_label and color_label != "unknown":
            allowed_for_item.add(f"[{name.strip().lower()} {color_label}]")
        # Also allow base garment name with trailing color stripped (including khaki/be/kem)
        for col_vi in (*colors.values(), "khaki", "kaki", "kem"):
            raw_lower = item.name.strip().lower()
            if raw_lower.endswith(f" {col_vi}"):
                base_only = raw_lower[: -len(col_vi)].strip()
                if base_only:
                    allowed_for_item.add(f"[{base_only}]")
        item_allowed_brackets.append(allowed_for_item)
        parts.append(f"[{name}]{color_note}")
    explanation = "Phối " + ", ".join(parts) + "."
    major = [item for item in outfit.items if item.slot_role != OutfitSlotRole.ACCESSORY]
    levels = [item.formality_level for item in major]
    target = context.target_formality_range
    if levels and len(target) == 2:
        if all(target[0] <= level <= target[1] for level in levels):
            explanation += " Các món chính đều nằm trong mức trang trọng bạn cần."
        else:
            explanation += " Mức trang trọng giữa các món chưa hoàn toàn đồng đều với nhu cầu."
    low_score_note = ""
    if outfit.composite_score < 0.65:
        low_score_note = f"Độ phù hợp ở mức vừa phải ({round(outfit.composite_score * 100)}%); bạn nên cân nhắc theo nhu cầu."
        explanation += f" {low_score_note}"
    valid_prefs = [p.strip() for p in outfit.applied_preferences
                   if p.strip() in CANONICAL_PREFERENCE_TAGS]
    if valid_prefs:
        explanation += " " + "; ".join(valid_prefs[:2]) + "."

    dedup_relax_notes: list[str] = []
    if active_relaxations:
        relax_notes: list[str] = []
        for step in active_relaxations:
            matching_items = [item for item in outfit.items if item.category == step.category]
            if not matching_items:
                continue
            if step.action == "color_family":
                relaxed_cols = {_normalized_value(v) for v in step.relaxed_values}
                orig_col = _normalized_value(step.original_value)
                if any(
                    _normalized_value(it.primary_color) in relaxed_cols
                    and _normalized_value(it.primary_color) != orig_col
                    for it in matching_items
                ):
                    relax_notes.append(
                        "Đã linh hoạt chọn màu hiện có trong tủ thay cho màu yêu cầu ban đầu."
                    )
            elif step.action == "subcategory_equivalent":
                relaxed_subs = {_normalized_value(v) for v in step.relaxed_values}
                orig_sub = _normalized_value(step.original_value)
                if any(
                    _normalized_value(it.sub_category) in relaxed_subs
                    and _normalized_value(it.sub_category) != orig_sub
                    for it in matching_items
                ):
                    relax_notes.append(
                        "Đã linh hoạt chọn kiểu dáng tương đương hiện có trong tủ."
                    )
            elif step.action == "material_relax":
                orig_mat = _normalized_value(step.original_value)
                if any(_normalized_value(it.material) != orig_mat for it in matching_items):
                    relax_notes.append(
                        "Đã linh hoạt mở rộng chất liệu có sẵn trong tủ."
                    )
        dedup_relax_notes = list(dict.fromkeys(relax_notes))
        for note in dedup_relax_notes:
            explanation += f" {note}"

    if llm_provider is not None and hasattr(llm_provider, "generate_outfit_explanation"):
        try:
            conflict_strs = [f"{c.description_vi} {c.resolution_vi}" for c in (conflict_notes or ())]
            llm_text = llm_provider.generate_outfit_explanation(
                items_description=parts,
                occasion=context.occasion,
                weather_condition=context.weather_condition,
                target_formality_range=list(context.target_formality_range),
                composite_score=outfit.composite_score,
                applied_preferences=valid_prefs[:2],
                relaxation_notes=dedup_relax_notes,
                conflict_notes=conflict_strs,
            )
            if isinstance(llm_text, str) and _validate_grounded_llm_explanation(llm_text, item_allowed_brackets):
                final_llm = llm_text.strip()
                if not final_llm.endswith("."):
                    final_llm += "."
                if low_score_note and f"{round(outfit.composite_score * 100)}%" not in final_llm:
                    final_llm += f" {low_score_note}"
                for pref in valid_prefs[:2]:
                    if pref not in final_llm:
                        final_llm += f" {pref}."
                for r_note in dedup_relax_notes:
                    if r_note not in final_llm:
                        final_llm += f" {r_note}"
                return final_llm
        except Exception as exc:
            logger.warning("Grounded LLM explanation fallback triggered: %s", exc)

    return explanation


def evaluate_critic_signal(
    canonical_outfits: list[RankedOutfit],
    candidate_pool: dict[str, list[OutfitItemSlot]],
    context: StylistContext,
    reference_time: datetime | None = None,
) -> CritiqueSignal | None:
    """Evaluate top ranked outfits for repetition or functional gaps before DB persistence."""
    if not canonical_outfits:
        return None

    slot_map: dict[WardrobeCategory, str] = {
        WardrobeCategory.TOP: "tops",
        WardrobeCategory.BOTTOM: "bottoms",
        WardrobeCategory.DRESS: "dresses",
        WardrobeCategory.FOOTWEAR: "footwear",
        WardrobeCategory.OUTERWEAR: "outerwear",
        WardrobeCategory.ACCESSORY: "accessories",
    }

    # Rule 1: ALL_RECENTLY_WORN (every top candidate contains at least one item worn within 48h,
    # while the candidate_pool still has an unworn replacement in that same slot).
    if all(
        count_recently_worn_items(outfit.items, reference_time=reference_time, recent_window_hours=48) > 0
        for outfit in canonical_outfits
    ):
        soft_avoid_ids: list[str] = []
        for outfit in canonical_outfits:
            for item in outfit.items:
                if count_recently_worn_items([item], reference_time=reference_time, recent_window_hours=48) == 0:
                    continue
                pool_slot = slot_map.get(item.category, "")
                slot_candidates = candidate_pool.get(pool_slot, [])
                has_unworn_alt = any(
                    cand.item_id != item.item_id
                    and count_recently_worn_items([cand], reference_time=reference_time, recent_window_hours=48) == 0
                    for cand in slot_candidates
                )
                if has_unworn_alt and item.item_id not in soft_avoid_ids:
                    soft_avoid_ids.append(item.item_id)
        if soft_avoid_ids:
            return CritiqueSignal(
                issue_code="ALL_RECENTLY_WORN",
                soft_avoid_item_ids=soft_avoid_ids,
                reason_vi="Cả 3 phương án đầu đều chứa món vừa mặc trong 48h trong khi tủ vẫn còn món chưa mặc.",
            )

    # Rule 2: CONTEXT_GAP (rainy context expects water_resistant, pool has one, top outfits lack it).
    if "water_resistant" in (context.target_functional_tags or []):
        has_water_resistant_in_top = any(
            "water_resistant" in item.functional_flags
            for outfit in canonical_outfits
            for item in outfit.items
        )
        has_water_resistant_in_pool = any(
            "water_resistant" in cand.functional_flags
            for slot_items in candidate_pool.values()
            for cand in slot_items
        )
        if not has_water_resistant_in_top and has_water_resistant_in_pool:
            return CritiqueSignal(
                issue_code="CONTEXT_GAP",
                require_functional_tags=["water_resistant"],
                reason_vi="Thời tiết mưa nhưng các bộ đề xuất chưa tận dụng trang phục chống thấm nước có sẵn trong tủ.",
            )

    return None


# ============================================================================
# 6. ATOMIC TRANSACTION PERSISTENCE
# ============================================================================

def persist_recommendations_atomically(
    session: Session,
    user_id: str,
    request_id: str,
    user_query: str,
    context: StylistContext,
    ranked_outfits: list[RankedOutfit],
    request_location: str | None = None,
    warnings: list[str] | None = None,
    agent_trace: Sequence[AgentTraceEvent] | None = None,
) -> tuple[bool, list[str]]:
    """Persists OutfitRecommendation and OutfitItem records in a single atomic transaction with invariant validation."""
    serialized_trace = [
        t.model_dump() if hasattr(t, "model_dump") else dict(t)
        for t in (agent_trace or ())
    ]
    return persist_outfit_recommendations(
        session=session,
        user_id=user_id,
        request_id=request_id,
        user_query=user_query,
        context_snapshot={
            **context.model_dump(),
            "_request_location": request_location,
            "_warnings": list(warnings or []),
            "_agent_trace": serialized_trace,
        },
        ranked_outfits=ranked_outfits,
    )


# ============================================================================
# 7. LANGGRAPH COORDINATOR NODE EXECUTION
# ============================================================================

def coordinator_node(
    state: StylistGraphState,
    session: Session | None = None,
    llm_provider: Any = None,
) -> dict[str, Any]:
    """LangGraph node execution function for the Coordinator Agent.

    Workflow:
    1. Pre-flight input state validation (all mandatory fields and scores must exist).
    2. Candidate pool canonicalization (lookup and replace with genuine OutfitItemSlots).
    3. Database ownership and active status validation.
    4. Outfit completeness and mutual exclusivity check.
    5. Deterministic grounded Vietnamese explanation generation.
    6. Single-transaction atomic persistence.
    7. Return standardized state updates with feedback cadence placeholders.
    """
    existing_errors = list(state.get("errors", []))
    existing_warnings = list(state.get("warnings", []))

    # Phase boundary defaults (feedback cadence deferred to Phase 5)
    base_response: dict[str, Any] = {
        "grounding_validated": False,
        "recommendation_ids": [],
        "feedback_prompt_eligible": False,
        "feedback_target_outfit_id": None,
        "errors": existing_errors,
        "warnings": existing_warnings,
    }

    # Short-circuit invariant: An error state cannot also produce a successful recommendation payload.
    if existing_errors:
        logger.warning(
            "Coordinator short-circuiting due to existing upstream errors: %s",
            existing_errors,
        )
        return {
            **base_response,
            "ranked_outfits": [],
        }

    # 1. Validate Input State
    state_valid, state_error = validate_coordinator_input_state(state)
    if not state_valid:
        logger.error("Coordinator state invalid: %s", state_error)
        base_response["errors"] = existing_errors + [COORDINATOR_STATE_INVALID]
        return base_response

    user_id = state["user_id"]
    request_id = state["request_id"]
    user_query = state["user_query"]
    context = state["context"]
    candidate_pool = state["candidate_pool"]
    ranked_outfits = state["ranked_outfits"]

    # 2. Candidate Pool Grounding & Canonicalization
    pool_valid, canonical_outfits, pool_error = canonicalize_and_validate_pool(
        ranked_outfits, candidate_pool
    )
    if not pool_valid:
        logger.error("Candidate pool grounding failed: %s", pool_error)
        base_response["errors"] = existing_errors + [GROUNDING_VALIDATION_FAILED]
        return base_response

    # 3. Completeness & Mutual Exclusivity Check
    active_relaxations = list(state.get("active_relaxations", []))
    for outfit in canonical_outfits:
        complete_valid, complete_error = validate_outfit_completeness(outfit.items)
        if not complete_valid:
            logger.error("Outfit completeness check failed for rank %s: %s", outfit.rank, complete_error)
            base_response["errors"] = existing_errors + [GROUNDING_VALIDATION_FAILED]
            return base_response
        if not outfit_satisfies_explicit_constraints(outfit.items, context, active_relaxations):
            logger.error("Outfit rank %s violates explicit query constraints", outfit.rank)
            base_response["errors"] = existing_errors + [GROUNDING_VALIDATION_FAILED]
            return base_response

    # 3.5. Coordinator Critic Evaluation (Loop 2 before persistence)
    conflict_notes = list(state.get("conflict_notes", []))
    existing_trace = list(state.get("agent_trace", []))
    enable_loops = bool(state.get("enable_agent_loops", False))
    critique_round = int(state.get("critique_round", 0))
    previous_ranked_outfits = list(state.get("previous_ranked_outfits", []))

    if enable_loops:
        if critique_round >= 1 and previous_ranked_outfits:
            prev_score = previous_ranked_outfits[0].composite_score
            new_score = canonical_outfits[0].composite_score
            if prev_score - new_score > 0.05:
                canonical_outfits = previous_ranked_outfits
                conflict_notes.append(
                    ConflictNote(
                        conflict_type="CRITIC_KEPT_ORIGINAL",
                        description_vi=(
                            "Đã thử tìm phương án thay thế để tránh lặp đồ nhưng độ phù hợp hoàn cảnh giảm đáng kể."
                        ),
                        resolution_vi="Giữ lại phương án có điểm phù hợp cao nhất ban đầu.",
                    )
                )
        elif critique_round == 0:
            signal = evaluate_critic_signal(
                canonical_outfits,
                candidate_pool,
                context,
                reference_time=state.get("reference_time"),
            )
            if signal is not None:
                reroute_trace = AgentTraceEvent(
                    round=critique_round,
                    sender="coordinator",
                    receiver="fashion",
                    event_type=f"CRITIQUE_{signal.issue_code}",
                    summary_vi=signal.reason_vi,
                )
                return {
                    "coordinator_decision": "reroute_fashion",
                    "critique": signal,
                    "critique_round": critique_round + 1,
                    "previous_ranked_outfits": canonical_outfits,
                    "warnings": existing_warnings,
                    "errors": existing_errors,
                    "conflict_notes": conflict_notes,
                    "agent_trace": existing_trace + [reroute_trace],
                }

    # Collect all item slots across all outfits for comprehensive DB & category validation
    all_item_slots = [
        item for outfit in canonical_outfits for item in outfit.items
    ]

    # 4. Database Ownership & Active Status Validation & Persistence
    def _execute_persistence(db_session: Session) -> dict[str, Any]:
        db_valid, db_error = validate_database_active_ownership(
            db_session, user_id, all_item_slots
        )
        if not db_valid:
            logger.error("Database active ownership check failed: %s", db_error)
            return {
                **base_response,
                "errors": existing_errors + [GROUNDING_VALIDATION_FAILED],
            }

        # 5. Generate Grounded Explanations
        for outfit in canonical_outfits:
            outfit.explanation_vi = generate_grounded_explanation_vi(
                outfit,
                context,
                active_relaxations=active_relaxations,
                conflict_notes=conflict_notes,
                llm_provider=llm_provider,
            )

        approve_trace = AgentTraceEvent(
            round=critique_round,
            sender="coordinator",
            receiver="end",
            event_type="RECOMMENDATIONS_APPROVED",
            summary_vi=f"Đã kiểm định và lưu {len(canonical_outfits)} bộ trang phục vào cơ sở dữ liệu.",
        )
        final_trace = existing_trace + [approve_trace]

        # 6. Atomic Persistence
        success, persisted_ids = persist_recommendations_atomically(
            db_session,
            user_id=user_id,
            request_id=request_id,
            user_query=user_query,
            context=context,
            ranked_outfits=canonical_outfits,
            request_location=state.get("location"),
            warnings=existing_warnings,
            agent_trace=final_trace,
        )

        if not success or not persisted_ids:
            return {
                **base_response,
                "errors": existing_errors + [COORDINATOR_PERSISTENCE_ERROR],
            }

        return {
            "ranked_outfits": canonical_outfits,
            "recommendation_ids": persisted_ids,
            "grounding_validated": True,
            "feedback_prompt_eligible": False,
            "feedback_target_outfit_id": None,
            "coordinator_decision": "approve",
            "critique": None,
            "conflict_notes": conflict_notes,
            "warnings": existing_warnings,
            "agent_trace": final_trace,
        }

    if session is not None:
        return _execute_persistence(session)
    else:
        with Session(get_engine()) as db_session:
            return _execute_persistence(db_session)
