from __future__ import annotations

from datetime import datetime
import logging
from typing import Any
from sqlmodel import Session, select

from app.agents.state import (
    OutfitItemSlot,
    RankedOutfit,
    StylistContext,
    StylistGraphState,
)
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

logger = logging.getLogger(__name__)

# Constants & Error Codes
COORDINATOR_RULE_VERSION = "coordinator-v1.0"
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

def generate_grounded_explanation_vi(
    outfit: RankedOutfit,
    context: StylistContext,
) -> str:
    """Generates a 100% deterministic, grounded Vietnamese explanation for a selected outfit.
    
    Strict Invariants:
    - References ONLY canonical items present in this specific outfit.
    - Never hallucinates external garments, colors, or materials.
    - Synthesizes normalized context attributes (occasion, weather, time).
    - Reflects applied preferences if present.
    """
    items_by_role: dict[OutfitSlotRole, OutfitItemSlot] = {
        item.slot_role: item for item in outfit.items
    }

    # Bilingual context normalization
    occasion_map = {
        "cafe": "đi cà phê",
        "work": "đi làm công sở",
        "party": "dự tiệc",
        "date": "hẹn hò",
        "casual": "dạo phố thường ngày",
        "formal": "sự kiện trang trọng",
    }
    occasion_str = occasion_map.get(
        context.occasion.lower() if context.occasion else "",
        context.occasion or "hoạt động thường ngày",
    )

    weather_map = {
        "cool": "thời tiết mát mẻ",
        "warm": "thời tiết ấm áp",
        "hot": "thời tiết nóng",
        "cold": "thời tiết se lạnh",
        "rainy": "thời tiết mưa",
    }
    weather_str = weather_map.get(
        context.weather_condition.lower() if context.weather_condition else "",
        context.weather_condition or "thời tiết dễ chịu",
    )

    time_map = {
        "morning": "buổi sáng",
        "afternoon": "buổi chiều",
        "evening": "buổi tối",
        "night": "buổi đêm",
    }
    time_str = time_map.get(
        context.time_of_day.lower() if context.time_of_day else "",
        context.time_of_day or "trong ngày",
    )

    # Core garment phrasing strictly referencing outfit items
    garment_parts: list[str] = []
    if OutfitSlotRole.DRESS in items_by_role:
        dress = items_by_role[OutfitSlotRole.DRESS]
        garment_parts.append(f"đầm [{dress.name}]")
    else:
        top = items_by_role[OutfitSlotRole.TOP]
        bottom = items_by_role[OutfitSlotRole.BOTTOM]
        garment_parts.append(f"sự kết hợp giữa [{top.name}] và [{bottom.name}]")

    footwear = items_by_role[OutfitSlotRole.FOOTWEAR]
    garment_parts.append(f"đi kèm [{footwear.name}]")

    if OutfitSlotRole.OUTERWEAR in items_by_role:
        outer = items_by_role[OutfitSlotRole.OUTERWEAR]
        garment_parts.append(f"khoác thêm [{outer.name}]")

    if OutfitSlotRole.ACCESSORY in items_by_role:
        acc = items_by_role[OutfitSlotRole.ACCESSORY]
        garment_parts.append(f"phối cùng phụ kiện [{acc.name}]")

    composition_str = ", ".join(garment_parts)

    explanation = (
        f"Bộ trang phục lý tưởng cho dịp {occasion_str} vào {time_str} trong {weather_str}. "
        f"Tổng thể tạo nên từ {composition_str}, mang lại diện mạo hài hòa và tự tin."
    )

    # Weave in applied preferences if present and strictly in canonical allowlist
    valid_prefs = [
        p.strip()
        for p in outfit.applied_preferences
        if p.strip() in CANONICAL_PREFERENCE_TAGS
    ]
    if valid_prefs:
        pref_notes = ", ".join(valid_prefs[:2])
        explanation += f" Phù hợp với sở thích cá nhân ({pref_notes})."

    return explanation


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
) -> tuple[bool, list[str]]:
    """Persists OutfitRecommendation and OutfitItem records in a single atomic transaction.
    
    Guarantees:
    - All outfits and their items commit together.
    - If any error occurs, session.rollback() is executed and zero new records remain.
    - outfit_id is assigned only after successful commit.
    """
    persisted_ids: list[str] = []
    temp_records: list[tuple[RankedOutfit, OutfitRecommendation, list[OutfitItem]]] = []

    try:
        temp_outfits: list[tuple[RankedOutfit, OutfitRecommendation]] = []
        for outfit in ranked_outfits:
            outfit_id = new_uuid()
            rec = OutfitRecommendation(
                id=outfit_id,
                user_id=user_id,
                request_id=request_id,
                user_query=user_query,
                context_snapshot=context.model_dump(),
                explanation_vi=outfit.explanation_vi,
                fashion_score=outfit.fashion_score or 0.0,
                personalization_score=outfit.personalization_score or 0.0,
                composite_score=outfit.composite_score,
                rank=outfit.rank,
                is_bookmarked=False,
                rule_version=COORDINATOR_RULE_VERSION,
                created_at=utc_now(),
            )
            session.add(rec)
            temp_outfits.append((outfit, rec))
            persisted_ids.append(outfit_id)

        # Flush recommendations first so FK constraints are satisfied under SQLite FK enforcement
        session.flush()

        for outfit, rec in temp_outfits:
            for item in outfit.items:
                outfit_item = OutfitItem(
                    outfit_id=rec.id,
                    wardrobe_item_id=item.item_id,
                    user_id=user_id,
                    slot_role=item.slot_role,
                )
                session.add(outfit_item)

        session.commit()

        # Update RankedOutfit instances with the committed outfit_id
        for outfit, rec in temp_outfits:
            outfit.outfit_id = rec.id

        return True, persisted_ids

    except Exception as exc:
        session.rollback()
        logger.exception(
            "Atomic persistence failed for user %s, request %s: %s",
            user_id,
            request_id,
            exc,
        )
        for outfit in ranked_outfits:
            outfit.outfit_id = None
        return False, []


# ============================================================================
# 7. LANGGRAPH COORDINATOR NODE EXECUTION
# ============================================================================

def coordinator_node(
    state: StylistGraphState,
    session: Session | None = None,
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
    for outfit in canonical_outfits:
        complete_valid, complete_error = validate_outfit_completeness(outfit.items)
        if not complete_valid:
            logger.error("Outfit completeness check failed for rank %s: %s", outfit.rank, complete_error)
            base_response["errors"] = existing_errors + [GROUNDING_VALIDATION_FAILED]
            return base_response

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
            outfit.explanation_vi = generate_grounded_explanation_vi(outfit, context)

        # 6. Atomic Persistence
        success, persisted_ids = persist_recommendations_atomically(
            db_session,
            user_id=user_id,
            request_id=request_id,
            user_query=user_query,
            context=context,
            ranked_outfits=canonical_outfits,
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
            "warnings": existing_warnings,
        }

    if session is not None:
        return _execute_persistence(session)
    else:
        with Session(get_engine()) as db_session:
            return _execute_persistence(db_session)
