from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Sequence

from sqlmodel import Session, select

from app.agents.state import OutfitItemSlot, RankedOutfit
from app.models.entities import (
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    WardrobeItem,
    new_uuid,
    utc_now,
)

logger = logging.getLogger(__name__)

COORDINATOR_RULE_VERSION = "coordinator-v1.0"


class OutfitInvariantError(ValueError):
    """Raised when an outfit violates business or safety invariants."""

    pass


def validate_outfit_invariants(
    session: Session,
    user_id: str,
    items: Sequence[OutfitItemSlot | tuple[str, OutfitSlotRole]],
) -> None:
    """Validate outfit composition invariants:
    1. Slot Cardinality: at most 1 item per core slot (top, bottom, dress, footwear, outerwear).
    2. Branch XOR: (top AND bottom AND NOT dress) XOR (dress AND NOT top AND NOT bottom).
    3. User Isolation & Active Status: all items belong to user, exist, is_active is True, deleted_at is None.
    4. Slot Category Match: item.category matches slot_role.
    """
    if not items:
        raise OutfitInvariantError("An outfit must contain at least one item.")

    normalized_items: list[tuple[str, OutfitSlotRole]] = []
    for it in items:
        if isinstance(it, tuple):
            normalized_items.append(it)
        else:
            normalized_items.append((it.item_id, it.slot_role))

    slot_counts = Counter(slot for _, slot in normalized_items)

    # 1. Slot Cardinality
    for slot in (
        OutfitSlotRole.TOP,
        OutfitSlotRole.BOTTOM,
        OutfitSlotRole.DRESS,
        OutfitSlotRole.FOOTWEAR,
        OutfitSlotRole.OUTERWEAR,
    ):
        if slot_counts[slot] > 1:
            raise OutfitInvariantError(
                f"Duplicate item for slot '{slot}'. At most 1 item allowed per slot."
            )

    # 2. Branch XOR
    has_top = slot_counts[OutfitSlotRole.TOP] == 1
    has_bottom = slot_counts[OutfitSlotRole.BOTTOM] == 1
    has_dress = slot_counts[OutfitSlotRole.DRESS] == 1

    is_two_piece = has_top and has_bottom and not has_dress
    is_dress = has_dress and not has_top and not has_bottom

    if not (is_two_piece or is_dress):
        raise OutfitInvariantError(
            f"Outfit must satisfy branch XOR rule: either (top and bottom) without dress, "
            f"or dress without top/bottom. (top={has_top}, bottom={has_bottom}, dress={has_dress})"
        )

    # 3. Database lookup: active items belonging to user
    item_ids = [item_id for item_id, _ in normalized_items]
    if len(item_ids) != len(set(item_ids)):
        raise OutfitInvariantError("Outfit contains duplicate items.")

    db_items = session.exec(
        select(WardrobeItem).where(WardrobeItem.id.in_(item_ids))
    ).all()
    db_items_by_id = {db_item.id: db_item for db_item in db_items}

    for item_id, slot_role in normalized_items:
        db_item = db_items_by_id.get(item_id)
        if db_item is None:
            raise OutfitInvariantError(f"Wardrobe item '{item_id}' not found.")
        if db_item.user_id != user_id:
            raise OutfitInvariantError(
                f"Wardrobe item '{item_id}' does not belong to user '{user_id}'."
            )
        if not db_item.is_active or db_item.deleted_at is not None:
            raise OutfitInvariantError(
                f"Wardrobe item '{item_id}' is inactive or deleted."
            )
        if db_item.category.value != slot_role.value:
            raise OutfitInvariantError(
                f"Wardrobe item '{item_id}' category '{db_item.category}' does not match slot '{slot_role}'."
            )


def persist_outfit_recommendations(
    session: Session,
    user_id: str,
    request_id: str,
    user_query: str,
    context_snapshot: dict[str, Any],
    ranked_outfits: list[RankedOutfit],
) -> tuple[bool, list[str]]:
    """Persist ranked outfit recommendations and their items atomically with invariant validation."""
    if not ranked_outfits:
        return True, []

    persisted_ids: list[str] = []
    try:
        existing = session.exec(
            select(OutfitRecommendation)
            .where(
                OutfitRecommendation.user_id == user_id,
                OutfitRecommendation.request_id == request_id,
            )
            .order_by(OutfitRecommendation.rank.asc())
        ).all()
        if existing:
            for outfit in ranked_outfits:
                matched = next((e for e in existing if e.rank == outfit.rank), None)
                if matched:
                    outfit.outfit_id = matched.id
            return True, [e.id for e in existing]

        temp_outfits: list[tuple[RankedOutfit, OutfitRecommendation]] = []

        # Validate all outfits before adding any to session
        for outfit in ranked_outfits:
            validate_outfit_invariants(session, user_id, outfit.items)

            outfit_id = new_uuid()
            rec = OutfitRecommendation(
                id=outfit_id,
                user_id=user_id,
                request_id=request_id,
                user_query=user_query,
                context_snapshot=context_snapshot,
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

        for outfit, rec in temp_outfits:
            outfit.outfit_id = rec.id

        return True, persisted_ids

    except Exception as exc:
        session.rollback()
        logger.exception(
            "Atomic outfit persistence failed for user %s, request %s: %s",
            user_id,
            request_id,
            exc,
        )
        for outfit in ranked_outfits:
            outfit.outfit_id = None
        return False, []
