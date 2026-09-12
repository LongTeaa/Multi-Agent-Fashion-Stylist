from __future__ import annotations

from datetime import date, timedelta
import pytest
from pydantic import ValidationError

from app.agents.context_agent import (
    CLARIFICATION_PROMPT_VI,
    context_agent_node,
    extract_context,
    extract_context_with_providers,
    is_ambiguous_query,
)
from app.agents.state import (
    EvaluatedOutfit,
    GarmentConstraint,
    OutfitItemSlot,
    RankedOutfit,
    StylistContext,
    StylistGraphState,
)
from app.models.entities import OutfitSlotRole, WardrobeCategory
from app.services.fakes.context_fakes import FakeLLMProvider, FakeWeatherProvider


def test_golden_scenario_query():
    """Verify context extraction for the Phase 4 Golden Scenario prompt."""
    query = "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?"
    ctx = extract_context(query)

    assert ctx.occasion == "cafe"
    assert ctx.time_of_day == "evening"
    assert ctx.weather_condition == "cool"
    assert ctx.weather_source == "user"
    assert ctx.target_formality_range == [2, 3]
    assert ctx.needs_clarification is False
    assert ctx.clarification_question is None


def test_context_provider_and_weather_enrichment_are_injectable():
    ctx, warnings = extract_context_with_providers(
        "Ngày mai đi cafe ở Đà Lạt",
        current_date=date(2026, 9, 12),
        llm_provider=FakeLLMProvider("valid"),
        weather_provider=FakeWeatherProvider("success"),
    )

    assert warnings == []
    assert ctx.location_text == "Đà Lạt"
    assert ctx.event_date == "2026-09-13"
    assert ctx.weather_condition == "cold"
    assert ctx.temperature_celsius == 18.0
    assert ctx.weather_source == "api"


def test_fake_context_provider_maps_underspecified_query_to_clarification():
    ctx, warnings = extract_context_with_providers(
        "Mặc gì?",
        current_date=date(2026, 9, 12),
        llm_provider=FakeLLMProvider("valid"),
    )

    assert warnings == []
    assert ctx.needs_clarification is True
    assert ctx.confidence < 0.5
    assert ctx.clarification_question


def test_user_weather_takes_precedence_over_weather_provider():
    ctx, warnings = extract_context_with_providers(
        "Ngày mai đi cafe ở Đà Lạt, trời nóng",
        current_date=date(2026, 9, 12),
        llm_provider=FakeLLMProvider("valid"),
        weather_provider=FakeWeatherProvider("success"),
    )

    assert warnings == []
    assert ctx.weather_condition == "hot"
    assert ctx.weather_source == "user"
    assert ctx.temperature_celsius is None


@pytest.mark.parametrize("scenario", ["malformed", "timeout", "provider_error"])
def test_context_provider_failure_uses_rule_based_fallback(scenario: str):
    ctx, warnings = extract_context_with_providers(
        "Tối nay đi cafe, trời mát",
        current_date=date(2026, 9, 12),
        llm_provider=FakeLLMProvider(scenario),
    )

    assert ctx.occasion == "cafe"
    assert ctx.weather_condition == "cool"
    assert ctx.weather_source == "user"
    assert warnings


@pytest.mark.parametrize("scenario", ["timeout", "unknown_location", "provider_error"])
def test_weather_provider_failure_preserves_default_and_warns(scenario: str):
    ctx, warnings = extract_context_with_providers(
        "Ngày mai đi cafe ở Đà Lạt",
        current_date=date(2026, 9, 12),
        llm_provider=FakeLLMProvider("valid"),
        weather_provider=FakeWeatherProvider(scenario),
    )

    assert ctx.weather_source == "default"
    assert ctx.weather_condition == "cool"
    assert warnings


def test_work_office_query():
    """Verify extraction for office/work scenario."""
    query = "Sáng mai đi làm văn phòng, trời nóng nực, cần lịch sự"
    today = date(2026, 9, 11)
    ctx = extract_context(query, current_date=today)

    assert ctx.occasion == "daily_work"
    assert ctx.time_of_day == "morning"
    assert ctx.event_date == (today + timedelta(days=1)).isoformat()
    assert ctx.weather_condition == "hot"
    assert ctx.weather_source == "user"
    assert ctx.target_formality_range == [3, 4]
    assert ctx.environment == "indoor"
    assert ctx.needs_clarification is False


def test_wedding_query():
    """Verify extraction for formal wedding event."""
    query = "Cuối tuần đi ăn cưới bạn thân ở nhà hàng sang trọng, trời mát mẻ"
    ctx = extract_context(query)

    assert ctx.occasion == "wedding"
    assert ctx.weather_condition == "cool"
    assert ctx.weather_source == "user"
    assert ctx.target_formality_range == [4, 5]
    assert ctx.needs_clarification is False
    assert ctx.event_date is None  # Unspecified date defaults to None


def test_interview_query():
    """Verify extraction for job interview."""
    query = "Sáng mai đi phỏng vấn xin việc, trời nắng, ăn mặc chỉn chu"
    ctx = extract_context(query)

    assert ctx.occasion == "interview"
    assert ctx.time_of_day == "morning"
    assert ctx.weather_condition == "hot"
    assert ctx.target_formality_range == [4, 5]
    assert ctx.needs_clarification is False


def test_location_and_environment():
    """Verify extraction of location and outdoor environment matching API_CONTRACT.md."""
    query = "Tối nay đi cafe ngoài trời ở Đà Lạt, hơi lạnh, muốn lịch sự nhẹ"
    ctx = extract_context(query)

    assert ctx.occasion == "cafe"
    assert ctx.time_of_day == "evening"
    assert ctx.location_text == "Đà Lạt"
    assert ctx.environment == "outdoor"
    assert ctx.weather_condition == "cold"  # API_CONTRACT.md maps 'hơi lạnh' to cold
    assert ctx.weather_source == "user"
    assert ctx.target_formality_range == [2, 3]
    assert "smart_casual" in ctx.style_hints
    assert "lịch sự nhẹ" in ctx.vibe_keywords
    assert ctx.must_have == []
    assert ctx.must_avoid == []
    assert ctx.needs_clarification is False


def test_explicit_constraints():
    """Verify extraction of must_have and must_avoid constraints."""
    query = "Đi cafe tối nay trời se lạnh, không mặc màu đen, thích áo polo"
    ctx = extract_context(query)

    assert ctx.occasion == "cafe"
    assert ctx.weather_condition == "cool"
    assert "màu đen" in ctx.must_avoid
    assert "áo polo" in ctx.must_have
    assert ctx.needs_clarification is False


def test_rain_priority_over_temperature():
    """Verify rainy weather has top priority over cool/cold for garment safety."""
    query = "Tối nay đi cafe với bạn, trời mưa và se lạnh"
    ctx = extract_context(query)
    assert ctx.weather_condition == "rainy"
    assert ctx.weather_source == "user"


def test_multiple_constraints_connected_by_va():
    """Verify parser extracts multiple constraints connected by 'và'."""
    query = "Đi cafe tối nay, phải mặc áo polo và giày sneaker, không mặc màu đen"
    ctx = extract_context(query)
    assert "áo polo" in ctx.must_have
    assert "giày sneaker" in ctx.must_have
    assert "màu đen" in ctx.must_avoid


def test_isolated_garment_triggers_clarification():
    """Verify isolated garment question without occasion/context triggers clarification."""
    query = "Áo nào hợp với tôi?"
    assert is_ambiguous_query(query) is True
    ctx = extract_context(query)
    assert ctx.needs_clarification is True
    assert ctx.confidence == 0.3


@pytest.mark.parametrize(
    "ambiguous_query",
    [
        "Mặc gì bây giờ?",
        "Hôm nay mặc gì?",
        "Mặc gì?",
        "Tư vấn phối đồ",
        "Gợi ý đồ cho tôi",
        "Tôi nên mặc gì đây?",
        "Cho mình xin vài gợi ý phối đồ với",
    ],
)
def test_ambiguous_queries_trigger_clarification(ambiguous_query: str):
    """Verify ambiguous queries trigger the safeguard clarification prompt."""
    assert is_ambiguous_query(ambiguous_query) is True

    ctx = extract_context(ambiguous_query)
    assert ctx.needs_clarification is True
    assert ctx.clarification_question == CLARIFICATION_PROMPT_VI
    assert ctx.confidence == 0.3
    assert "Bạn dự định" in ctx.clarification_question


def test_state_models_validation():
    """Verify validation and serialization of state models."""
    ctx = StylistContext(
        occasion="cafe",
        time_of_day="evening",
        weather_condition="cool",
        target_formality_range=[2, 3],
        confidence=0.9,
    )
    assert ctx.occasion == "cafe"
    assert ctx.target_formality_range == [2, 3]
    assert ctx.confidence == 0.9

    # Invalid range boundaries
    with pytest.raises(ValidationError):
        StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[4, 2],
        )

    # Test OutfitItemSlot with full metadata
    slot = OutfitItemSlot(
        item_id="item-top-01",
        slot_role=OutfitSlotRole.TOP,
        name="Áo polo trắng",
        primary_color="white",
        secondary_color="navy",
        style="smart_casual",
        category=WardrobeCategory.TOP,
        formality_level=3,
        weather_suitability=["warm", "cool"],
        pattern="solid",
        material="cotton",
        fit="regular",
        functional_flags=["breathable"],
    )
    assert slot.item_id == "item-top-01"
    assert slot.slot_role == OutfitSlotRole.TOP
    assert slot.formality_level == 3
    assert slot.functional_flags == ["breathable"]

    # Slot role mismatch with category raises validation error
    with pytest.raises(ValidationError):
        OutfitItemSlot(
            item_id="item-top-02",
            slot_role=OutfitSlotRole.BOTTOM,
            name="Áo polo",
            primary_color="white",
            style="casual",
            category=WardrobeCategory.TOP,
        )

    # Test EvaluatedOutfit
    eval_outfit = EvaluatedOutfit(
        items=[slot],
        fashion_score=0.92,
        component_scores={"color": 0.95, "style": 0.90},
        combination_id="combo-1",
    )
    assert eval_outfit.fashion_score == 0.92

    # Test RankedOutfit
    ranked = RankedOutfit(
        outfit_id="outfit-uuid-1",
        rank=1,
        composite_score=0.91,
        items=[slot],
        explanation_vi="Set đồ rất phù hợp.",
        applied_preferences=["Ưu tiên polo"],
    )
    assert ranked.rank == 1
    assert ranked.composite_score == 0.91


def test_context_agent_node():
    """Verify context_agent_node function in LangGraph workflow receives location."""
    initial_state: StylistGraphState = {
        "request_id": "req-123",
        "user_id": "user-456",
        "user_query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?",
        "location": "Đà Lạt",
    }

    result = context_agent_node(initial_state)
    assert "context" in result
    extracted_ctx = result["context"]
    assert isinstance(extracted_ctx, StylistContext)
    assert extracted_ctx.occasion == "cafe"
    assert extracted_ctx.weather_condition == "cool"
    assert extracted_ctx.location_text == "Đà Lạt"
    assert extracted_ctx.needs_clarification is False
    assert extracted_ctx.confidence == 0.95


def test_negation_handling_weather_and_occasion():
    """Verify negation handling prevents false positive classification."""
    query_weather = "Tối nay đi cafe với bạn, trời không lạnh, không mưa đâu"
    ctx_weather = extract_context(query_weather)
    assert ctx_weather.weather_condition != "cold"
    assert ctx_weather.weather_condition != "rainy"
    assert ctx_weather.occasion == "cafe"

    query_work = "Hôm nay nghỉ làm, đi chơi dạo phố với bạn"
    ctx_work = extract_context(query_work)
    assert ctx_work.occasion == "casual"


def test_outerwear_and_dress_constraint_extraction():
    """Verify specific garments like áo khoác, áo blazer, váy đầm are preserved without falling back to generic 'áo'."""
    query = "Đi làm ngày mai, phải mặc áo khoác và váy đầm, không mặc áo blazer"
    ctx = extract_context(query)
    assert "áo khoác" in ctx.must_have
    assert "áo" not in ctx.must_have
    assert "váy đầm" in ctx.must_have
    assert "áo blazer" in ctx.must_avoid
    assert "áo" not in ctx.must_avoid


def test_weather_time_without_occasion_triggers_clarification():
    """Verify queries with only weather and time but no occasion/location/garment trigger clarification."""
    query = "Tối nay trời mát mặc gì?"
    assert is_ambiguous_query(query) is True
    ctx = extract_context(query)
    assert ctx.needs_clarification is True
    assert ctx.confidence == 0.3

    query2 = "Hôm nay trời lạnh nên mặc gì?"
    assert is_ambiguous_query(query2) is True
    ctx2 = extract_context(query2)
    assert ctx2.needs_clarification is True
    assert ctx2.confidence == 0.3


def test_structured_garment_color_binding():
    """Verify structured constraint preserves garment + color binding and avoids false cross-slot bans."""
    query = "Đi làm ngày mai, phải mặc áo polo trắng, không mặc áo polo đen"
    ctx = extract_context(query)

    # Check structured must_have
    assert len(ctx.structured_must_have) == 1
    c_have = ctx.structured_must_have[0]
    assert c_have.category == WardrobeCategory.TOP
    assert c_have.sub_category == "polo"
    assert c_have.color == "white"

    # Check structured must_avoid
    assert len(ctx.structured_must_avoid) == 1
    c_avoid = ctx.structured_must_avoid[0]
    assert c_avoid.category == WardrobeCategory.TOP
    assert c_avoid.sub_category == "polo"
    assert c_avoid.color == "black"


def test_taxonomy_garment_category_mappings():
    """Verify specific garment taxonomy mappings: giày da -> leather, áo vest -> outerwear blazer, giày -> category_only."""
    query = "Đi tiệc tối nay, phải mặc áo vest và giày da, phải mặc quần"
    ctx = extract_context(query)

    # Áo vest must be OUTERWEAR, blazer
    vest_constraints = [c for c in ctx.structured_must_have if "vest" in c.raw_text]
    assert len(vest_constraints) == 1
    assert vest_constraints[0].category == WardrobeCategory.OUTERWEAR
    assert vest_constraints[0].sub_category == "blazer"

    # Giày da must be FOOTWEAR, material leather
    shoes_constraints = [c for c in ctx.structured_must_have if "giày da" in c.raw_text]
    assert len(shoes_constraints) == 1
    assert shoes_constraints[0].category == WardrobeCategory.FOOTWEAR
    assert shoes_constraints[0].material == "leather"

    # Quần must be category_only
    pants_constraints = [c for c in ctx.structured_must_have if c.raw_text == "quần"]
    assert len(pants_constraints) == 1
    assert pants_constraints[0].category == WardrobeCategory.BOTTOM
    assert pants_constraints[0].is_category_only is True


def test_location_without_occasion_triggers_clarification():
    """Verify query with only location (no occasion, no garment/style) triggers clarification."""
    query = "Ở Đà Lạt mặc gì?"
    assert is_ambiguous_query(query) is True
    ctx = extract_context(query)
    assert ctx.needs_clarification is True
    assert ctx.confidence == 0.3


def test_garment_with_defaulted_occasion_calibrates_confidence():
    """Verify query with garment constraint but missing occasion uses safe default and lowers confidence."""
    query = "Áo polo nào hợp tối nay?"
    assert is_ambiguous_query(query) is False
    ctx = extract_context(query)
    assert ctx.needs_clarification is False
    assert ctx.occasion == "casual"
    # occasion defaulted (-0.15) and weather defaulted (-0.10) => 0.95 - 0.25 = 0.70
    assert ctx.confidence == 0.70
