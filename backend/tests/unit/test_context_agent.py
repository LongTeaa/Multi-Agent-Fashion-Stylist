from __future__ import annotations

from datetime import date, timedelta
import pytest
from pydantic import ValidationError

from app.agents.context_agent import (
    CLARIFICATION_PROMPT_VI,
    context_agent_node,
    extract_context,
    is_ambiguous_query,
)
from app.agents.state import (
    EvaluatedOutfit,
    OutfitItemSlot,
    RankedOutfit,
    StylistContext,
    StylistGraphState,
)
from app.models.entities import OutfitSlotRole, WardrobeCategory


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
    """Verify extraction of location and outdoor environment."""
    query = "Tối nay đi cafe ngoài trời ở Đà Lạt, hơi lạnh, muốn lịch sự nhẹ"
    ctx = extract_context(query)

    assert ctx.occasion == "cafe"
    assert ctx.time_of_day == "evening"
    assert ctx.location_text == "Đà Lạt"
    assert ctx.environment == "outdoor"
    assert ctx.weather_condition == "cool"
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


@pytest.mark.parametrize(
    "ambiguous_query",
    [
        "Mặc gì bây giờ?",
        "Hôm nay mặc gì?",
        "Mặc gì?",
        "Tư vấn phối đồ",
        "Gợi ý đồ cho tôi",
        "Tôi nên mặc gì đây?",
    ],
)
def test_ambiguous_queries_trigger_clarification(ambiguous_query: str):
    """Verify ambiguous queries trigger the safeguard clarification prompt."""
    assert is_ambiguous_query(ambiguous_query) is True

    ctx = extract_context(ambiguous_query)
    assert ctx.needs_clarification is True
    assert ctx.clarification_question == CLARIFICATION_PROMPT_VI
    assert "Bạn dự định" in ctx.clarification_question


def test_state_models_validation():
    """Verify validation and serialization of state models."""
    ctx = StylistContext(
        occasion="cafe",
        time_of_day="evening",
        weather_condition="cool",
        target_formality_range=[2, 3],
    )
    assert ctx.occasion == "cafe"
    assert ctx.target_formality_range == [2, 3]

    # Invalid range boundaries
    with pytest.raises(ValidationError):
        StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[4, 2],  # min > max
        )

    with pytest.raises(ValidationError):
        StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[0, 3],  # 0 < 1
        )

    # Test OutfitItemSlot
    slot = OutfitItemSlot(
        item_id="item-top-01",
        slot_role=OutfitSlotRole.TOP,
        name="Áo polo trắng",
        primary_color="white",
        style="smart_casual",
        category=WardrobeCategory.TOP,
    )
    assert slot.item_id == "item-top-01"
    assert slot.slot_role == OutfitSlotRole.TOP

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
    """Verify context_agent_node function in LangGraph workflow."""
    initial_state: StylistGraphState = {
        "request_id": "req-123",
        "user_id": "user-456",
        "user_query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?",
    }

    result = context_agent_node(initial_state)
    assert "context" in result
    extracted_ctx = result["context"]
    assert isinstance(extracted_ctx, StylistContext)
    assert extracted_ctx.occasion == "cafe"
    assert extracted_ctx.weather_condition == "cool"
    assert extracted_ctx.needs_clarification is False
