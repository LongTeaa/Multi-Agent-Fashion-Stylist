from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from app.agents.state import EvaluatedOutfit, OutfitItemSlot, StylistContext
from app.models.entities import OutfitSlotRole, WardrobeCategory

# --- 1. TAXONOMY & COLOR FAMILIES ---

COLOR_FAMILIES: dict[str, set[str]] = {
    "neutral": {"white", "black", "grey", "beige", "cream", "khaki", "navy", "brown", "tan"},
    "red": {"red", "burgundy", "pink", "coral"},
    "orange": {"orange", "terracotta"},
    "yellow": {"yellow", "mustard"},
    "green": {"green", "olive", "mint"},
    "blue": {"blue", "light_blue", "denim_blue", "teal", "navy"},
    "purple": {"purple", "lavender"},
}

ANALOGOUS_PAIRS: list[set[str]] = [
    {"red", "orange"},
    {"orange", "yellow"},
    {"yellow", "green"},
    {"green", "blue"},
    {"blue", "purple"},
]

COMPLEMENTARY_PAIRS: list[set[str]] = [
    {"red", "green"},
    {"orange", "blue"},
    {"yellow", "purple"},
]

MAJOR_SLOT_ROLES: set[OutfitSlotRole] = {
    OutfitSlotRole.TOP,
    OutfitSlotRole.BOTTOM,
    OutfitSlotRole.DRESS,
    OutfitSlotRole.FOOTWEAR,
    OutfitSlotRole.OUTERWEAR,
}

STYLE_PAIR_SCORES: dict[tuple[str, str], float] = {
    ("casual", "streetwear"): 0.95,
    ("casual", "minimalist"): 0.95,
    ("smart_casual", "minimalist"): 0.95,
    ("smart_casual", "casual"): 0.95,
    ("smart_casual", "formal"): 0.85,
    ("minimalist", "vintage"): 0.85,
    ("casual", "vintage"): 0.80,
    ("smart_casual", "vintage"): 0.80,
    ("formal", "minimalist"): 0.75,
    ("formal", "casual"): 0.55,
    ("formal", "streetwear"): 0.20,
}


def _get_major_items(items: list[OutfitItemSlot]) -> list[OutfitItemSlot]:
    """Extract major items excluding accessories."""
    return [item for item in items if item.slot_role in MAJOR_SLOT_ROLES]


def _get_color_families(color: str) -> set[str]:
    """Map a canonical color name to its matching color families."""
    c = color.lower().strip()
    families: set[str] = set()
    for family, members in COLOR_FAMILIES.items():
        if c in members:
            families.add(family)
    return families


# --- 2. COLOR SCORING ---

def calculate_color_score(items: list[OutfitItemSlot]) -> float:
    """Calculate deterministic color harmony score according to Section 3.

    Uses primary colors of major items only. Accessories must not count.

    Invariant:
    - 'navy' behaves as a practical neutral for neutral combinations
      and as a blue-family shade for monochromatic evaluation.
    """
    major_items = _get_major_items(items)
    if not major_items:
        return 1.0

    colors = [item.primary_color.lower().strip() for item in major_items if item.primary_color]
    if not colors:
        return 1.0

    distinct_colors = len(set(colors))
    pure_neutrals = {"white", "black", "grey", "beige", "cream", "khaki", "brown", "tan"}
    all_neutrals_with_navy = pure_neutrals | {"navy"}

    # Rule 1: All colors are neutral (navy acts as practical neutral)
    if all(c in all_neutrals_with_navy for c in colors):
        base_score = 1.00

    # Rule 3: One non-neutral family with multiple shades (monochromatic)
    # Spec: "navy MUST behave as a blue-family shade for monochromatic evaluation."
    # E.g. [navy, blue], [navy, light_blue], [blue, denim_blue] -> all shades of blue family
    elif distinct_colors >= 2 and any(
        all(c in (members if fam != "blue" else (members | {"navy"})) for c in colors)
        for fam, members in COLOR_FAMILIES.items()
        if fam != "neutral"
    ):
        base_score = 0.90

    else:
        # Check neutral anchor and non-neutral accent families
        has_pure_neutral = any(c in pure_neutrals for c in colors)
        has_navy = "navy" in colors
        has_neutral_anchor = has_pure_neutral or has_navy

        # Collect accent families for non-neutral items (excluding pure neutrals and navy)
        accent_families: set[str] = set()
        for c in colors:
            if c not in pure_neutrals and c != "navy":
                fams = _get_color_families(c) - {"neutral"}
                accent_families.update(fams)

        # Rule 2: Neutral base plus exactly one accent family
        is_neutral_plus_one_accent = False
        if has_neutral_anchor:
            if has_pure_neutral and not has_navy:
                is_neutral_plus_one_accent = (len(accent_families) == 1)
            elif has_navy and not has_pure_neutral:
                # Navy is the only neutral anchor. If accent_families has 1 family (not blue), navy anchors it.
                # E.g. navy + red -> neutral base + red accent (0.95)
                # Note: navy + blue was already handled by monochromatic check above (0.90)
                if len(accent_families) == 1 and accent_families != {"blue"}:
                    is_neutral_plus_one_accent = True
            elif has_navy and has_pure_neutral:
                # E.g. white + navy + red -> white & navy are neutrals, red is 1 accent -> 0.95
                # E.g. white + navy + blue -> white is neutral, navy & blue are blue accent -> 0.95
                # But white + navy + blue + red has 2 accents (blue and red) -> not 1 accent
                if len(accent_families) == 1:
                    is_neutral_plus_one_accent = True

        if is_neutral_plus_one_accent:
            base_score = 0.95
        else:
            # Determine effective non-neutral families for analogous / complementary checks
            # In multi-color combos, navy can be considered as blue family or neutral anchor
            fams_with_navy_neutral = accent_families
            fams_with_navy_blue = accent_families | ({"blue"} if has_navy else set())

            # Rule 4: Two analogous families
            if any(fams_with_navy_neutral == pair or fams_with_navy_blue == pair for pair in ANALOGOUS_PAIRS):
                base_score = 0.85
            # Rule 5: Two complementary families with at least one neutral anchor
            elif has_neutral_anchor and any(fams_with_navy_neutral == pair or fams_with_navy_blue == pair for pair in COMPLEMENTARY_PAIRS):
                base_score = 0.80
            # Rule 7: Three or more saturated families without a neutral anchor
            elif not has_neutral_anchor and len(fams_with_navy_blue) >= 3:
                base_score = 0.20
            # Rule 6: No rule above matches
            else:
                base_score = 0.55

    # Three-color rule penalty: max(0, base_score - 0.20 * max(0, distinct_major_colors - 3))
    penalty = 0.20 * max(0, distinct_colors - 3)
    final_score = max(0.0, min(1.0, base_score - penalty))
    return round(final_score, 4)


# --- 3. STYLE SCORING ---

def calculate_style_score(items: list[OutfitItemSlot]) -> float:
    """Calculate deterministic style compatibility score according to Section 4.

    Outfit style score is the mean of every major-item pair (symmetric).
    """
    major_items = _get_major_items(items)
    if len(major_items) < 2:
        return 1.0

    pair_scores: list[float] = []
    n = len(major_items)
    for i in range(n):
        for j in range(i + 1, n):
            s1 = major_items[i].style.lower().strip()
            s2 = major_items[j].style.lower().strip()
            if s1 == s2:
                pair_scores.append(1.00)
            elif (s1, s2) in STYLE_PAIR_SCORES:
                pair_scores.append(STYLE_PAIR_SCORES[(s1, s2)])
            elif (s2, s1) in STYLE_PAIR_SCORES:
                pair_scores.append(STYLE_PAIR_SCORES[(s2, s1)])
            else:
                pair_scores.append(0.60)

    mean_score = sum(pair_scores) / len(pair_scores)
    return round(max(0.0, min(1.0, mean_score)), 4)


# --- 4. FORMALITY SCORING ---

def calculate_formality_score(
    items: list[OutfitItemSlot],
    target_range: list[int] | None = None,
) -> float:
    """Calculate formality score according to Section 5.

    If average formality of major items is inside target_range [min, max], score is 1.0.
    Otherwise max(0, 1 - distance / 4).
    """
    major_items = _get_major_items(items)
    if not major_items:
        return 1.0

    avg_formality = sum(item.formality_level for item in major_items) / len(major_items)
    if not target_range or len(target_range) != 2:
        target_range = [2, 3]

    min_f, max_f = target_range[0], target_range[1]
    if min_f <= avg_formality <= max_f:
        return 1.0

    distance = min(abs(avg_formality - min_f), abs(avg_formality - max_f))
    score = max(0.0, 1.0 - (distance / 4.0))
    return round(max(0.0, min(1.0, score)), 4)


# --- 5. WEATHER & ENVIRONMENT SCORING ---

def calculate_weather_score(
    items: list[OutfitItemSlot],
    weather_condition: str,
    environment: str | None = None,
) -> float:
    """Calculate weather and environment score according to Section 6.

    Base score is proportion of major items whose weather_suitability contains target weather.
    Adjustments are applied additively and clamped to [0, 1].
    Material capabilities rely STRICTLY on explicit functional_flags; never inferred from material names.
    """
    major_items = _get_major_items(items)
    if not major_items:
        return 1.0

    target_weather = weather_condition.lower().strip()
    env = environment.lower().strip() if environment else None

    # Base score: proportion of major items suitable for target weather
    suitable_count = sum(
        1 for item in major_items
        if any(target_weather in w.lower() for w in item.weather_suitability)
    )
    base_score = suitable_count / len(major_items)

    adjustment = 0.0
    outerwear_items = [item for item in items if item.slot_role == OutfitSlotRole.OUTERWEAR]
    footwear_items = [item for item in items if item.slot_role == OutfitSlotRole.FOOTWEAR]
    has_outerwear = len(outerwear_items) > 0

    # Rule 1: Hot weather with heavy outerwear (STRICTLY via functional_flags)
    if target_weather == "hot" and has_outerwear:
        if any("heavy" in item.functional_flags for item in outerwear_items):
            adjustment -= 0.40

    # Rule 2: Cool weather without outerwear (outerwear optional if indoor)
    if target_weather == "cool" and env != "indoor" and not has_outerwear:
        adjustment -= 0.10

    # Rule 3: Cold weather without suitable outerwear
    if target_weather == "cold":
        has_cold_outerwear = any(
            any("cold" in w.lower() for w in item.weather_suitability)
            for item in outerwear_items
        )
        if not has_cold_outerwear:
            adjustment -= 0.40

    # Rule 4: Rainy weather with light suede/canvas footwear (requires explicit 'light' flag)
    if target_weather == "rainy":
        for shoe in footwear_items:
            mat = shoe.material.lower()
            if mat in {"suede", "canvas"} and "light" in shoe.functional_flags:
                adjustment -= 0.25
                break

    # Rule 5: Outdoor + rainy without a water-resistant item
    if target_weather == "rainy" and env == "outdoor":
        has_water_resistant = any("water_resistant" in item.functional_flags for item in items)
        if not has_water_resistant:
            adjustment -= 0.20

    final_score = max(0.0, min(1.0, base_score + adjustment))
    return round(final_score, 4)


# --- 6. PATTERN & PROPORTION SCORING ---

def calculate_pattern_proportion_score(
    items: list[OutfitItemSlot],
    target_style: str | None = None,
) -> tuple[float, list[str]]:
    """Calculate pattern and proportion score according to Section 7.

    Starts at 1.0, subtracts penalties, and emits 'fit_unknown' if fit metadata is missing.
    Oversized exception applies ONLY when target_style is 'streetwear'.
    """
    major_items = _get_major_items(items)
    warnings: list[str] = []
    if not major_items:
        return 1.0, warnings

    penalties = 0.0

    # Check for missing fit metadata
    for item in major_items:
        if not item.fit or item.fit.lower().strip() in {"", "unknown", "none"}:
            if "fit_unknown" not in warnings:
                warnings.append("fit_unknown")

    # Heavily patterned items beyond the first: -0.30 each
    patterned_items = [
        item for item in major_items
        if item.pattern.lower().strip() not in {"solid", "", "none"}
    ]
    if len(patterned_items) > 1:
        penalties += 0.30 * (len(patterned_items) - 1)

    # Patterned top plus patterned bottom: additional -0.20
    tops = [item for item in items if item.slot_role == OutfitSlotRole.TOP]
    bottoms = [item for item in items if item.slot_role == OutfitSlotRole.BOTTOM]
    if tops and bottoms:
        top_patterned = tops[0].pattern.lower().strip() not in {"solid", "", "none"}
        bottom_patterned = bottoms[0].pattern.lower().strip() not in {"solid", "", "none"}
        if top_patterned and bottom_patterned:
            penalties += 0.20

    # Oversized top plus oversized/wide bottom: -0.15 unless TARGET style is streetwear
    target_style_lower = target_style.lower().strip() if target_style else ""
    is_streetwear = (target_style_lower == "streetwear")
    if tops and bottoms and not is_streetwear:
        top_oversized = tops[0].fit.lower().strip() in {"oversized", "baggy"}
        bottom_oversized = bottoms[0].fit.lower().strip() in {"oversized", "wide", "baggy"}
        if top_oversized and bottom_oversized:
            penalties += 0.15

    score = max(0.0, min(1.0, 1.0 - penalties))
    return round(score, 4), warnings


# --- 7. COMPOSITE FASHION SCORE & TIE-BREAKING ---

def calculate_composite_fashion_score(
    items: list[OutfitItemSlot],
    context: StylistContext | None = None,
) -> tuple[float, dict[str, float], list[str]]:
    """Calculate the exact composite fashion score according to Section 8.

    Weights:
      0.30 * color_score
      + 0.20 * style_score
      + 0.20 * formality_score
      + 0.20 * weather_environment_score
      + 0.10 * pattern_proportion_score
    """
    warnings: list[str] = []

    color_score = calculate_color_score(items)
    style_score = calculate_style_score(items)

    formality_range = context.target_formality_range if context else [2, 3]
    formality_score = calculate_formality_score(items, formality_range)

    weather_condition = context.weather_condition if context else "warm"
    environment = context.environment if context else None
    weather_score = calculate_weather_score(items, weather_condition, environment)

    target_style = context.style_hints[0] if context and context.style_hints else None
    pattern_score, pat_warnings = calculate_pattern_proportion_score(items, target_style)
    warnings.extend(pat_warnings)

    composite = (
        0.30 * color_score
        + 0.20 * style_score
        + 0.20 * formality_score
        + 0.20 * weather_score
        + 0.10 * pattern_score
    )
    final_score = round(max(0.0, min(1.0, composite)), 4)

    components = {
        "color_score": color_score,
        "style_score": style_score,
        "formality_score": formality_score,
        "weather_environment_score": weather_score,
        "pattern_proportion_score": pattern_score,
    }

    return final_score, components, warnings


def count_recently_worn_items(
    items: list[OutfitItemSlot],
    reference_time: datetime | None = None,
    recent_window_hours: int = 48,
) -> int:
    """Count items in an outfit that were worn within recent_window_hours.

    Uses item.last_worn_at (ISO 8601 string). If last_worn_at is missing,
    unparseable, or outside the window, the item is not counted as recently worn.
    """
    if not items:
        return 0
    ref = reference_time or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    recent_count = 0
    for item in items:
        if not item.last_worn_at:
            continue
        try:
            raw = item.last_worn_at.replace("Z", "+00:00")
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            diff_seconds = (ref - dt).total_seconds()
            if 0 <= diff_seconds <= recent_window_hours * 3600:
                recent_count += 1
        except (ValueError, TypeError):
            continue
    return recent_count


def outfit_tie_breaker_key(
    evaluated_outfit: EvaluatedOutfit,
    recent_wear_count: int = 0,
) -> tuple[float, float, int, str]:
    """Deterministic tie-breaker key according to Section 8.

    Order:
      1. Descending fashion_score (-fashion_score)
      2. Descending weather score (-weather_score)
      3. Ascending recently worn items count
      4. Ascending combination_id
    """
    weather_score = evaluated_outfit.component_scores.get("weather_environment_score", 0.0)
    return (
        -evaluated_outfit.fashion_score,
        -weather_score,
        recent_wear_count,
        evaluated_outfit.combination_id,
    )
