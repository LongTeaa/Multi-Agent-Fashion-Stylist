from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.agents.personalization_agent import (
    AVOID_RELAXATION_WARNING,
    REPETITION_WARNING,
    calculate_learned_affinity,
    calculate_palette_preference,
    calculate_priority_preference,
    calculate_recent_wear_penalty,
    calculate_style_preference,
    check_outfit_avoid_violations,
    get_user_personalization_data,
    personalization_agent_node,
    rerank_evaluated_outfits,
)
from app.agents.state import (
    EvaluatedOutfit,
    OutfitItemSlot,
    RankedOutfit,
    StylistContext,
    StylistGraphState,
)
from app.models.entities import (
    OutfitItem,
    OutfitSlotRole,
    User,
    UserPreference,
    WardrobeCategory,
    WearLog,
)


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
) -> OutfitItemSlot:
    """Helper to create an OutfitItemSlot."""
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
        weather_suitability=weather or ["warm", "cool"],
        pattern=pattern,
        material=material,
        fit=fit,
        functional_flags=flags or [],
        times_worn=times_worn,
        last_worn_at=last_worn_at,
    )


def _make_evaluated_outfit(
    combo_id: str,
    items: list[OutfitItemSlot],
    fashion_score: float = 0.85,
) -> EvaluatedOutfit:
    return EvaluatedOutfit(
        items=items,
        fashion_score=fashion_score,
        component_scores={
            "color_score": 0.90,
            "style_score": 0.85,
            "formality_score": 0.80,
            "weather_environment_score": 0.85,
            "pattern_proportion_score": 0.85,
        },
        combination_id=combo_id,
    )


@pytest.fixture
def in_memory_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# ============================================================================
# 1. INPUT / OUTPUT BOUNDS & SLICING TESTS
# ============================================================================

def test_personalization_bounds_input_and_output():
    """Takes at most 5 candidates and outputs at most 3 ranked outfits."""
    slots = [
        _make_slot(f"t{i}", OutfitSlotRole.TOP) for i in range(7)
    ]
    candidates = [
        _make_evaluated_outfit(f"combo_{i}", [slots[i]], fashion_score=0.80 + i * 0.02)
        for i in range(7)
    ]

    ranked, warnings = rerank_evaluated_outfits(
        candidates,
        preferences=None,
        max_output=3,
    )

    # Output capped at 3
    assert len(ranked) == 3
    # Ranks assigned 1, 2, 3
    assert [r.rank for r in ranked] == [1, 2, 3]

    # Contract hardening: Caller passing max_output > 3 is clamped to 3
    ranked_clamped_max, _ = rerank_evaluated_outfits(candidates, max_output=10)
    assert len(ranked_clamped_max) == 3

    # Contract hardening: Caller passing max_output < 1 is clamped to 1
    ranked_clamped_min, _ = rerank_evaluated_outfits(candidates, max_output=0)
    assert len(ranked_clamped_min) == 1


def test_explicit_avoid_scans_full_fashion_pool_before_relaxing():
    violating = [
        _make_evaluated_outfit(
            f"black_{i}",
            [_make_slot(f"black-item-{i}", OutfitSlotRole.TOP, color="black")],
            fashion_score=1.0 - i * 0.01,
        )
        for i in range(5)
    ]
    clean = _make_evaluated_outfit(
        "clean_sixth",
        [_make_slot("white-item", OutfitSlotRole.TOP, color="white")],
        fashion_score=0.90,
    )
    preferences = UserPreference(user_id="user-avoid", avoid_colors=["black"])

    ranked, warnings = rerank_evaluated_outfits(
        [*violating, clean],
        preferences=preferences,
    )

    assert [[item.primary_color for item in outfit.items] for outfit in ranked] == [["white"]]
    assert AVOID_RELAXATION_WARNING not in warnings

def test_personalization_handles_empty_candidates():
    """Empty candidate input returns empty ranked list."""
    ranked, warnings = rerank_evaluated_outfits([], preferences=None)
    assert ranked == []
    assert warnings == []


# ============================================================================
# 2. COLD START DETERMINISM TESTS
# ============================================================================

def test_cold_start_neutral_scoring():
    """Missing user preferences produces neutral 0.50 preference score and preserves ranking."""
    top_a = _make_slot("t1", OutfitSlotRole.TOP)
    bot_a = _make_slot("b1", OutfitSlotRole.BOTTOM)
    cand_high_f = _make_evaluated_outfit("combo_high", [top_a, bot_a], fashion_score=0.90)

    top_b = _make_slot("t2", OutfitSlotRole.TOP)
    bot_b = _make_slot("b2", OutfitSlotRole.BOTTOM)
    cand_low_f = _make_evaluated_outfit("combo_low", [top_b, bot_b], fashion_score=0.70)

    ranked, warnings = rerank_evaluated_outfits([cand_low_f, cand_high_f], preferences=None)

    assert len(ranked) == 2
    # In neutral cold start: preference_score is 0.50
    assert ranked[0].personalization_score == 0.50
    # Higher fashion score ranks first: 0.60 * 0.90 + 0.40 * 0.50 = 0.74
    assert ranked[0].items[0].item_id == "t1"
    assert ranked[0].composite_score == 0.74
    assert ranked[1].items[0].item_id == "t2"
    assert ranked[1].composite_score == 0.62


# ============================================================================
# 3. STYLE & PALETTE PREFERENCE MATCHING
# ============================================================================

def test_style_preference_reranking():
    """Outfit matching user's preferred style gets reranked above mismatched outfit."""
    top_street = _make_slot("t_street", OutfitSlotRole.TOP, style="streetwear")
    bot_street = _make_slot("b_street", OutfitSlotRole.BOTTOM, style="streetwear")
    cand_street = _make_evaluated_outfit("combo_street", [top_street, bot_street], fashion_score=0.85)

    top_formal = _make_slot("t_formal", OutfitSlotRole.TOP, style="formal")
    bot_formal = _make_slot("b_formal", OutfitSlotRole.BOTTOM, style="formal")
    cand_formal = _make_evaluated_outfit("combo_formal", [top_formal, bot_formal], fashion_score=0.85)

    pref = UserPreference(
        user_id="user_1",
        styles=["streetwear"],
    )

    ranked, _ = rerank_evaluated_outfits([cand_formal, cand_street], preferences=pref)

    assert ranked[0].items[0].item_id == "t_street"
    assert ranked[0].rank == 1
    assert any("streetwear" in tag for tag in ranked[0].applied_preferences)


def test_palette_preference_earth_tone():
    """Outfit with earth tone colors scores higher when earth_tone is preferred."""
    items_earth = [
        _make_slot("t1", OutfitSlotRole.TOP, color="brown"),
        _make_slot("b1", OutfitSlotRole.BOTTOM, color="khaki"),
    ]
    items_cool = [
        _make_slot("t2", OutfitSlotRole.TOP, color="blue"),
        _make_slot("b2", OutfitSlotRole.BOTTOM, color="light_blue"),
    ]

    cand_earth = _make_evaluated_outfit("combo_earth", items_earth, fashion_score=0.80)
    cand_cool = _make_evaluated_outfit("combo_cool", items_cool, fashion_score=0.80)

    pref = UserPreference(
        user_id="user_1",
        color_palettes=["earth_tone"],
    )

    ranked, _ = rerank_evaluated_outfits([cand_cool, cand_earth], preferences=pref)
    assert ranked[0].items[0].item_id == "t1"
    assert any("đất" in tag for tag in ranked[0].applied_preferences)


# ============================================================================
# 4. PRIORITY MATCHING
# ============================================================================

def test_priority_preference_comfort_and_polished():
    """Comfort priority rewards relaxed fits and cotton; polished rewards formal/smart_casual."""
    items_comfort = [
        _make_slot("t1", OutfitSlotRole.TOP, style="casual", formality=1, material="cotton", fit="relaxed"),
        _make_slot("b1", OutfitSlotRole.BOTTOM, style="casual", formality=1, material="cotton", fit="relaxed"),
    ]
    items_formal = [
        _make_slot("t2", OutfitSlotRole.TOP, style="formal", formality=4, material="silk", fit="slim"),
        _make_slot("b2", OutfitSlotRole.BOTTOM, style="formal", formality=4, material="wool", fit="slim"),
    ]

    cand_comf = _make_evaluated_outfit("c_comf", items_comfort, fashion_score=0.80)
    cand_form = _make_evaluated_outfit("c_form", items_formal, fashion_score=0.80)

    pref_comf = UserPreference(user_id="u1", priorities=["comfort"])
    ranked_comf, _ = rerank_evaluated_outfits([cand_form, cand_comf], preferences=pref_comf)
    assert ranked_comf[0].items[0].item_id == "t1"

    pref_pol = UserPreference(user_id="u1", priorities=["polished"])
    ranked_pol, _ = rerank_evaluated_outfits([cand_form, cand_comf], preferences=pref_pol)
    assert ranked_pol[0].items[0].item_id == "t2"


# ============================================================================
# 5. EXPLICIT AVOID & CONTROLLED RELAXATION
# ============================================================================

def test_explicit_avoid_strict_filtering_when_clean_exists():
    """When at least one clean candidate exists, ALL violating candidates are filtered out.

    Even if 4 violating candidates have fashion_score 1.00 and 1 clean candidate has 0.70,
    the output MUST contain only the 1 clean candidate, and ZERO violating candidates in top 3!
    """
    cand_clean = _make_evaluated_outfit(
        "clean_1",
        [_make_slot("t_clean", OutfitSlotRole.TOP, color="white", style="casual")],
        fashion_score=0.70,
    )
    violating_cands = [
        _make_evaluated_outfit(
            f"violating_{i}",
            [_make_slot(f"t_v_{i}", OutfitSlotRole.TOP, color="yellow", style="casual")],
            fashion_score=1.00,
        )
        for i in range(4)
    ]

    pref = UserPreference(
        user_id="user_1",
        avoid_colors=["yellow"],
    )

    ranked, warnings = rerank_evaluated_outfits(
        violating_cands + [cand_clean],
        preferences=pref,
    )

    # Invariant: Explicit exclusions win. Only the clean candidate is returned!
    assert len(ranked) == 1
    assert ranked[0].items[0].item_id == "t_clean"
    assert AVOID_RELAXATION_WARNING not in warnings


def test_explicit_avoid_controlled_relaxation_when_all_violate():
    """When ALL candidate outfits violate avoid constraints, controlled relaxation applies."""
    cand1 = _make_evaluated_outfit(
        "c1",
        [_make_slot("t1", OutfitSlotRole.TOP, color="red")],
        fashion_score=0.85,
    )
    cand2 = _make_evaluated_outfit(
        "c2",
        [_make_slot("t2", OutfitSlotRole.TOP, color="red")],
        fashion_score=0.75,
    )

    pref = UserPreference(
        user_id="user_1",
        avoid_colors=["red"],
    )

    ranked, warnings = rerank_evaluated_outfits([cand1, cand2], preferences=pref)

    # Outfits are NOT discarded; relaxation warning is emitted
    assert len(ranked) == 2
    assert AVOID_RELAXATION_WARNING in warnings
    assert ranked[0].items[0].item_id == "t1"


# ============================================================================
# 6. ANTI-REPETITION PENALTIES (72h EXACT OUTFIT & 48h MAJOR ITEM)
# ============================================================================

def test_recent_wear_penalty_exact_outfit_within_72h():
    """Exact outfit worn in last 3 days receives strong penalty (-0.40)."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)

    items_worn = [
        _make_slot("t1", OutfitSlotRole.TOP),
        _make_slot("b1", OutfitSlotRole.BOTTOM),
        _make_slot("s1", OutfitSlotRole.FOOTWEAR),
    ]
    items_unworn = [
        _make_slot("t2", OutfitSlotRole.TOP),
        _make_slot("b2", OutfitSlotRole.BOTTOM),
        _make_slot("s2", OutfitSlotRole.FOOTWEAR),
    ]

    cand_worn = _make_evaluated_outfit("c_worn", items_worn, fashion_score=0.85)
    cand_unworn = _make_evaluated_outfit("c_unworn", items_unworn, fashion_score=0.85)

    recent_wear_data = {
        "exact_outfits_72h": [{"t1", "b1", "s1"}],
        "items_worn_48h": set(),
    }

    ranked, _ = rerank_evaluated_outfits(
        [cand_worn, cand_unworn],
        preferences=None,
        recent_wear_data=recent_wear_data,
        reference_time=now,
    )

    # Unworn candidate strictly beats the candidate worn yesterday
    assert ranked[0].items[0].item_id == "t2"
    assert ranked[1].items[0].item_id == "t1"
    assert ranked[1].composite_score < ranked[0].composite_score


def test_recent_wear_penalty_major_item_within_48h():
    """Major item worn within 48h receives -0.15 penalty per item."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)

    item_worn_recently = _make_slot(
        "t1", OutfitSlotRole.TOP, last_worn_at="2026-09-12T06:00:00Z"
    )
    item_worn_long_ago = _make_slot(
        "t2", OutfitSlotRole.TOP, last_worn_at="2026-09-01T00:00:00Z"
    )

    cand_recent = _make_evaluated_outfit("c_recent", [item_worn_recently], fashion_score=0.85)
    cand_old = _make_evaluated_outfit("c_old", [item_worn_long_ago], fashion_score=0.85)

    ranked, _ = rerank_evaluated_outfits(
        [cand_recent, cand_old],
        preferences=None,
        recent_wear_data={},
        reference_time=now,
    )

    assert ranked[0].items[0].item_id == "t2"
    assert ranked[1].items[0].item_id == "t1"


def test_small_wardrobe_repetition_warning_when_all_repeat():
    """When every candidate in a limited wardrobe repeats recent wear, emit warning without hard reject."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)

    cand1 = _make_evaluated_outfit(
        "c1",
        [_make_slot("t1", OutfitSlotRole.TOP, last_worn_at="2026-09-12T06:00:00Z")],
        fashion_score=0.85,
    )
    cand2 = _make_evaluated_outfit(
        "c2",
        [_make_slot("t2", OutfitSlotRole.TOP, last_worn_at="2026-09-12T08:00:00Z")],
        fashion_score=0.80,
    )

    ranked, warnings = rerank_evaluated_outfits(
        [cand1, cand2],
        preferences=None,
        recent_wear_data={},
        reference_time=now,
    )

    assert len(ranked) == 2
    assert REPETITION_WARNING in warnings


# ============================================================================
# 7. LEARNED RATING AFFINITY & THRESHOLD
# ============================================================================

def test_learned_rating_affinity_below_threshold_returns_neutral():
    """Before 5 ratings exist, learned rating affinity stays at neutral 0.50."""
    items = [_make_slot("t1", OutfitSlotRole.TOP, style="casual")]
    weights = {"version": 1, "weights": {"style:casual": 1.0}}

    # 4 ratings (< 5 threshold)
    score_4 = calculate_learned_affinity(items, weights, ratings_count=4)
    assert score_4 == 0.50

    # 5 ratings (>= 5 threshold)
    score_5 = calculate_learned_affinity(items, weights, ratings_count=5)
    # (1.0 + 1.0) / 2.0 = 1.0
    assert score_5 == 1.0


# ============================================================================
# 8. MULTI-USER ISOLATION (DATABASE INTEGRATION)
# ============================================================================

def test_multi_user_isolation(in_memory_session: Session):
    """User B's preferences and wear logs MUST NOT leak or affect User A."""
    now = datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)

    # Create User A and User B
    user_a = User(id="user_a", full_name="User A")
    user_b = User(id="user_b", full_name="User B")
    in_memory_session.add(user_a)
    in_memory_session.add(user_b)

    # User B has preference for formal style and avoid casual
    pref_b = UserPreference(
        user_id="user_b",
        styles=["formal"],
        avoid_styles=["casual"],
    )
    in_memory_session.add(pref_b)

    # User B has wear log for outfit with t1
    wear_b = WearLog(id="wear_b", user_id="user_b", outfit_id="outfit_b", worn_at=now)
    in_memory_session.add(wear_b)
    item_b = OutfitItem(outfit_id="outfit_b", wardrobe_item_id="t1", user_id="user_b", slot_role=OutfitSlotRole.TOP)
    in_memory_session.add(item_b)

    in_memory_session.commit()

    # Load data for User A (who has no preferences and no wear logs)
    pref_loaded_a, wear_data_a = get_user_personalization_data(
        in_memory_session, "user_a", reference_time=now
    )

    assert pref_loaded_a is None
    assert wear_data_a["exact_outfits_72h"] == []
    assert wear_data_a["items_worn_48h"] == set()

    # Load data for User B
    pref_loaded_b, wear_data_b = get_user_personalization_data(
        in_memory_session, "user_b", reference_time=now
    )
    assert pref_loaded_b is not None
    assert pref_loaded_b.styles == ["formal"]
    assert "t1" in wear_data_b["items_worn_48h"]


# ============================================================================
# 9. LANGGRAPH NODE EXECUTION
# ============================================================================

def test_personalization_agent_node_execution(in_memory_session: Session):
    """Verifies personalization_agent_node executes cleanly inside graph state."""
    user = User(id="user_demo")
    pref = UserPreference(
        user_id="user_demo",
        styles=["smart_casual"],
        color_palettes=["neutral"],
    )
    in_memory_session.add(user)
    in_memory_session.add(pref)
    in_memory_session.commit()

    items = [
        _make_slot("t1", OutfitSlotRole.TOP, style="smart_casual", color="white"),
        _make_slot("b1", OutfitSlotRole.BOTTOM, style="smart_casual", color="black"),
        _make_slot("s1", OutfitSlotRole.FOOTWEAR, style="smart_casual", color="white"),
    ]
    cand = _make_evaluated_outfit("c1", items, fashion_score=0.88)

    ctx = StylistContext(occasion="cafe", time_of_day="morning", weather_condition="cool")

    state: StylistGraphState = {
        "user_id": "user_demo",
        "evaluated_outfits": [cand],
        "context": ctx,
        "warnings": [],
    }

    result = personalization_agent_node(state, session=in_memory_session)

    assert "ranked_outfits" in result
    ranked = result["ranked_outfits"]
    assert len(ranked) == 1
    assert ranked[0].rank == 1
    assert ranked[0].composite_score > 0.80
    assert any("smart_casual" in p for p in ranked[0].applied_preferences)
    assert any("trung tính" in p for p in ranked[0].applied_preferences)


def test_personalization_agent_node_db_error_reports_error():
    """When DB query fails, personalization_agent_node emits error instead of hiding it."""
    class BrokenSession:
        def get(self, *args, **kwargs):
            raise RuntimeError("DB connection dropped")

        def exec(self, *args, **kwargs):
            raise RuntimeError("DB connection dropped")

    state: StylistGraphState = {
        "user_id": "u1",
        "evaluated_outfits": [_make_evaluated_outfit("c1", [_make_slot("t1", OutfitSlotRole.TOP)])],
        "errors": [],
        "warnings": [],
    }

    result = personalization_agent_node(state, session=BrokenSession())  # type: ignore[arg-type]
    assert "ranked_outfits" in result
    assert result["ranked_outfits"] == []
    assert result["errors"] == ["PERSONALIZATION_DB_ERROR"]
    assert "DB connection dropped" not in str(result["errors"])
