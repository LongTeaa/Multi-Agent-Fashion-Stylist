from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from app.agents.state import EvaluatedOutfit, OutfitItemSlot, StylistContext
from app.agents.garment_profile import effective_length, infer_silhouette_level
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

STYLE_ALIASES = {"athletic": "sporty", "street": "streetwear", "business": "formal"}

STYLE_PAIR_SCORES: dict[tuple[str, str], float] = {
    # High compatibility (0.95 - 1.0)
    ("casual", "casual"): 1.00,
    ("smart_casual", "smart_casual"): 1.00,
    ("formal", "formal"): 1.00,
    ("streetwear", "streetwear"): 1.00,
    ("minimalist", "minimalist"): 1.00,
    ("vintage", "vintage"): 1.00,
    ("sporty", "sporty"): 1.00,
    ("luxury", "luxury"): 1.00,

    ("casual", "streetwear"): 0.95,
    ("casual", "minimalist"): 0.95,
    ("smart_casual", "minimalist"): 0.95,
    ("smart_casual", "casual"): 0.95,
    ("sporty", "streetwear"): 0.90,

    # Medium-High compatibility (0.80 - 0.85)
    ("smart_casual", "formal"): 0.85,
    ("minimalist", "vintage"): 0.85,
    ("sporty", "casual"): 0.85,
    ("casual", "vintage"): 0.80,
    ("smart_casual", "vintage"): 0.80,

    # Medium compatibility (0.65 - 0.75)
    ("formal", "minimalist"): 0.75,
    ("formal", "vintage"): 0.70,
    ("streetwear", "minimalist"): 0.70,
    ("streetwear", "vintage"): 0.65,

    # Medium-Low compatibility (0.50 - 0.55)
    ("formal", "casual"): 0.55,

    # Low compatibility (0.20 - 0.25)
    ("sporty", "formal"): 0.25,
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
    Applies the Advisor's Style Compatibility Matrix (0.0 to 1.0, continuous scale).
    """
    major_items = _get_major_items(items)
    if len(major_items) < 2:
        return 1.0

    pair_scores: list[float] = []
    n = len(major_items)
    for i in range(n):
        for j in range(i + 1, n):
            it1 = major_items[i]
            it2 = major_items[j]
            s1 = STYLE_ALIASES.get(it1.style.lower().strip(), it1.style.lower().strip())
            s2 = STYLE_ALIASES.get(it2.style.lower().strip(), it2.style.lower().strip())

            # Cross-role footwear vs dress / formal suit clash
            sub1 = it1.sub_category.lower().strip()
            sub2 = it2.sub_category.lower().strip()
            is_shoe_formal_clash = (
                (it1.slot_role == OutfitSlotRole.FOOTWEAR and sub1 in {"sneakers", "running_shoes", "slides"} and (it2.slot_role == OutfitSlotRole.DRESS or it2.category == WardrobeCategory.DRESS) and s2 in {"formal", "luxury"}) or
                (it2.slot_role == OutfitSlotRole.FOOTWEAR and sub2 in {"sneakers", "running_shoes", "slides"} and (it1.slot_role == OutfitSlotRole.DRESS or it1.category == WardrobeCategory.DRESS) and s1 in {"formal", "luxury"})
            )
            if is_shoe_formal_clash:
                pair_scores.append(0.25)
                continue

            # Advisor example: Slides / flip-flops with formal suit / trousers -> Low (0.20)
            is_shoe_suit_clash = (
                (it1.slot_role == OutfitSlotRole.FOOTWEAR and sub1 in {"slides", "flip_flops"} and s2 in {"formal", "luxury"}) or
                (it2.slot_role == OutfitSlotRole.FOOTWEAR and sub2 in {"slides", "flip_flops"} and s1 in {"formal", "luxury"})
            )
            if is_shoe_suit_clash:
                pair_scores.append(0.20)
                continue

            # Advisor example: Hoodie oversized + Formal blazer -> Low/Medium (0.35)
            is_hoodie_blazer_clash = (
                ("hoodie" in sub1 and "blazer" in sub2 and s2 in {"formal", "luxury", "smart_casual"}) or
                ("hoodie" in sub2 and "blazer" in sub1 and s1 in {"formal", "luxury", "smart_casual"})
            )
            if is_hoodie_blazer_clash:
                pair_scores.append(0.35)
                continue

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


# --- 6. PROPORTION BALANCE & PATTERN SCORING ---

def _derive_silhouette(item: OutfitItemSlot) -> int:
    """Stored silhouette (1-5) wins; free-text inference only fills a missing value."""
    if item.silhouette_level is not None:
        return item.silhouette_level
    return infer_silhouette_level(item.fit, item.sub_category, item.name)


def _derive_length(item: OutfitItemSlot) -> str | None:
    """Category-aware length with proportion meaning (None for shoes/accessories)."""
    return effective_length(item.category.value, item.length, item.sub_category, item.name)


def _is_patterned(item: OutfitItemSlot) -> bool:
    return item.pattern.lower().strip() not in {"solid", "", "none", "unknown"}


# Top silhouette x bottom silhouette -> base proportion score (before length/layer modifiers).
# Rows: top 1..5, columns: bottom 1..5. 1 = very fitted, 3 = regular, 5 = oversized.
#   - Fitted top over a regular-to-wide bottom is the "golden" contrast (0.95).
#   - Loose top over a fitted/regular bottom is the classic counterweight (0.92).
#   - Regular on regular is clean but unremarkable (0.85).
#   - Extremes on both halves swallow (5+5) or constrict (1+1) the figure.
PROPORTION_MATRIX: tuple[tuple[float, ...], ...] = (
    # bottom:  1     2     3     4     5
    (0.60, 0.78, 0.95, 0.95, 0.95),  # top 1
    (0.78, 0.82, 0.95, 0.95, 0.95),  # top 2
    (0.82, 0.86, 0.85, 0.88, 0.84),  # top 3
    (0.92, 0.92, 0.92, 0.74, 0.66),  # top 4
    (0.90, 0.92, 0.92, 0.66, 0.55),  # top 5
)
STREETWEAR_VOLUME_SCORE = 0.92  # streetwear deliberately stacks volume (both halves >= 4)
SPORT_FITTED_SCORE = 0.92  # compression/activewear layers are meant to be fitted
ELONGATION_BONUS = 0.05  # cropped/waist-length top over a full-length bottom
LAYER_HARMONY_BONUS = 0.03  # outer layer whose length frames the silhouette
SHORTENING_PENALTY = 0.10  # long top/outer over a short bottom
BULK_TRAP_PENALTY = 0.15  # oversized outer + loose top + baggy bottom
DRESS_BASE_SCORE = 0.92  # one-piece outfits are inherently cohesive


def calculate_proportion_score(
    items: list[OutfitItemSlot],
    target_style: str | None = None,
) -> tuple[float, list[str]]:
    """Calculate deterministic proportion balance and pattern compatibility (0.0-1.0).

    1. Silhouette contrast: ``PROPORTION_MATRIX[top][bottom]``. Golden contrast
       (fitted top + regular/wide bottom) 0.95; classic counterweight (loose top +
       fitted/regular bottom) 0.92; regular + regular 0.85; 4+4 0.74;
       4+5 / 5+4 0.66; 5+5 0.55; 1+1 0.60. Streetwear scores any loose + loose
       pairing 0.92 and sport/activewear scores 1+1 at 0.92.
    2. Length: cropped/waist top + full-length bottom +0.05 (leg elongation);
       long top + short bottom -0.10.
    3. Layers: cropped outer over full-length bottom/dress, or long outer over
       full-length bottom/dress, +0.03; long outer over short bottom/dress -0.10;
       oversized outer + loose top + baggy bottom -0.15 unless streetwear.
    4. Dress: base 0.92 with the layer rules above; oversized dress under an
       oversized outer -0.10 unless streetwear.
    5. Patterns: -0.30 per patterned major item beyond the first; -0.20 more when
       both top and bottom are patterned.

    Stored silhouette/length are authoritative; inference applies only to missing data.
    """
    major_items = _get_major_items(items)
    warnings: list[str] = []
    if not major_items:
        return 1.0, warnings

    if any(not item.fit or item.fit.lower().strip() in {"", "unknown", "none"} for item in major_items):
        warnings.append("fit_unknown")

    tops = [item for item in items if item.slot_role == OutfitSlotRole.TOP]
    bottoms = [item for item in items if item.slot_role == OutfitSlotRole.BOTTOM]
    dresses = [item for item in items if item.slot_role == OutfitSlotRole.DRESS]
    outerwears = [item for item in items if item.slot_role == OutfitSlotRole.OUTERWEAR]

    patterned_count = sum(1 for item in major_items if _is_patterned(item))
    pattern_penalty = 0.30 * max(0, patterned_count - 1)
    if tops and bottoms and _is_patterned(tops[0]) and _is_patterned(bottoms[0]):
        pattern_penalty += 0.20

    target_style_lower = target_style.lower().strip() if target_style else ""
    target_style_lower = STYLE_ALIASES.get(target_style_lower, target_style_lower)
    is_streetwear = target_style_lower == "streetwear"
    is_sport = target_style_lower in {"sporty", "activewear"} or any(
        "sport" in item.functional_flags for item in items
    )

    outer = outerwears[0] if outerwears else None
    outer_sil = _derive_silhouette(outer) if outer else None
    outer_len = _derive_length(outer) if outer else None

    def layer_adjustment(lower_len: str | None) -> float:
        if outer is None or lower_len is None:
            return 0.0
        if outer_len == "long" and lower_len == "cropped":
            return -SHORTENING_PENALTY
        if lower_len == "long" and outer_len in {"cropped", "waist", "long"}:
            return LAYER_HARMONY_BONUS
        return 0.0

    if tops and bottoms:
        top_sil = _derive_silhouette(tops[0])
        bot_sil = _derive_silhouette(bottoms[0])
        top_len = _derive_length(tops[0])
        bot_len = _derive_length(bottoms[0])

        if top_sil >= 4 and bot_sil >= 4 and is_streetwear:
            base = STREETWEAR_VOLUME_SCORE
        elif top_sil <= 1 and bot_sil <= 1 and is_sport:
            base = SPORT_FITTED_SCORE
        else:
            base = PROPORTION_MATRIX[top_sil - 1][bot_sil - 1]

        if top_len in {"cropped", "waist"} and bot_len == "long":
            base += ELONGATION_BONUS
        elif top_len == "long" and bot_len == "cropped":
            base -= SHORTENING_PENALTY

        if outer is not None and outer_sil is not None:
            if outer_sil >= 5 and top_sil >= 4 and bot_sil >= 5 and not is_streetwear:
                base -= BULK_TRAP_PENALTY
            else:
                base += layer_adjustment(bot_len)
    elif dresses:
        dress = dresses[0]
        dress_sil = _derive_silhouette(dress)
        base = DRESS_BASE_SCORE
        if outer is not None and outer_sil is not None and outer_sil >= 5 and dress_sil >= 5 and not is_streetwear:
            base -= SHORTENING_PENALTY
        else:
            base += layer_adjustment(_derive_length(dress))
    else:
        base = 1.0

    final_prop = max(0.0, min(1.0, base - pattern_penalty))
    return round(final_prop, 4), warnings


def calculate_pattern_proportion_score(
    items: list[OutfitItemSlot],
    target_style: str | None = None,
) -> tuple[float, list[str]]:
    """Backward-compatible alias for calculate_proportion_score."""
    return calculate_proportion_score(items, target_style)


# --- 7. TIER-2 OUTFIT AESTHETIC SCORE ---

def calculate_aesthetic_score(
    items: list[OutfitItemSlot],
    target_style: str | None = None,
) -> tuple[float, dict[str, float], list[str]]:
    """Calculate intrinsic Tier-2 Outfit Aesthetic Score (0.0 to 1.0, equivalent to 0-100).

    AestheticScore = 0.40 * ColorHarmony + 0.35 * ProportionBalance + 0.25 * StyleCompatibility
    Completely independent of external weather or user situation.
    """
    color_score = calculate_color_score(items)
    proportion_score, warnings = calculate_proportion_score(items, target_style)
    style_score = calculate_style_score(items)

    score = 0.40 * color_score + 0.35 * proportion_score + 0.25 * style_score
    final_score = round(max(0.0, min(1.0, score)), 4)

    components = {
        "color_score": color_score,
        "proportion_score": proportion_score,
        "style_score": style_score,
        "aesthetic_score": final_score,
    }
    return final_score, components, warnings


# --- 8. COMPOSITE FASHION SCORE & TIE-BREAKING ---

def calculate_composite_fashion_score(
    items: list[OutfitItemSlot],
    context: StylistContext | None = None,
) -> tuple[float, dict[str, float], list[str]]:
    """Calculate composite fashion score combining Tier-2 Aesthetic with Contextual elements."""
    warnings: list[str] = []

    target_style = context.style_hints[0] if context and context.style_hints else None
    aesthetic_score, aest_components, prop_warnings = calculate_aesthetic_score(items, target_style)
    warnings.extend(prop_warnings)

    color_score = aest_components["color_score"]
    style_score = aest_components["style_score"]
    proportion_score = aest_components["proportion_score"]

    formality_range = context.target_formality_range if context else [2, 3]
    formality_score = calculate_formality_score(items, formality_range)

    weather_condition = context.weather_condition if context else "warm"
    environment = context.environment if context else None
    weather_score = calculate_weather_score(items, weather_condition, environment)

    composite = (
        0.30 * color_score
        + 0.20 * style_score
        + 0.20 * formality_score
        + 0.20 * weather_score
        + 0.10 * proportion_score
    )
    final_score = round(max(0.0, min(1.0, composite)), 4)

    components = {
        "color_score": color_score,
        "style_score": style_score,
        "formality_score": formality_score,
        "weather_environment_score": weather_score,
        "pattern_proportion_score": proportion_score,
        "proportion_score": proportion_score,
        "aesthetic_score": aesthetic_score,
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
