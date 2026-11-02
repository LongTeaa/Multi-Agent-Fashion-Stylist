"""Deterministic diversity over required garments, never invented wardrobe IDs."""
from app.agents.state import OutfitItemSlot
from app.models.entities import OutfitSlotRole


def core_signature(items: list[OutfitItemSlot]) -> frozenset[str]:
    return frozenset(item.item_id for item in items if item.slot_role in {
        OutfitSlotRole.TOP, OutfitSlotRole.BOTTOM, OutfitSlotRole.DRESS, OutfitSlotRole.FOOTWEAR,
    })


def overlap(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 1.0
