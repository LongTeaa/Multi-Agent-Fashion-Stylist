"""Tier-1 garment profile semantics shared by ingestion, editing and scoring.

The stored profile (``silhouette_level`` 1-5, ``length``) is authoritative once it
exists: a value the user confirmed is never re-guessed from free text. Heuristics
here only fill genuinely missing data.

Length is category-aware. ``cropped | waist | hip | long`` describe where a top or
outer layer ends on the torso. For bottoms and dresses only two readings carry
proportion meaning (short vs. full length), so ``waist``/``hip`` on those
categories is treated as "not specified" and inferred from the garment type.
Footwear and accessories have no proportion length.
"""

from __future__ import annotations

from app.models.entities import VALID_FUNCTIONAL_FLAGS, VALID_LENGTH_VALUES, WardrobeCategory

TORSO_CATEGORIES: frozenset[str] = frozenset({WardrobeCategory.TOP.value, WardrobeCategory.OUTERWEAR.value})
FULL_LENGTH_CATEGORIES: frozenset[str] = frozenset({WardrobeCategory.BOTTOM.value, WardrobeCategory.DRESS.value})
FULL_LENGTH_VALUES: frozenset[str] = frozenset({"cropped", "long"})

_SHORT_GARMENT_KEYWORDS: tuple[str, ...] = (
    "short",  # shorts, short skirt
    "mini",
    "skort",
    "bermuda",
    "capri",
    "cropped",
    "quần đùi",
    "quần short",
    "váy ngắn",
)
_LONG_OUTER_KEYWORDS: tuple[str, ...] = ("trench", "overcoat", "long_coat", "long coat", "maxi", "măng tô")
_CROPPED_TORSO_KEYWORDS: tuple[str, ...] = ("crop", "bolero", "lửng")

_SILHOUETTE_KEYWORDS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (5, ("oversized", "oversize", "baggy")),
    (4, ("relaxed", "loose", "wide", "boxy", "hoodie", "ống rộng", "dáng rộng")),
    (1, ("skinny", "tight", "bodycon", "bó sát")),
    (2, ("slim", "fitted", "ôm")),
)

# Common free-form flags produced before the taxonomy existed.
FUNCTIONAL_FLAG_ALIASES: dict[str, str] = {
    "waterproof": "water_resistant",
    "water-resistant": "water_resistant",
    "water resistant": "water_resistant",
    "rainproof": "water_resistant",
    "breathable": "light",
    "lightweight": "light",
    "stretch": "movement",
    "stretchy": "movement",
    "athletic": "sport",
    "activewear": "sport",
    "office": "work",
    "formal_work": "work",
    "uv": "sun",
    "uv_protection": "sun",
    "sun_protection": "sun",
    "insulated": "heavy",
    "warm": "heavy",
    "windproof": "protection",
}


def _text(*parts: str | None) -> str:
    return " ".join(part.lower().strip() for part in parts if part)


def infer_silhouette_level(fit: str | None, sub_category: str | None = None, name: str | None = None) -> int:
    """Best-effort 1-5 silhouette from free text; 3 (regular) when nothing matches."""
    text = _text(fit, sub_category, name)
    for level, keywords in _SILHOUETTE_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return level
    return 3


def default_length(category: str, sub_category: str | None = None, name: str | None = None) -> str:
    """Length to store when the vision model or user gave none."""
    text = _text(sub_category, name)
    if category in FULL_LENGTH_CATEGORIES:
        return "cropped" if any(keyword in text for keyword in _SHORT_GARMENT_KEYWORDS) else "long"
    if category in TORSO_CATEGORIES:
        if any(keyword in text for keyword in _LONG_OUTER_KEYWORDS):
            return "long"
        if any(keyword in text for keyword in _CROPPED_TORSO_KEYWORDS):
            return "cropped"
    return "hip"


def effective_length(
    category: str,
    stored_length: str | None,
    sub_category: str | None = None,
    name: str | None = None,
) -> str | None:
    """Length that carries proportion meaning for scoring, or None when irrelevant."""
    if category not in TORSO_CATEGORIES and category not in FULL_LENGTH_CATEGORIES:
        return None
    value = (stored_length or "").lower().strip()
    if category in FULL_LENGTH_CATEGORIES:
        return value if value in FULL_LENGTH_VALUES else default_length(category, sub_category, name)
    return value if value in VALID_LENGTH_VALUES else default_length(category, sub_category, name)


def normalize_functional_flags(flags: list[str] | None) -> tuple[list[str], list[str]]:
    """Map flags onto the canonical taxonomy.

    Returns ``(canonical_flags, unrecognized)`` in first-seen order, without duplicates.
    """
    canonical: list[str] = []
    unrecognized: list[str] = []
    for raw in flags or []:
        value = str(raw).strip().lower()
        if not value:
            continue
        value = FUNCTIONAL_FLAG_ALIASES.get(value, value)
        target = canonical if value in VALID_FUNCTIONAL_FLAGS else unrecognized
        if value not in target:
            target.append(value)
    return canonical, unrecognized
