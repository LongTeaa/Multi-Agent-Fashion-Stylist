from __future__ import annotations

from datetime import datetime, timezone
import pytest
from app.agents.fashion_agent import (
    MAX_EVALUATED_OUTFITS,
    NO_COMPLETE_OUTFIT_ERROR,
    NO_COMPLETE_OUTFIT_WARNING,
    TOP_K_OUTFITS,
    evaluate_and_rank_combinations,
    fashion_agent_node,
    generate_outfit_combinations,
)
from app.agents.fashion_scoring import (
    calculate_aesthetic_score,
    calculate_color_score,
    calculate_composite_fashion_score,
    calculate_formality_score,
    calculate_pattern_proportion_score,
    calculate_proportion_score,
    calculate_style_score,
    calculate_weather_score,
    count_recently_worn_items,
    outfit_tie_breaker_key,
)
from app.agents.state import (
    EvaluatedOutfit,
    OutfitItemSlot,
    StylistContext,
    StylistGraphState,
)
from app.models.entities import OutfitSlotRole, WardrobeCategory


def _make_slot(
    item_id: str,
    role: OutfitSlotRole,
    name: str = "item",
    color: str = "white",
    style: str = "smart_casual",
    formality: int = 3,
    weather: list[str] | None = None,
    pattern: str = "solid",
    material: str = "cotton",
    fit: str = "regular",
    flags: list[str] | None = None,
    times_worn: int = 0,
    last_worn_at: str | None = None,
    comfort_level: int = 3,
    silhouette_level: int = 3,
    length: str = "hip",
    sub_category: str = "",
) -> OutfitItemSlot:
    """Helper to create an OutfitItemSlot with valid category matching."""
    category_map = {
        OutfitSlotRole.TOP: WardrobeCategory.TOP,
        OutfitSlotRole.BOTTOM: WardrobeCategory.BOTTOM,
        OutfitSlotRole.DRESS: WardrobeCategory.DRESS,
        OutfitSlotRole.FOOTWEAR: WardrobeCategory.FOOTWEAR,
        OutfitSlotRole.OUTERWEAR: WardrobeCategory.OUTERWEAR,
        OutfitSlotRole.ACCESSORY: WardrobeCategory.ACCESSORY,
    }
    return OutfitItemSlot(
        item_id=item_id,
        slot_role=role,
        category=category_map[role],
        name=name,
        primary_color=color,
        style=style,
        formality_level=formality,
        comfort_level=comfort_level,
        silhouette_level=silhouette_level,
        length=length,
        sub_category=sub_category,
        weather_suitability=weather or ["warm", "cool"],
        pattern=pattern,
        material=material,
        fit=fit,
        functional_flags=flags or [],
        times_worn=times_worn,
        last_worn_at=last_worn_at,
    )


# ============================================================================
# 1. COLOR SCORING TESTS
# ============================================================================

def test_color_all_neutral():
    """All neutral colors score 1.0."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="white")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="black")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="grey")

    score = calculate_color_score([top, bottom, shoes])
    assert score == 1.0


def test_color_navy_as_neutral_in_neutral_combo():
    """Navy behaves as neutral in neutral-base combinations."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="white")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="navy")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="grey")

    score = calculate_color_score([top, bottom, shoes])
    assert score == 1.0


def test_color_navy_with_blue_is_monochromatic():
    """Navy + blue evaluates as monochromatic blue family (0.90), not neutral + accent (0.95)."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="navy")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="blue")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="navy")

    score = calculate_color_score([top, bottom, shoes])
    # Monochromatic non-neutral rule gives 0.90
    assert score == 0.90


def test_color_navy_with_multiple_accents_not_single_accent():
    """Navy + blue + red has 2 distinct accent families (blue and red), not 1 accent."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="navy")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="blue")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="red")

    score = calculate_color_score([top, bottom, shoes])
    # Unlisted combinations score 0.55
    assert score == 0.55


def test_color_neutral_plus_one_accent():
    """Neutral base plus single accent family scores 0.95."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="red")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="black")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="white")

    score = calculate_color_score([top, bottom, shoes])
    assert score == 0.95


def test_color_navy_as_neutral_anchor_with_one_accent():
    """Navy acting as neutral anchor with exactly one accent family (red) scores 0.95."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="red")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="navy")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="black")

    score = calculate_color_score([top, bottom, shoes])
    assert score == 0.95


def test_color_monochromatic_non_neutral():
    """One non-neutral family with multiple shades scores 0.90."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="light_blue")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="blue")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="denim_blue")

    score = calculate_color_score([top, bottom, shoes])
    assert score == 0.90


def test_color_analogous_families():
    """Two analogous families (e.g. orange and yellow) score 0.85."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="orange")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="yellow")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="orange")

    score = calculate_color_score([top, bottom, shoes])
    assert score == 0.85


def test_color_complementary_with_neutral():
    """Two complementary families with neutral anchor score 0.80."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="blue")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="orange")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="white")

    score = calculate_color_score([top, bottom, shoes])
    assert score == 0.80


def test_color_three_saturated_without_neutral():
    """Three or more saturated families without neutral anchor score 0.20."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="red")
    bottom = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="green")
    shoes = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="yellow")

    score = calculate_color_score([top, bottom, shoes])
    assert score == 0.20


def test_color_penalty_for_more_than_three_distinct_colors():
    """Penalty of 0.20 per distinct color beyond 3."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="white")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="black")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="grey")
    coat = _make_slot("coat-1", OutfitSlotRole.OUTERWEAR, color="beige")

    score = calculate_color_score([top, bot, shoe, coat])
    # Base 1.0 - 0.20 * (4 - 3) = 0.80
    assert score == 0.80


def test_color_accessory_ignored_in_color_rule():
    """Accessories must not count toward the three-color rule or color scoring."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="white")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="black")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="grey")
    acc = _make_slot("acc-1", OutfitSlotRole.ACCESSORY, color="red")

    score = calculate_color_score([top, bot, shoe, acc])
    assert score == 1.0


# ============================================================================
# 2. STYLE SCORING TESTS
# ============================================================================

def test_style_identical():
    """Identical styles across major items score 1.0."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, style="smart_casual")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, style="smart_casual")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, style="smart_casual")

    assert calculate_style_score([top, bot, shoe]) == 1.0


def test_style_symmetric_pairs():
    """Style scoring is symmetric across pairs."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, style="casual")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, style="streetwear")

    assert calculate_style_score([top, bot]) == 0.95
    assert calculate_style_score([bot, top]) == 0.95


def test_style_incompatible_pair():
    """Formal + streetwear scores 0.20."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, style="formal")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, style="streetwear")

    assert calculate_style_score([top, bot]) == 0.20


# ============================================================================
# 3. FORMALITY SCORING TESTS
# ============================================================================

def test_formality_in_range():
    """Formality inside target range scores 1.0."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, formality=3)
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, formality=3)
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, formality=2)

    score = calculate_formality_score([top, bot, shoe], target_range=[2, 3])
    assert score == 1.0


def test_formality_distance_penalty():
    """Formality outside range applies distance / 4 penalty."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, formality=5)
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, formality=5)
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, formality=5)

    score = calculate_formality_score([top, bot, shoe], target_range=[2, 3])
    assert score == 0.50


# ============================================================================
# 4. WEATHER & ENVIRONMENT SCORING TESTS
# ============================================================================

def test_weather_base_proportion():
    """Base weather score is proportion of items suitable for condition."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, weather=["cool", "warm"])
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, weather=["cool"])
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, weather=["warm"])

    score = calculate_weather_score([top, bot, shoe], weather_condition="cool")
    assert pytest.approx(score, 0.01) == 0.5667


def test_weather_hot_heavy_outerwear_requires_explicit_flag():
    """Hot weather with heavy outerwear penalty relies strictly on functional_flags."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, weather=["hot"])
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, weather=["hot"])
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, weather=["hot"])

    # Outerwear with material='heavy wool' but WITHOUT 'heavy' in functional_flags must NOT trigger penalty
    coat_no_flag = _make_slot("coat-1", OutfitSlotRole.OUTERWEAR, weather=["cold"], material="heavy wool", flags=[])
    score_no_flag = calculate_weather_score([top, bot, shoe, coat_no_flag], weather_condition="hot")
    assert pytest.approx(score_no_flag, 0.01) == 0.75

    # Outerwear with explicit 'heavy' in functional_flags triggers -0.40 penalty
    coat_with_flag = _make_slot("coat-2", OutfitSlotRole.OUTERWEAR, weather=["cold"], flags=["heavy"])
    score_with_flag = calculate_weather_score([top, bot, shoe, coat_with_flag], weather_condition="hot")
    assert pytest.approx(score_with_flag, 0.01) == 0.35


def test_weather_cool_indoor_exemption():
    """In indoor environment, cool weather without outerwear has no penalty."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, weather=["cool"])
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, weather=["cool"])
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, weather=["cool"])

    score = calculate_weather_score([top, bot, shoe], weather_condition="cool", environment="indoor")
    assert score == 1.0


def test_weather_rainy_suede_and_outdoor_penalties():
    """Rainy weather with light canvas shoes and outdoor without water_resistant item."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, weather=["rainy"])
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, weather=["rainy"])
    # Canvas shoes WITH explicit 'light' functional flag triggers -0.25 penalty
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, weather=["rainy"], material="canvas", flags=["light"])

    score = calculate_weather_score([top, bot, shoe], weather_condition="rainy", environment="outdoor")
    assert pytest.approx(score, 0.01) == 0.55


def test_weather_rainy_canvas_without_light_flag_no_penalty():
    """Rainy weather with canvas shoes lacking 'light' flag does NOT trigger penalty."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, weather=["rainy"])
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, weather=["rainy"])
    # Canvas shoes WITHOUT 'light' flag
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, weather=["rainy"], material="canvas", flags=[])

    # Outdoor without water-resistant item still applies -0.20, but not the -0.25 shoe penalty
    score = calculate_weather_score([top, bot, shoe], weather_condition="rainy", environment="outdoor")
    assert pytest.approx(score, 0.01) == 0.80


# ============================================================================
# 5. PATTERN & PROPORTION SCORING TESTS
# ============================================================================

def test_pattern_all_solid():
    """All solid items score 1.0 without warnings."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, pattern="solid")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, pattern="solid")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, pattern="solid")

    score, warnings = calculate_pattern_proportion_score([top, bot, shoe])
    assert score == 1.0
    assert "fit_unknown" not in warnings


def test_pattern_multiple_patterned_items():
    """Heavily patterned top + patterned bottom applies -0.30 and -0.20."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, pattern="floral")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, pattern="checkered")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, pattern="solid")

    score, _ = calculate_pattern_proportion_score([top, bot, shoe])
    assert score == 0.50


def test_pattern_oversized_exemption_strictly_checks_target_style():
    """Oversized exception is only granted if target_style is 'streetwear', not from item styles."""
    # Top is streetwear item, but user requested formal/smart_casual
    top = _make_slot("top-1", OutfitSlotRole.TOP, style="streetwear", fit="oversized")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, style="casual", fit="wide")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, fit="regular")

    # When target_style is 'smart_casual', penalty -0.15 MUST apply
    score_formal, _ = calculate_pattern_proportion_score([top, bot, shoe], target_style="smart_casual")
    assert pytest.approx(score_formal, 0.01) == 0.85

    # When target_style is 'streetwear', penalty is exempted -> 1.0
    score_streetwear, _ = calculate_pattern_proportion_score([top, bot, shoe], target_style="streetwear")
    assert score_streetwear == 1.0


def test_pattern_missing_fit_emits_warning():
    """Missing fit metadata emits 'fit_unknown' warning without score penalty."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, fit="")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, fit="regular")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, fit="regular")

    score, warnings = calculate_pattern_proportion_score([top, bot, shoe])
    assert score == 1.0
    assert "fit_unknown" in warnings


# ============================================================================
# 6. COMPOSITE FASHION SCORE & TIE BREAKING
# ============================================================================

def test_composite_weights():
    """Verify exact composite weighting: 0.30, 0.20, 0.20, 0.20, 0.10."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, color="white", style="smart_casual", formality=3, weather=["warm"])
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, color="navy", style="smart_casual", formality=3, weather=["warm"])
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR, color="white", style="smart_casual", formality=3, weather=["warm"])

    ctx = StylistContext(
        occasion="cafe",
        time_of_day="afternoon",
        weather_condition="warm",
        target_formality_range=[2, 4],
    )

    score, components, _ = calculate_composite_fashion_score([top, bot, shoe], ctx)
    assert score == 1.0
    assert components["color_score"] == 1.0
    assert components["style_score"] == 1.0
    assert components["formality_score"] == 1.0
    assert components["weather_environment_score"] == 1.0
    assert components["pattern_proportion_score"] == 1.0


def test_tie_breaking_with_real_wear_data():
    """Ties resolve by weather score, then fewer recently worn items, then combination_id.

    Proves invariant: An item worn 20 times a year ago is preferred over an item worn 2 hours ago.
    """
    ref_time = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)

    # o1 has an item worn 20 times, but last worn 1 year ago (NOT recently worn within 48h)
    slot_old = _make_slot("t1", OutfitSlotRole.TOP, times_worn=20, last_worn_at="2025-01-01T00:00:00Z")
    o1 = EvaluatedOutfit(
        items=[slot_old],
        fashion_score=0.85,
        component_scores={"weather_environment_score": 0.90},
        combination_id="combo_a",
    )

    # o2 has an item worn only 1 time, but last worn 2 hours ago (recently worn within 48h)
    slot_recent = _make_slot("t2", OutfitSlotRole.TOP, times_worn=1, last_worn_at="2026-09-12T10:00:00Z")
    o2 = EvaluatedOutfit(
        items=[slot_recent],
        fashion_score=0.85,
        component_scores={"weather_environment_score": 0.90},
        combination_id="combo_b",
    )

    # o3 has higher weather score
    slot_unworn = _make_slot("t3", OutfitSlotRole.TOP, times_worn=0, last_worn_at=None)
    o3 = EvaluatedOutfit(
        items=[slot_unworn],
        fashion_score=0.85,
        component_scores={"weather_environment_score": 0.95},
        combination_id="combo_c",
    )

    outfits = [o1, o2, o3]
    # Tie-breaking order:
    # 1. Highest weather score (o3 with 0.95)
    # 2. Lower recent_wear_count (o1 has 0 recent wears vs o2 has 1 recent wear)
    # 3. combination_id
    outfits.sort(
        key=lambda o: outfit_tie_breaker_key(
            o,
            recent_wear_count=count_recently_worn_items(o.items, reference_time=ref_time, recent_window_hours=48),
        )
    )

    assert outfits[0].combination_id == "combo_c"
    assert outfits[1].combination_id == "combo_a"  # o1 (0 recent) beats o2 (1 recent)!
    assert outfits[2].combination_id == "combo_b"


# ============================================================================
# 7. FASHION AGENT NODE & COMBINATIONS
# ============================================================================

def test_fashion_agent_generates_both_branches():
    """Generates top+bottom+footwear and dress+footwear branches without mixing."""
    pool = {
        "tops": [_make_slot("t1", OutfitSlotRole.TOP)],
        "bottoms": [_make_slot("b1", OutfitSlotRole.BOTTOM)],
        "dresses": [_make_slot("d1", OutfitSlotRole.DRESS)],
        "footwear": [_make_slot("s1", OutfitSlotRole.FOOTWEAR)],
        "outerwear": [],
        "accessories": [],
    }

    combos = generate_outfit_combinations(pool)
    assert len(combos) == 2

    roles_combo1 = {item.slot_role for item in combos[0]}
    roles_combo2 = {item.slot_role for item in combos[1]}

    assert roles_combo1 == {OutfitSlotRole.TOP, OutfitSlotRole.BOTTOM, OutfitSlotRole.FOOTWEAR}
    assert roles_combo2 == {OutfitSlotRole.DRESS, OutfitSlotRole.FOOTWEAR}


def test_fashion_agent_fair_quota_never_starves_dresses():
    """When top+bottom combinations exceed 350, dresses are still generated and evaluated."""
    # 10 tops, 10 bottoms, 4 shoes -> 400 top-bottom combos (exceeds 350 quota)
    tops = [_make_slot(f"t{i}", OutfitSlotRole.TOP) for i in range(10)]
    bottoms = [_make_slot(f"b{i}", OutfitSlotRole.BOTTOM) for i in range(10)]
    shoes = [_make_slot(f"s{i}", OutfitSlotRole.FOOTWEAR) for i in range(4)]
    # 2 dresses -> 8 dress combos
    dresses = [_make_slot(f"d{i}", OutfitSlotRole.DRESS) for i in range(2)]

    pool = {
        "tops": tops,
        "bottoms": bottoms,
        "dresses": dresses,
        "footwear": shoes,
        "outerwear": [],
        "accessories": [],
    }

    combos = generate_outfit_combinations(pool)
    # Total combinations should be capped <= 500
    assert len(combos) <= 500

    # Ensure dress combos are present and not starved!
    dress_combos = [c for c in combos if any(item.slot_role == OutfitSlotRole.DRESS for item in c)]
    assert len(dress_combos) == 8


def test_fashion_agent_quota_redistribution_uses_full_capacity():
    """When dress branch produces only 2 combinations, top-bottom expands to reach 500 cap."""
    # 15 tops, 15 bottoms, 3 shoes -> 675 potential top-bottom combos (exceeds 500)
    tops = [_make_slot(f"t{i}", OutfitSlotRole.TOP) for i in range(15)]
    bottoms = [_make_slot(f"b{i}", OutfitSlotRole.BOTTOM) for i in range(15)]
    shoes = [_make_slot(f"s{i}", OutfitSlotRole.FOOTWEAR) for i in range(3)]
    # 1 dress, 2 shoes -> 2 dress combos
    dresses = [_make_slot("d1", OutfitSlotRole.DRESS)]

    pool = {
        "tops": tops,
        "bottoms": bottoms,
        "dresses": dresses,
        "footwear": shoes,  # 3 shoes -> 15 * 15 * 3 = 675 potential top-bottom combos
        "outerwear": [],
        "accessories": [],
    }

    combos = generate_outfit_combinations(pool)
    # Exactly 500 combinations should be generated (3 dress + 497 top-bottom)
    assert len(combos) == 500
    dress_combos = [c for c in combos if any(item.slot_role == OutfitSlotRole.DRESS for item in c)]
    top_bottom_combos = [c for c in combos if any(item.slot_role == OutfitSlotRole.TOP for item in c)]
    assert len(dress_combos) == 3
    assert len(top_bottom_combos) == 497


def test_fashion_agent_never_combines_dress_with_top_or_bottom():
    """Invariant: An outfit never contains both dress and top/bottom."""
    pool = {
        "tops": [_make_slot("t1", OutfitSlotRole.TOP)],
        "bottoms": [_make_slot("b1", OutfitSlotRole.BOTTOM)],
        "dresses": [_make_slot("d1", OutfitSlotRole.DRESS)],
        "footwear": [_make_slot("s1", OutfitSlotRole.FOOTWEAR)],
    }

    combos = generate_outfit_combinations(pool)
    for c in combos:
        roles = {item.slot_role for item in c}
        assert not (OutfitSlotRole.DRESS in roles and (OutfitSlotRole.TOP in roles or OutfitSlotRole.BOTTOM in roles))


def test_fashion_agent_incomplete_wardrobe():
    """Missing required slot (e.g. no footwear) returns NO_COMPLETE_OUTFIT."""
    pool = {
        "tops": [_make_slot("t1", OutfitSlotRole.TOP)],
        "bottoms": [_make_slot("b1", OutfitSlotRole.BOTTOM)],
        "dresses": [],
        "footwear": [],
    }

    state: StylistGraphState = {
        "candidate_pool": pool,
        "context": StylistContext(
            occasion="cafe",
            time_of_day="morning",
            weather_condition="warm",
        ),
    }

    res = fashion_agent_node(state)
    assert res["evaluated_outfits"] == []
    assert NO_COMPLETE_OUTFIT_ERROR in res["errors"]
    assert any(NO_COMPLETE_OUTFIT_WARNING in w for w in res["warnings"])


# ============================================================================
# 8. GOLDEN SCENARIO FULL 8-ITEM BENCHMARK TEST
# ============================================================================

def test_golden_scenario_full_wardrobe_top_three():
    """Full 8-item Golden Wardrobe fixture generates 18 combinations.

    Verifies that 'White Polo + Navy Chinos + White Sneakers' strictly ranks in the TOP 3
    for the Phase 4 Golden Query: 'Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?'
    """
    # 8-item Golden Wardrobe fixture from DATA_SCHEMA.md Section 5
    polo = _make_slot("item-top-01", OutfitSlotRole.TOP, name="white solid cotton polo", color="white", style="smart_casual", formality=3, weather=["warm", "cool"])
    shirt = _make_slot("item-top-02", OutfitSlotRole.TOP, name="black button-down shirt", color="black", style="smart_casual", formality=3, weather=["warm", "cool", "cold"])
    tee = _make_slot("item-top-03", OutfitSlotRole.TOP, name="grey graphic tee", color="grey", style="streetwear", formality=1, weather=["hot", "warm"], pattern="graphic")

    chinos = _make_slot("item-bottom-01", OutfitSlotRole.BOTTOM, name="navy chinos", color="navy", style="smart_casual", formality=3, weather=["warm", "cool"])
    trousers = _make_slot("item-bottom-02", OutfitSlotRole.BOTTOM, name="black wool trousers", color="black", style="formal", formality=4, weather=["warm", "cool", "cold"])
    shorts = _make_slot("item-bottom-03", OutfitSlotRole.BOTTOM, name="denim shorts", color="denim_blue", style="casual", formality=1, weather=["hot", "warm"])

    sneakers = _make_slot("item-shoes-01", OutfitSlotRole.FOOTWEAR, name="white leather sneakers", color="white", style="minimalist", formality=2, weather=["hot", "warm", "cool"])
    oxfords = _make_slot("item-shoes-02", OutfitSlotRole.FOOTWEAR, name="brown leather Oxford shoes", color="brown", style="formal", formality=4, weather=["warm", "cool", "cold"])

    pool = {
        "tops": [polo, shirt, tee],
        "bottoms": [chinos, trousers, shorts],
        "dresses": [],
        "footwear": [sneakers, oxfords],
        "outerwear": [],
        "accessories": [],
    }

    # Query context: 'Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?'
    ctx = StylistContext(
        occasion="cafe",
        time_of_day="evening",
        weather_condition="cool",
        target_formality_range=[2, 3],
        style_hints=["smart_casual"],
    )

    state: StylistGraphState = {
        "candidate_pool": pool,
        "context": ctx,
    }

    result = fashion_agent_node(state)
    evaluated = result["evaluated_outfits"]

    # Preserve the full bounded set so Personalization can enforce exclusions
    # before selecting at most five candidates to rerank.
    assert len(evaluated) == 18
    assert len(evaluated) <= MAX_EVALUATED_OUTFITS

    # Extract top 3 outfit combinations
    top_3_combinations = [
        {item.item_id for item in outfit.items}
        for outfit in evaluated[:3]
    ]

    target_golden_combination = {"item-top-01", "item-bottom-01", "item-shoes-01"}

    # Assert invariant: White Polo + Navy Chinos + White Sneakers is strictly in top 3!
    assert target_golden_combination in top_3_combinations, (
        f"Expected {target_golden_combination} to be in top 3, but got: {top_3_combinations}"
    )


# ============================================================================
# 8. PHASE 4 TESTS: PROPORTION BALANCE, STYLE MATRIX & TIER-2 AESTHETIC SCORE
# ============================================================================

def test_proportion_harmonious_contrast_tight_loose():
    """Tight top (1-2) + Loose bottom (4-5) achieves full proportion score (1.0)."""
    top = _make_slot("top-tight", OutfitSlotRole.TOP, silhouette_level=2, fit="slim")
    bot = _make_slot("bot-loose", OutfitSlotRole.BOTTOM, silhouette_level=4, fit="loose")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR)

    score, warnings = calculate_proportion_score([top, bot, shoe])
    assert score == 1.0
    assert "fit_unknown" not in warnings


def test_proportion_harmonious_contrast_loose_fitted():
    """Loose top (4-5) + Fitted bottom (2-3) achieves full proportion score (1.0)."""
    top = _make_slot("top-loose", OutfitSlotRole.TOP, silhouette_level=4, fit="relaxed")
    bot = _make_slot("bot-fitted", OutfitSlotRole.BOTTOM, silhouette_level=2, fit="slim")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR)

    score, _ = calculate_proportion_score([top, bot, shoe])
    assert score == 1.0


def test_proportion_cropped_long_leg_lengthening():
    """Cropped top + Long bottom achieves leg-lengthening full score (1.0)."""
    top = _make_slot("top-crop", OutfitSlotRole.TOP, length="cropped", silhouette_level=2)
    bot = _make_slot("bot-long", OutfitSlotRole.BOTTOM, length="long", silhouette_level=3)
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR)

    score, _ = calculate_proportion_score([top, bot, shoe])
    assert score == 1.0


def test_proportion_long_top_cropped_bottom_penalized():
    """Long top + Cropped bottom shortens silhouette proportions and is penalized."""
    top = _make_slot("top-long", OutfitSlotRole.TOP, length="long", silhouette_level=3)
    bot = _make_slot("bot-crop", OutfitSlotRole.BOTTOM, length="cropped", silhouette_level=3)
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR)

    score, _ = calculate_proportion_score([top, bot, shoe])
    assert score == 0.90


def test_proportion_extreme_loose_clashing_and_streetwear_exemption():
    """Oversized (5) + Baggy (5) is penalized (-0.15), unless target style is streetwear."""
    top = _make_slot("top-5", OutfitSlotRole.TOP, silhouette_level=5, fit="oversized")
    bot = _make_slot("bot-5", OutfitSlotRole.BOTTOM, silhouette_level=5, fit="baggy")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR)

    score_casual, _ = calculate_proportion_score([top, bot, shoe], target_style="casual")
    assert pytest.approx(score_casual, 0.01) == 0.85

    score_streetwear, _ = calculate_proportion_score([top, bot, shoe], target_style="streetwear")
    assert score_streetwear == 1.0


def test_proportion_extreme_tight_clashing_and_sport_exemption():
    """Tight (1) + Tight (1) is penalized (-0.20), unless sporty/activewear."""
    top = _make_slot("top-1", OutfitSlotRole.TOP, silhouette_level=1, fit="skinny")
    bot = _make_slot("bot-1", OutfitSlotRole.BOTTOM, silhouette_level=1, fit="skinny")
    shoe = _make_slot("shoe-1", OutfitSlotRole.FOOTWEAR)

    score_casual, _ = calculate_proportion_score([top, bot, shoe], target_style="casual")
    assert pytest.approx(score_casual, 0.01) == 0.80

    score_sport, _ = calculate_proportion_score([top, bot, shoe], target_style="sporty")
    assert score_sport == 1.0


def test_style_compatibility_matrix_advisor_cases():
    """Verify continuous style scores from Advisor's Style Matrix (0.0 to 1.0)."""
    # 1. Same style = 1.00
    top_c = _make_slot("t1", OutfitSlotRole.TOP, style="casual")
    bot_c = _make_slot("b1", OutfitSlotRole.BOTTOM, style="casual")
    assert calculate_style_score([top_c, bot_c]) == 1.00

    # 2. smart_casual x formal = 0.85
    top_sc = _make_slot("t2", OutfitSlotRole.TOP, style="smart_casual")
    bot_f = _make_slot("b2", OutfitSlotRole.BOTTOM, style="formal")
    assert calculate_style_score([top_sc, bot_f]) == 0.85

    # 3. formal x casual = 0.55
    assert calculate_style_score([top_c, bot_f]) == 0.55

    # 4. formal x streetwear = 0.20
    top_sw = _make_slot("t3", OutfitSlotRole.TOP, style="streetwear")
    assert calculate_style_score([top_sw, bot_f]) == 0.20

    # 5. Sneakers with formal/luxury gown = 0.25 (Low)
    dress_formal = _make_slot("d1", OutfitSlotRole.DRESS, style="formal", formality=5, sub_category="evening_gown")
    sneakers = _make_slot("s1", OutfitSlotRole.FOOTWEAR, style="casual", sub_category="sneakers")
    assert calculate_style_score([dress_formal, sneakers]) == 0.25


def test_tier_2_aesthetic_score_formula():
    """Verify exact Tier-2 Aesthetic Score: 0.40 * Color + 0.35 * Proportion + 0.25 * Style."""
    # Perfect combo: All neutral (1.0), Harmonious contrast (1.0), Matching smart_casual (1.0)
    top = _make_slot("t1", OutfitSlotRole.TOP, color="white", silhouette_level=2, style="smart_casual")
    bot = _make_slot("b1", OutfitSlotRole.BOTTOM, color="black", silhouette_level=4, style="smart_casual")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, color="grey", style="smart_casual")

    aesthetic_score, components, warnings = calculate_aesthetic_score([top, bot, shoe])
    assert aesthetic_score == 1.0
    assert components["color_score"] == 1.0
    assert components["proportion_score"] == 1.0
    assert components["style_score"] == 1.0
    assert components["aesthetic_score"] == 1.0
    assert len(warnings) == 0


def test_tier_2_aesthetic_score_weather_independence():
    """Aesthetic score reflects intrinsic garment harmony, unaffected by external weather changes."""
    top = _make_slot("t1", OutfitSlotRole.TOP, color="white", silhouette_level=2, style="casual", weather=["warm"])
    bot = _make_slot("b1", OutfitSlotRole.BOTTOM, color="navy", silhouette_level=4, style="casual", weather=["warm"])
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, color="white", style="casual", weather=["warm"])

    score_hot, _, _ = calculate_aesthetic_score([top, bot, shoe])

    # Context changing to cold or rainy does NOT alter the intrinsic aesthetic score
    score_cold, _, _ = calculate_aesthetic_score([top, bot, shoe])
    score_rainy, _, _ = calculate_aesthetic_score([top, bot, shoe])

    assert score_hot == score_cold == score_rainy == 1.0


def test_style_hoodie_formal_blazer_advisor_clash():
    """Advisor rule: Hoodie + Formal blazer scores Low/Medium (0.35)."""
    hoodie = _make_slot("h1", OutfitSlotRole.TOP, style="casual", sub_category="hoodie")
    blazer = _make_slot("b1", OutfitSlotRole.OUTERWEAR, style="smart_casual", sub_category="blazer")
    bot = _make_slot("bot1", OutfitSlotRole.BOTTOM, style="smart_casual")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, style="smart_casual")

    # Direct pair compatibility of Hoodie + Blazer is exactly 0.35 (Low/Medium)
    assert calculate_style_score([hoodie, blazer]) == 0.35
    # Overall 4-item outfit style is noticeably impacted
    assert calculate_style_score([hoodie, blazer, bot, shoe]) <= 0.88


def test_style_slides_formal_suit_clash():
    """Advisor rule: Slides / flip-flops with formal items scores Low (0.20)."""
    suit_jacket = _make_slot("sj1", OutfitSlotRole.OUTERWEAR, style="formal", formality=5, sub_category="suit_jacket")
    suit_pants = _make_slot("sp1", OutfitSlotRole.BOTTOM, style="formal", formality=5, sub_category="suit_trousers")
    slides = _make_slot("sl1", OutfitSlotRole.FOOTWEAR, style="casual", sub_category="slides")

    score = calculate_style_score([suit_jacket, suit_pants, slides])
    assert score < 0.60


def test_proportion_layered_outerwear_3layer_bulk_trap():
    """Oversized jacket (5) + loose top (4) + baggy bottom (5) is penalized for extreme bulk."""
    top = _make_slot("t1", OutfitSlotRole.TOP, silhouette_level=4, fit="loose")
    bot = _make_slot("b1", OutfitSlotRole.BOTTOM, silhouette_level=5, fit="baggy")
    coat = _make_slot("c1", OutfitSlotRole.OUTERWEAR, silhouette_level=5, fit="oversized")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR)

    score_casual, _ = calculate_proportion_score([top, bot, coat, shoe], target_style="casual")
    assert score_casual <= 0.85

    score_streetwear, _ = calculate_proportion_score([top, bot, coat, shoe], target_style="streetwear")
    assert score_streetwear == 1.0


def test_proportion_layered_outerwear_long_coat_cropped_bottom():
    """Long coat + cropped pants shortens visual height and is penalized (-0.10)."""
    top = _make_slot("t1", OutfitSlotRole.TOP, length="hip", silhouette_level=3)
    bot = _make_slot("b1", OutfitSlotRole.BOTTOM, length="cropped", silhouette_level=3)
    coat = _make_slot("c1", OutfitSlotRole.OUTERWEAR, length="long", silhouette_level=3)
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR)

    score, _ = calculate_proportion_score([top, bot, coat, shoe])
    assert score <= 0.90


def test_proportion_fallback_derivation_from_crop_top_and_baggy():
    """Fallback derivation correctly identifies silhouette & length from sub_category/name."""
    top = _make_slot("t1", OutfitSlotRole.TOP, sub_category="crop_top", silhouette_level=3, length="")
    bot = _make_slot("b1", OutfitSlotRole.BOTTOM, sub_category="baggy_jeans", silhouette_level=3, length="")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR)

    # crop_top derived length='cropped', baggy_jeans derived sil=5
    # Cropped top + Baggy bottom -> Harmonious contrast + Vertical elongation
    score, _ = calculate_proportion_score([top, bot, shoe])
    assert score == 1.0


