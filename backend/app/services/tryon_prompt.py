from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.models.entities import OutfitSlotRole

_SLOT_ORDER = {
    OutfitSlotRole.TOP: 0,
    OutfitSlotRole.BOTTOM: 1,
    OutfitSlotRole.DRESS: 2,
    OutfitSlotRole.FOOTWEAR: 3,
    OutfitSlotRole.OUTERWEAR: 4,
    OutfitSlotRole.ACCESSORY: 5,
}
_OMITTED_VALUES = frozenset(
    {"", "unknown", "unspecified", "none", "n/a", "null", "không xác định"}
)


@dataclass(frozen=True)
class LookbookPromptItem:
    """Confirmed metadata for one persisted outfit item."""

    slot: OutfitSlotRole
    sub_category: str
    primary_color: str
    secondary_color: str | None = None
    pattern: str | None = None
    material: str | None = None
    style: str | None = None
    fit: str | None = None


def _usable(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized.casefold() in _OMITTED_VALUES:
        return None
    return normalized


def _describe_item(item: LookbookPromptItem) -> str:
    sub_category = _usable(item.sub_category) or "garment"
    parts = [f"{item.slot.value}: {sub_category}"]
    fields = (
        ("primary color", item.primary_color),
        ("secondary color", item.secondary_color),
        ("pattern", item.pattern),
        ("material", item.material),
        ("style", item.style),
        ("fit", item.fit),
    )
    for label, raw_value in fields:
        value = _usable(raw_value)
        if value is not None:
            parts.append(f"{label}: {value}")
    return "; ".join(parts)


def build_lookbook_prompt(items: Iterable[LookbookPromptItem]) -> str:
    """Build a null-safe prompt grounded only in confirmed outfit metadata."""

    ordered_items = sorted(tuple(items), key=lambda item: _SLOT_ORDER[item.slot])
    if not 2 <= len(ordered_items) <= 5:
        raise ValueError("A lookbook prompt requires 2 to 5 outfit items.")

    item_lines = "\n".join(f"- {_describe_item(item)}" for item in ordered_items)
    return (
        "Create an illustrative fashion lookbook on a standard adult mannequin. "
        "Use a full-length catalog composition, natural proportions, soft studio lighting, "
        "and a neutral background. Show exactly the listed garments, with no added garments, "
        "jewelry, bags, hats, or props. Do not infer or add brand names or logos. "
        "Do not imply accurate sizing, fit, or drape.\n"
        f"Outfit items:\n{item_lines}"
    )
