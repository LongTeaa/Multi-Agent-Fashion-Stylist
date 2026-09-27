from __future__ import annotations

import pytest
from app.agents.context_agent import extract_context
from app.agents.context_scoring import (
    WEIGHT_PROFILES,
    calculate_context_composite_score,
    calculate_functional_fit,
    calculate_weather_comfort_fit,
)
from app.agents.coordinator import generate_grounded_explanation_vi
from app.agents.personalization_agent import rerank_evaluated_outfits
from app.agents.state import EvaluatedOutfit, OutfitItemSlot, RankedOutfit, StylistContext
from app.models.entities import OutfitSlotRole, WardrobeCategory


def _make_slot(
    item_id: str,
    role: OutfitSlotRole,
    name: str = "item",
    color: str = "white",
    style: str = "smart_casual",
    formality: int = 3,
    comfort_level: int = 3,
    silhouette_level: int = 3,
    length: str = "hip",
    weather: list[str] | None = None,
    material: str = "cotton",
    flags: list[str] | None = None,
) -> OutfitItemSlot:
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
        weather_suitability=weather or ["warm", "cool"],
        material=material,
        functional_flags=flags or [],
    )


# ============================================================================
# 1. WEATHER & COMFORT FIT TESTS
# ============================================================================

def test_weather_comfort_hot_weather_favors_soft_breathable_items():
    """Hot weather gives high score to comfort_level >= 4 and penalizes heavy/stiff items."""
    # Light, soft cotton tee (comfort 5) + breezy linen pants (comfort 5) + breathable shoes
    tee_soft = _make_slot("t_soft", OutfitSlotRole.TOP, comfort_level=5, weather=["hot", "warm"])
    pants_soft = _make_slot("p_soft", OutfitSlotRole.BOTTOM, comfort_level=5, weather=["hot", "warm"])
    shoes_breathable = _make_slot("s_light", OutfitSlotRole.FOOTWEAR, comfort_level=4, weather=["hot", "warm"])

    score_soft = calculate_weather_comfort_fit([tee_soft, pants_soft, shoes_breathable], weather_condition="hot")

    # Stiff, heavy woolen suit jacket + heavy trousers
    jacket_heavy = _make_slot(
        "j_heavy", OutfitSlotRole.TOP, formality=5, comfort_level=2,
        weather=["cold"], material="wool", flags=["heavy"]
    )
    pants_heavy = _make_slot(
        "p_heavy", OutfitSlotRole.BOTTOM, formality=5, comfort_level=2,
        weather=["cold"], material="wool", flags=["heavy"]
    )
    shoes_leather = _make_slot("s_dress", OutfitSlotRole.FOOTWEAR, formality=5, comfort_level=2, weather=["cool"])

    score_heavy = calculate_weather_comfort_fit([jacket_heavy, pants_heavy, shoes_leather], weather_condition="hot")

    assert score_soft >= 0.90
    assert score_heavy <= 0.40
    assert score_soft > score_heavy + 0.50


def test_weather_comfort_cold_weather_favors_insulating_outerwear():
    """Cold weather rewards suitable outerwear and penalizes lack of outerwear."""
    top = _make_slot("t1", OutfitSlotRole.TOP, comfort_level=4, weather=["cold", "cool"])
    bot = _make_slot("b1", OutfitSlotRole.BOTTOM, comfort_level=4, weather=["cold", "cool"])
    shoes = _make_slot("s1", OutfitSlotRole.FOOTWEAR, comfort_level=4, weather=["cold", "cool"])
    coat_cold = _make_slot(
        "c_warm", OutfitSlotRole.OUTERWEAR, comfort_level=4,
        weather=["cold"], material="wool", flags=["insulated"]
    )

    score_with_coat = calculate_weather_comfort_fit([top, bot, shoes, coat_cold], weather_condition="cold")
    score_no_coat = calculate_weather_comfort_fit([top, bot, shoes], weather_condition="cold")

    assert score_with_coat >= 0.85
    assert score_no_coat < 0.60
    assert score_with_coat > score_no_coat


# ============================================================================
# 2. FUNCTIONAL FIT TESTS
# ============================================================================

def test_functional_fit_matches_target_tags():
    """Functional fit scores coverage of target functional tags (outdoor, sun, movement)."""
    top_sport = _make_slot("t_sport", OutfitSlotRole.TOP, flags=["movement", "sun"])
    pants_cargo = _make_slot("p_cargo", OutfitSlotRole.BOTTOM, flags=["movement", "outdoor"])
    shoes_sneaker = _make_slot("s_sneaker", OutfitSlotRole.FOOTWEAR, flags=["outdoor", "movement"])

    items = [top_sport, pants_cargo, shoes_sneaker]

    # Target: outdoor, sun, movement -> all 3 covered
    score_all_matched = calculate_functional_fit(items, target_functional_tags=["outdoor", "sun", "movement"])
    assert score_all_matched == 1.0

    # Target: water_resistant, rain -> neither covered
    score_unmatched = calculate_functional_fit(items, target_functional_tags=["water_resistant", "rain"])
    assert score_unmatched == 0.0

    # No functional requirement requested -> full score 1.0
    score_default = calculate_functional_fit(items, target_functional_tags=[])
    assert score_default == 1.0


# ============================================================================
# 3. CONTEXT AGENT INTENT & PROFILE DETECTION
# ============================================================================

def test_context_agent_intent_detection_profiles():
    """Context agent detects intent and activates the appropriate weight profile."""
    # 1. Wedding / Formal -> Formal Profile
    ctx_formal = extract_context("Tối nay tôi đi dự tiệc cưới trang trọng")
    assert ctx_formal.weight_profile == "formal"
    assert ctx_formal.target_formality_range[0] >= 3

    # 2. Hot day casual coffee -> Comfort Profile
    ctx_comfort = extract_context("Hôm nay trời nóng quá, đi cà phê bạn bè ưu tiên thoải mái")
    assert ctx_comfort.weight_profile == "comfort"

    # 3. Motorcycling under sun -> Active Profile + functional tags
    ctx_active = extract_context("Tôi đi xe máy ngoài trời nắng cần mặc gì?")
    assert ctx_active.weight_profile == "active"
    assert "outdoor" in ctx_active.target_functional_tags
    assert "sun" in ctx_active.target_functional_tags
    assert "movement" in ctx_active.target_functional_tags

    # 4. General / unspecified query -> Balanced Profile
    ctx_balanced = extract_context("Tôi đi làm công sở sáng nay")
    assert ctx_balanced.weight_profile == "balanced"


# ============================================================================
# 4. DYNAMIC WEIGHTING RE-RANKING CONTRAST SCENARIO
# ============================================================================

def test_dynamic_weighting_shifts_rankings_between_formal_and_comfort():
    """Verify that with the SAME wardrobe candidates, the Top-1 outfit shifts based on the context profile."""
    # Candidate A: Formal Luxury Suit (Aesthetic = 0.95, Formality = 5, Comfort = 2)
    top_formal = _make_slot("t_formal", OutfitSlotRole.TOP, style="formal", formality=5, comfort_level=2, weather=["cool"])
    bot_formal = _make_slot("b_formal", OutfitSlotRole.BOTTOM, style="formal", formality=5, comfort_level=2, weather=["cool"])
    shoe_formal = _make_slot("s_formal", OutfitSlotRole.FOOTWEAR, style="formal", formality=5, comfort_level=2, weather=["cool"])
    cand_formal = EvaluatedOutfit(
        items=[top_formal, bot_formal, shoe_formal],
        fashion_score=0.95,  # High Tier-2 aesthetic
        combination_id="formal_combo",
    )

    # Candidate B: Breezy Cotton Casual Set (Aesthetic = 0.85, Formality = 2, Comfort = 5)
    top_breezy = _make_slot("t_breezy", OutfitSlotRole.TOP, style="casual", formality=2, comfort_level=5, weather=["hot", "warm"])
    bot_breezy = _make_slot("b_breezy", OutfitSlotRole.BOTTOM, style="casual", formality=2, comfort_level=5, weather=["hot", "warm"])
    shoe_breezy = _make_slot("s_breezy", OutfitSlotRole.FOOTWEAR, style="casual", formality=2, comfort_level=5, weather=["hot", "warm"])
    cand_breezy = EvaluatedOutfit(
        items=[top_breezy, bot_breezy, shoe_breezy],
        fashion_score=0.85,  # Moderate Tier-2 aesthetic
        combination_id="breezy_combo",
    )

    candidates = [cand_formal, cand_breezy]

    # Scenario 1: Formal Wedding / Conference (weight_profile="formal", formality target [4, 5])
    ctx_wedding = StylistContext(
        occasion="wedding",
        time_of_day="evening",
        weather_condition="cool",
        target_formality_range=[4, 5],
        weight_profile="formal",
    )
    ranked_wedding, _ = rerank_evaluated_outfits(candidates, context=ctx_wedding)
    # Formal suit MUST be Rank 1 for wedding
    assert ranked_wedding[0].items[0].item_id == "t_formal"
    assert ranked_wedding[0].rank == 1

    # Scenario 2: Hot day cafe with friends (weight_profile="comfort", weather="hot", formality target [1, 2])
    ctx_hot_cafe = StylistContext(
        occasion="cafe",
        time_of_day="afternoon",
        weather_condition="hot",
        target_formality_range=[1, 2],
        weight_profile="comfort",
    )
    ranked_cafe, _ = rerank_evaluated_outfits(candidates, context=ctx_hot_cafe)
    # Breezy cotton set MUST be Rank 1 for hot cafe (comfort wins over pure aesthetic)
    assert ranked_cafe[0].items[0].item_id == "t_breezy"
    assert ranked_cafe[0].rank == 1


# ============================================================================
# 5. STYLIST GROUNDED EXPLANATION RATIONALE
# ============================================================================

def test_grounded_explanation_reflects_weight_profile_rationale():
    """Stylist explanation highlights the core reasoning according to the active profile."""
    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Sơ Mi Trắng")
    bot = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Tây Đen")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Giày Da Oxford")
    outfit = RankedOutfit(rank=1, composite_score=0.88, items=[top, bot, shoe])

    # Formal context
    ctx_formal = StylistContext(
        occasion="wedding",
        time_of_day="evening",
        weather_condition="cool",
        weight_profile="formal",
    )
    exp_formal = generate_grounded_explanation_vi(outfit, ctx_formal)
    assert "trang trọng, chỉn chu" in exp_formal

    # Comfort context
    ctx_comfort = StylistContext(
        occasion="cafe",
        time_of_day="afternoon",
        weather_condition="hot",
        weight_profile="comfort",
    )
    exp_comfort = generate_grounded_explanation_vi(outfit, ctx_comfort)
    assert "tối ưu sự thoải mái" in exp_comfort

    # Active context
    ctx_active = StylistContext(
        occasion="casual",
        time_of_day="morning",
        weather_condition="warm",
        weight_profile="active",
    )
    exp_active = generate_grounded_explanation_vi(outfit, ctx_active)
    assert "cơ động và bảo vệ" in exp_active
