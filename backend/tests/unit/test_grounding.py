from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.agents.coordinator import (
    COORDINATOR_PERSISTENCE_ERROR,
    COORDINATOR_RULE_VERSION,
    COORDINATOR_STATE_INVALID,
    GROUNDING_VALIDATION_FAILED,
    canonicalize_and_validate_pool,
    coordinator_node,
    generate_grounded_explanation_vi,
    persist_recommendations_atomically,
    validate_coordinator_input_state,
    validate_database_active_ownership,
    validate_outfit_completeness,
)
from app.agents.state import (
    OutfitItemSlot,
    RankedOutfit,
    StylistContext,
    StylistGraphState,
)
from app.models.entities import (
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    User,
    WardrobeCategory,
    WardrobeItem,
)


# ============================================================================
# TEST FIXTURES & HELPERS
# ============================================================================

from app.core.database import create_database_engine

@pytest.fixture
def db_session():
    """In-memory SQLite database session with PRAGMA foreign_keys=ON enabled."""
    engine = create_database_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


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
        weather_suitability=weather or ["cool", "warm"],
        pattern=pattern,
        material=material,
        fit=fit,
    )


def _seed_wardrobe_item(
    session: Session,
    item_id: str,
    user_id: str,
    category: WardrobeCategory,
    name: str = "Item",
    is_active: bool = True,
    deleted_at: datetime | None = None,
) -> WardrobeItem:
    item = WardrobeItem(
        id=item_id,
        user_id=user_id,
        category=category,
        sub_category="generic",
        primary_color="white",
        pattern="solid",
        material="cotton",
        style="smart_casual",
        fit="regular",
        formality_level=3,
        season=["all"],
        weather_suitability=["cool", "warm"],
        functional_flags=[],
        free_text_tags=[],
        field_confidence={},
        is_active=is_active,
        is_user_confirmed=True,
        deleted_at=deleted_at,
    )
    session.add(item)
    session.commit()
    return item


def _make_ranked_outfit(
    rank: int,
    items: list[OutfitItemSlot],
    fashion_score: float = 0.85,
    personalization_score: float = 0.80,
    composite_score: float = 0.83,
    applied_preferences: list[str] | None = None,
) -> RankedOutfit:
    return RankedOutfit(
        outfit_id=None,
        rank=rank,
        composite_score=composite_score,
        fashion_score=fashion_score,
        personalization_score=personalization_score,
        items=items,
        explanation_vi="",
        applied_preferences=applied_preferences or [],
    )


def _make_context(
    occasion: str = "cafe",
    time_of_day: str = "evening",
    weather_condition: str = "cool",
) -> StylistContext:
    return StylistContext(
        occasion=occasion,
        time_of_day=time_of_day,
        weather_condition=weather_condition,
    )


# ============================================================================
# 1. INPUT STATE PRE-FLIGHT VALIDATION TESTS
# ============================================================================

def test_coordinator_state_validation_missing_user_id():
    state: StylistGraphState = {
        "user_id": "",
        "request_id": "req-1",
        "user_query": "mặc gì đi chơi",
        "context": _make_context(occasion="cafe"),
        "candidate_pool": {},
        "ranked_outfits": [_make_ranked_outfit(1, [_make_slot("t1", OutfitSlotRole.TOP), _make_slot("b1", OutfitSlotRole.BOTTOM)])],
    }
    valid, err = validate_coordinator_input_state(state)
    assert not valid
    assert "user_id" in err


def test_coordinator_state_validation_missing_context():
    state: StylistGraphState = {
        "user_id": "u1",
        "request_id": "req-1",
        "user_query": "mặc gì đi chơi",
        "context": None,
        "candidate_pool": {},
        "ranked_outfits": [_make_ranked_outfit(1, [_make_slot("t1", OutfitSlotRole.TOP), _make_slot("b1", OutfitSlotRole.BOTTOM)])],
    }
    valid, err = validate_coordinator_input_state(state)
    assert not valid
    assert "context" in err


def test_coordinator_state_validation_missing_scores():
    outfit = _make_ranked_outfit(1, [_make_slot("t1", OutfitSlotRole.TOP), _make_slot("b1", OutfitSlotRole.BOTTOM)])
    outfit.fashion_score = None  # Non-null in OutfitRecommendation table

    state: StylistGraphState = {
        "user_id": "u1",
        "request_id": "req-1",
        "user_query": "mặc gì đi chơi",
        "context": _make_context(occasion="cafe"),
        "candidate_pool": {},
        "ranked_outfits": [outfit],
    }
    valid, err = validate_coordinator_input_state(state)
    assert not valid
    assert "fashion_score" in err


def test_coordinator_state_validation_empty_ranked_outfits():
    state: StylistGraphState = {
        "user_id": "u1",
        "request_id": "req-1",
        "user_query": "mặc gì đi chơi",
        "context": _make_context(occasion="cafe"),
        "candidate_pool": {},
        "ranked_outfits": [],
    }
    valid, err = validate_coordinator_input_state(state)
    assert not valid
    assert "ranked_outfits" in err


# ============================================================================
# 2. CANDIDATE POOL GROUNDING & ANTI-TAMPERING TESTS
# ============================================================================

def test_candidate_pool_grounding_success():
    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Polo Trắng")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Chinos Xanh")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneaker Trắng")

    candidate_pool = {
        "tops": [top],
        "bottoms": [bottom],
        "footwear": [shoe],
    }
    outfit = _make_ranked_outfit(1, [top, bottom, shoe])

    valid, canonical_outfits, err = canonicalize_and_validate_pool([outfit], candidate_pool)
    assert valid
    assert err is None
    assert len(canonical_outfits) == 1
    assert len(canonical_outfits[0].items) == 3


def test_candidate_pool_grounding_rejects_hallucinated_item_id():
    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Polo Trắng")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Chinos Xanh")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneaker Trắng")
    hallucinated = _make_slot("ghost_999", OutfitSlotRole.OUTERWEAR, name="Áo Khoác Vô Hình")

    candidate_pool = {
        "tops": [top],
        "bottoms": [bottom],
        "footwear": [shoe],
    }
    outfit = _make_ranked_outfit(1, [top, bottom, shoe, hallucinated])

    valid, canonical_outfits, err = canonicalize_and_validate_pool([outfit], candidate_pool)
    assert not valid
    assert "ghost_999" in err
    assert canonical_outfits == []


def test_candidate_pool_anti_tampering_canonicalizes_metadata():
    """If upstream mutates item name or properties, Coordinator canonicalizes from pool."""
    genuine_top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Thun Basic Trắng")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Kaki Đen")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Giày Lười")

    candidate_pool = {
        "tops": [genuine_top],
        "bottoms": [bottom],
        "footwear": [shoe],
    }

    # Upstream altered the item name to a fake luxury item
    tampered_top = _make_slot("t1", OutfitSlotRole.TOP, name="Fake Diamond Silk Shirt")
    outfit = _make_ranked_outfit(1, [tampered_top, bottom, shoe])

    valid, canonical_outfits, err = canonicalize_and_validate_pool([outfit], candidate_pool)
    assert valid
    assert err is None
    # Verifies the item slot in canonical_outfits has the genuine name, not the fake one
    assert canonical_outfits[0].items[0].name == "Áo Thun Basic Trắng"
    assert canonical_outfits[0].items[0].name != "Fake Diamond Silk Shirt"


# ============================================================================
# 3. DATABASE ACTIVE OWNERSHIP VALIDATOR TESTS
# ============================================================================

def test_database_ownership_success(db_session: Session):
    user_a = User(id="user_a")
    db_session.add(user_a)
    db_session.commit()

    _seed_wardrobe_item(db_session, "t1", "user_a", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b1", "user_a", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s1", "user_a", WardrobeCategory.FOOTWEAR)

    valid, err = validate_database_active_ownership(db_session, "user_a", {"t1", "b1", "s1"})
    assert valid
    assert err is None


def test_database_ownership_cross_user_fails(db_session: Session):
    user_a = User(id="user_a")
    user_b = User(id="user_b")
    db_session.add_all([user_a, user_b])
    db_session.commit()

    _seed_wardrobe_item(db_session, "t1", "user_a", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b1", "user_b", WardrobeCategory.BOTTOM)  # Owned by User B!

    valid, err = validate_database_active_ownership(db_session, "user_a", {"t1", "b1"})
    assert not valid
    assert "b1" in err
    assert "user_a" in err


def test_database_ownership_inactive_item_fails(db_session: Session):
    user_a = User(id="user_a")
    db_session.add(user_a)
    db_session.commit()

    _seed_wardrobe_item(db_session, "t1", "user_a", WardrobeCategory.TOP, is_active=False)

    valid, err = validate_database_active_ownership(db_session, "user_a", {"t1"})
    assert not valid
    assert "t1" in err


def test_database_ownership_soft_deleted_item_fails(db_session: Session):
    user_a = User(id="user_a")
    db_session.add(user_a)
    db_session.commit()

    _seed_wardrobe_item(
        db_session,
        "t1",
        "user_a",
        WardrobeCategory.TOP,
        deleted_at=datetime.now(timezone.utc),
    )

    valid, err = validate_database_active_ownership(db_session, "user_a", {"t1"})
    assert not valid
    assert "t1" in err


# ============================================================================
# 4. OUTFIT COMPLETENESS & MUTUAL EXCLUSIVITY TESTS
# ============================================================================

def test_outfit_completeness_valid_top_bottom_footwear():
    items = [
        _make_slot("t1", OutfitSlotRole.TOP),
        _make_slot("b1", OutfitSlotRole.BOTTOM),
        _make_slot("s1", OutfitSlotRole.FOOTWEAR),
    ]
    valid, err = validate_outfit_completeness(items)
    assert valid
    assert err is None


def test_outfit_completeness_valid_dress_footwear():
    items = [
        _make_slot("d1", OutfitSlotRole.DRESS),
        _make_slot("s1", OutfitSlotRole.FOOTWEAR),
    ]
    valid, err = validate_outfit_completeness(items)
    assert valid
    assert err is None


def test_outfit_completeness_with_outerwear_and_accessory():
    items = [
        _make_slot("t1", OutfitSlotRole.TOP),
        _make_slot("b1", OutfitSlotRole.BOTTOM),
        _make_slot("s1", OutfitSlotRole.FOOTWEAR),
        _make_slot("o1", OutfitSlotRole.OUTERWEAR),
        _make_slot("a1", OutfitSlotRole.ACCESSORY),
    ]
    valid, err = validate_outfit_completeness(items)
    assert valid
    assert err is None


def test_outfit_completeness_multiple_footwear_fails():
    """Reviewer hardening point 1: exactly 1 footwear required, never multiple."""
    items = [
        _make_slot("t1", OutfitSlotRole.TOP),
        _make_slot("b1", OutfitSlotRole.BOTTOM),
        _make_slot("s1", OutfitSlotRole.FOOTWEAR),
        _make_slot("s2", OutfitSlotRole.FOOTWEAR),  # 2nd shoe!
    ]
    valid, err = validate_outfit_completeness(items)
    assert not valid
    assert "must have exactly 1 footwear" in err


def test_outfit_completeness_zero_footwear_fails():
    items = [
        _make_slot("t1", OutfitSlotRole.TOP),
        _make_slot("b1", OutfitSlotRole.BOTTOM),
    ]
    valid, err = validate_outfit_completeness(items)
    assert not valid
    assert "must have exactly 1 footwear" in err


def test_outfit_completeness_dress_and_top_fails():
    items = [
        _make_slot("d1", OutfitSlotRole.DRESS),
        _make_slot("t1", OutfitSlotRole.TOP),
        _make_slot("s1", OutfitSlotRole.FOOTWEAR),
    ]
    valid, err = validate_outfit_completeness(items)
    assert not valid
    assert "cannot combine dress with top or bottom" in err


def test_outfit_completeness_missing_bottom_fails():
    items = [
        _make_slot("t1", OutfitSlotRole.TOP),
        _make_slot("s1", OutfitSlotRole.FOOTWEAR),
    ]
    valid, err = validate_outfit_completeness(items)
    assert not valid
    assert "missing required top or bottom" in err


# ============================================================================
# 5. DETERMINISTIC GROUNDED VIETNAMESE EXPLANATION TESTS
# ============================================================================

def test_grounded_explanation_mentions_only_canonical_items():
    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Polo Trắng")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Chinos Xanh Navy")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneaker Trắng")

    outfit = _make_ranked_outfit(
        1,
        [top, bottom, shoe],
        applied_preferences=["Bảng màu trung tính theo sở thích", "ưu tiên sự thoải mái"],
    )
    context = _make_context(occasion="cafe", weather_condition="cool", time_of_day="evening")

    explanation = generate_grounded_explanation_vi(outfit, context)

    # Contains exactly the item names present
    assert "[Áo Polo Trắng]" in explanation
    assert "[Quần Chinos Xanh Navy]" in explanation
    assert "[Sneaker Trắng]" in explanation

    # Does not contain foreign items or hallucinated fabrics
    assert "Áo Khoác" not in explanation
    assert "Lụa tơ tằm" not in explanation
    assert "Váy" not in explanation

    # Retains allowlisted preferences without repeating the extracted context
    assert "Bảng màu trung tính theo sở thích" in explanation
    assert "ưu tiên sự thoải mái" in explanation


def test_grounded_explanation_distinct_across_outfits():
    top1 = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Thun Đen")
    bottom1 = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Jeans Xanh")
    shoe1 = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneaker Đen")

    dress = _make_slot("d1", OutfitSlotRole.DRESS, name="Đầm Hoa Nhí")
    shoe2 = _make_slot("s2", OutfitSlotRole.FOOTWEAR, name="Sandal Cao Gót")

    outfit1 = _make_ranked_outfit(1, [top1, bottom1, shoe1])
    outfit2 = _make_ranked_outfit(2, [dress, shoe2])

    context = StylistContext(occasion="party", weather_condition="warm", time_of_day="night")

    exp1 = generate_grounded_explanation_vi(outfit1, context)
    exp2 = generate_grounded_explanation_vi(outfit2, context)

    assert exp1 != exp2
    assert "[Áo Thun Đen]" in exp1 and "[Áo Thun Đen]" not in exp2
    assert "[Đầm Hoa Nhí]" in exp2 and "[Đầm Hoa Nhí]" not in exp1


# ============================================================================
# 6. ATOMIC PERSISTENCE & DEEP ROLLBACK TESTS
# ============================================================================

def test_atomic_persistence_happy_path(db_session: Session):
    user = User(id="user_test")
    db_session.add(user)
    db_session.commit()

    _seed_wardrobe_item(db_session, "t1", "user_test", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b1", "user_test", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s1", "user_test", WardrobeCategory.FOOTWEAR)

    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Thun")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Kaki")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneakers")

    outfit = _make_ranked_outfit(1, [top, bottom, shoe])
    outfit.explanation_vi = "Giải thích mẫu 1"

    context = _make_context(occasion="cafe", weather_condition="cool")

    success, ids = persist_recommendations_atomically(
        db_session,
        user_id="user_test",
        request_id="req-123",
        user_query="Tối nay mặc gì đi cafe",
        context=context,
        ranked_outfits=[outfit],
    )

    assert success
    assert len(ids) == 1
    assert outfit.outfit_id == ids[0]

    # Verify persisted records in database
    recs = db_session.exec(select(OutfitRecommendation).where(OutfitRecommendation.id == ids[0])).all()
    assert len(recs) == 1
    rec = recs[0]
    assert rec.user_id == "user_test"
    assert rec.request_id == "req-123"
    assert rec.explanation_vi == "Giải thích mẫu 1"
    assert rec.rule_version == COORDINATOR_RULE_VERSION

    # Verify OutfitItem links
    outfit_items = db_session.exec(select(OutfitItem).where(OutfitItem.outfit_id == ids[0])).all()
    assert len(outfit_items) == 3
    assert {i.wardrobe_item_id for i in outfit_items} == {"t1", "b1", "s1"}
    assert all(i.user_id == "user_test" for i in outfit_items)


def test_atomic_persistence_deep_rollback_on_partial_failure(db_session: Session):
    """Reviewer hardening point 6: simulate failure after partial flush of 1st outfit/item.

    Verifies:
    - 0 OutfitRecommendation records remain.
    - 0 OutfitItem records remain.
    - Session remains clean and usable after rollback.
    """
    user = User(id="user_rollback")
    db_session.add(user)
    db_session.commit()

    _seed_wardrobe_item(db_session, "t1", "user_rollback", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b1", "user_rollback", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s1", "user_rollback", WardrobeCategory.FOOTWEAR)

    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Giày")

    outfit1 = _make_ranked_outfit(1, [top, bottom, shoe])
    outfit1.explanation_vi = "Outfit 1"

    # Outfit 2 contains an invalid item slot role that fails foreign key or constraint
    # We can simulate failure by adding an outfit that violates DB integrity
    class BrokenRankedOutfit(RankedOutfit):
        pass

    outfit2 = _make_ranked_outfit(2, [top, bottom, shoe])
    outfit2.fashion_score = -999.0  # Violates CheckConstraint 'ck_outfit_recommendations_fashion_score' (BETWEEN 0.0 AND 1.0)

    context = _make_context(occasion="work")

    # Initial count in DB
    assert len(db_session.exec(select(OutfitRecommendation)).all()) == 0
    assert len(db_session.exec(select(OutfitItem)).all()) == 0

    success, ids = persist_recommendations_atomically(
        db_session,
        user_id="user_rollback",
        request_id="req-err",
        user_query="Hỏi lỗi",
        context=context,
        ranked_outfits=[outfit1, outfit2],
    )

    assert not success
    assert ids == []
    assert outfit1.outfit_id is None
    assert outfit2.outfit_id is None

    # Deep rollback check: exactly 0 records remain in DB
    recs_after = db_session.exec(select(OutfitRecommendation)).all()
    items_after = db_session.exec(select(OutfitItem)).all()
    assert len(recs_after) == 0
    assert len(items_after) == 0

    # Session is still healthy and usable for subsequent queries
    res = db_session.exec(select(User).where(User.id == "user_rollback")).first()
    assert res is not None


# ============================================================================
# 7. LANGGRAPH COORDINATOR NODE INTEGRATION TESTS
# ============================================================================

def test_coordinator_node_full_happy_path(db_session: Session):
    user = User(id="user_node")
    db_session.add(user)
    db_session.commit()

    _seed_wardrobe_item(db_session, "t1", "user_node", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b1", "user_node", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s1", "user_node", WardrobeCategory.FOOTWEAR)

    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Polo")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Kaki")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneaker")

    candidate_pool = {
        "tops": [top],
        "bottoms": [bottom],
        "footwear": [shoe],
    }
    outfit = _make_ranked_outfit(1, [top, bottom, shoe])

    state: StylistGraphState = {
        "user_id": "user_node",
        "request_id": "req-node-1",
        "user_query": "Đi cafe mặc gì",
        "context": _make_context(occasion="cafe", weather_condition="cool"),
        "candidate_pool": candidate_pool,
        "ranked_outfits": [outfit],
        "errors": [],
        "warnings": [],
    }

    result = coordinator_node(state, session=db_session)

    assert result["grounding_validated"] is True
    assert len(result["recommendation_ids"]) == 1
    assert result["feedback_prompt_eligible"] is False
    assert result["feedback_target_outfit_id"] is None
    assert len(result["ranked_outfits"]) == 1
    saved_outfit = result["ranked_outfits"][0]
    assert saved_outfit.outfit_id == result["recommendation_ids"][0]
    assert saved_outfit.explanation_vi != ""
    assert "[Áo Polo]" in saved_outfit.explanation_vi


def test_coordinator_node_grounding_failure_leaves_zero_db_records(db_session: Session):
    user = User(id="user_node_fail")
    db_session.add(user)
    db_session.commit()

    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Polo")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Kaki")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneaker")

    # DB only has t1 and b1, shoe is missing from DB
    _seed_wardrobe_item(db_session, "t1", "user_node_fail", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b1", "user_node_fail", WardrobeCategory.BOTTOM)

    candidate_pool = {
        "tops": [top],
        "bottoms": [bottom],
        "footwear": [shoe],
    }
    outfit = _make_ranked_outfit(1, [top, bottom, shoe])

    state: StylistGraphState = {
        "user_id": "user_node_fail",
        "request_id": "req-node-fail",
        "user_query": "Đi cafe mặc gì",
        "context": _make_context(occasion="cafe", weather_condition="cool"),
        "candidate_pool": candidate_pool,
        "ranked_outfits": [outfit],
        "errors": [],
        "warnings": [],
    }

    result = coordinator_node(state, session=db_session)

    assert result["grounding_validated"] is False
    assert result["recommendation_ids"] == []
    assert any(GROUNDING_VALIDATION_FAILED in err for err in result["errors"])

    # Verifies zero DB records created
    assert len(db_session.exec(select(OutfitRecommendation)).all()) == 0
    assert len(db_session.exec(select(OutfitItem)).all()) == 0


def test_coordinator_node_short_circuits_on_upstream_errors(db_session: Session):
    """Invariant: An error state cannot also produce a successful recommendation payload."""
    user = User(id="user_err_short")
    db_session.add(user)
    db_session.commit()

    _seed_wardrobe_item(db_session, "t1", "user_err_short", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b1", "user_err_short", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s1", "user_err_short", WardrobeCategory.FOOTWEAR)

    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Polo")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Kaki")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneaker")

    candidate_pool = {
        "tops": [top],
        "bottoms": [bottom],
        "footwear": [shoe],
    }
    outfit = _make_ranked_outfit(1, [top, bottom, shoe])

    state: StylistGraphState = {
        "user_id": "user_err_short",
        "request_id": "req-err-short",
        "user_query": "Đi cafe mặc gì",
        "context": _make_context(occasion="cafe", weather_condition="cool"),
        "candidate_pool": candidate_pool,
        "ranked_outfits": [outfit],
        "errors": ["WARDROBE_EMPTY"],  # Existing upstream error
        "warnings": [],
    }

    result = coordinator_node(state, session=db_session)

    assert result["grounding_validated"] is False
    assert result["recommendation_ids"] == []
    assert result["ranked_outfits"] == []
    assert "WARDROBE_EMPTY" in result["errors"]

    # Invariant: 0 records in database
    assert len(db_session.exec(select(OutfitRecommendation)).all()) == 0
    assert len(db_session.exec(select(OutfitItem)).all()) == 0


def test_coordinator_state_validation_rejects_more_than_three_outfits():
    """Rejects state if ranked_outfits exceeds 3."""
    slots = [_make_slot(f"t{i}", OutfitSlotRole.TOP) for i in range(4)]
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM)
    outfits = [
        _make_ranked_outfit(1, [slots[0], bottom]),
        _make_ranked_outfit(2, [slots[1], bottom]),
        _make_ranked_outfit(3, [slots[2], bottom]),
        _make_ranked_outfit(3, [slots[3], bottom]),  # 4 outfits total
    ]

    state: StylistGraphState = {
        "user_id": "u1",
        "request_id": "req-1",
        "user_query": "query",
        "context": _make_context(),
        "candidate_pool": {},
        "ranked_outfits": outfits,
    }

    valid, err = validate_coordinator_input_state(state)
    assert not valid
    assert "exceeds maximum allowed" in err


def test_coordinator_state_validation_rejects_duplicate_or_non_consecutive_ranks():
    """Rejects state if ranks are duplicated or not strictly consecutive starting from 1."""
    top = _make_slot("t1", OutfitSlotRole.TOP)
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM)

    # Duplicate rank 1
    outfits_dup = [
        _make_ranked_outfit(1, [top, bottom]),
        _make_ranked_outfit(1, [top, bottom]),
    ]
    state_dup: StylistGraphState = {
        "user_id": "u1",
        "request_id": "req-1",
        "user_query": "query",
        "context": _make_context(),
        "candidate_pool": {},
        "ranked_outfits": outfits_dup,
    }
    valid, err = validate_coordinator_input_state(state_dup)
    assert not valid
    assert "strictly consecutive" in err

    # Non-consecutive: ranks [1, 3]
    outfits_gap = [
        _make_ranked_outfit(1, [top, bottom]),
        _make_ranked_outfit(3, [top, bottom]),
    ]
    state_gap: StylistGraphState = {
        "user_id": "u1",
        "request_id": "req-1",
        "user_query": "query",
        "context": _make_context(),
        "candidate_pool": {},
        "ranked_outfits": outfits_gap,
    }
    valid2, err2 = validate_coordinator_input_state(state_gap)
    assert not valid2
    assert "strictly consecutive" in err2


def test_database_ownership_rejects_category_slot_role_mismatch(db_session: Session):
    """Rejects if database category does not match the outfit slot role."""
    user = User(id="user_mismatch")
    db_session.add(user)
    db_session.commit()

    # Seed an item with category TOP in database
    _seed_wardrobe_item(db_session, "item_top_1", "user_mismatch", WardrobeCategory.TOP)

    # But pass it inside a slot claiming it is a BOTTOM
    mismatched_slot = _make_slot("item_top_1", OutfitSlotRole.BOTTOM, name="Áo Top làm Quần")

    valid, err = validate_database_active_ownership(db_session, "user_mismatch", [mismatched_slot])
    assert not valid
    assert "does not match outfit slot role" in err


def test_grounded_explanation_filters_injected_preference_text():
    """Injected or non-canonical preference strings must be stripped from explanation_vi,
    even if they mimic open prefixes like 'phong cách <injected>'."""
    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Polo Trắng")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Chinos Xanh Navy")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Sneaker Trắng")

    outfit = _make_ranked_outfit(
        1,
        [top, bottom, shoe],
        applied_preferences=[
            "Phù hợp phong cách smart_casual đã chọn",
            "Bảng màu trung tính theo sở thích",
            "phong cách <script>alert(1)</script>",  # Injected open prefix
            "tông màu malicious",                    # Injected open prefix
            "ưu tiên hack",                          # Injected open prefix
            "injected: BUY LUXURY BAG",
        ],
    )
    context = _make_context(occasion="cafe", weather_condition="cool", time_of_day="evening")

    explanation = generate_grounded_explanation_vi(outfit, context)

    # Valid canonical preferences from allowlist are retained
    assert "Phù hợp phong cách smart_casual đã chọn" in explanation
    assert "Bảng màu trung tính theo sở thích" in explanation

    # Injected / open-prefix strings are completely stripped
    assert "<script>" not in explanation
    assert "malicious" not in explanation
    assert "BUY LUXURY BAG" not in explanation
    assert "hack" not in explanation


def test_coordinator_real_pipeline_preferences_integrated_into_explanation(db_session: Session):
    """End-to-end integration: Personalization Agent outputs valid tags, which Coordinator preserves."""
    from app.agents.personalization_agent import rerank_evaluated_outfits
    from app.agents.state import EvaluatedOutfit
    from app.models.entities import UserPreference

    user = User(id="user_p_int")
    db_session.add(user)
    db_session.commit()

    _seed_wardrobe_item(db_session, "t1", "user_p_int", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b1", "user_p_int", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s1", "user_p_int", WardrobeCategory.FOOTWEAR)

    top = _make_slot("t1", OutfitSlotRole.TOP, name="Áo Polo", style="smart_casual", color="white")
    bottom = _make_slot("b1", OutfitSlotRole.BOTTOM, name="Quần Kaki", style="smart_casual", color="beige")
    shoe = _make_slot("s1", OutfitSlotRole.FOOTWEAR, name="Giày Sneaker", style="smart_casual", color="white")

    cand = EvaluatedOutfit(
        items=[top, bottom, shoe],
        fashion_score=0.90,
        component_scores={},
        combination_id="combo_1",
    )

    prefs = UserPreference(
        user_id="user_p_int",
        styles=["smart_casual"],
        color_palettes=["neutral"],
        priorities=["comfort"],
    )

    # Personalization Agent reranking produces real applied_preferences
    ranked_outfits, _ = rerank_evaluated_outfits([cand], preferences=prefs)
    assert len(ranked_outfits) == 1
    real_ranked = ranked_outfits[0]
    assert len(real_ranked.applied_preferences) > 0

    candidate_pool = {
        "tops": [top],
        "bottoms": [bottom],
        "footwear": [shoe],
    }

    state: StylistGraphState = {
        "user_id": "user_p_int",
        "request_id": "req-p-int",
        "user_query": "Đi làm mặc gì",
        "context": _make_context(occasion="work", weather_condition="cool"),
        "candidate_pool": candidate_pool,
        "ranked_outfits": [real_ranked],
        "errors": [],
        "warnings": [],
    }

    result = coordinator_node(state, session=db_session)
    assert result["grounding_validated"] is True
    saved_outfit = result["ranked_outfits"][0]

    # Verify that the explanation retains the real preferences produced by Personalization Agent
    assert "Phù hợp phong cách smart_casual đã chọn" in saved_outfit.explanation_vi
    assert "Bảng màu trung tính theo sở thích" in saved_outfit.explanation_vi


def test_grounded_explanation_low_score_transparency_and_diversity():
    """LT-04: Verify low-score transparency and metadata-based explanations."""
    top = _make_slot("t_red", OutfitSlotRole.TOP, name="Áo Thun Đỏ Ngôi Sao")
    bottom = _make_slot("b_jean", OutfitSlotRole.BOTTOM, name="Quần Jeans Xanh")
    footwear = _make_slot("f_shoe", OutfitSlotRole.FOOTWEAR, name="Giày Sneaker Đen")

    context = _make_context(occasion="work", weather_condition="cold", time_of_day="morning")

    # 1. Low score outfit (56%) - Must be honest, never claiming to be 'lý tưởng'
    low_outfit = _make_ranked_outfit(1, [top, bottom, footwear], composite_score=0.56)
    low_exp = generate_grounded_explanation_vi(low_outfit, context)

    assert "lý tưởng" not in low_exp
    assert "rất phù hợp" not in low_exp
    assert "56%" in low_exp
    assert "vừa phải" in low_exp
    assert "[Áo Thun Đỏ Ngôi Sao]" in low_exp
    assert "[Quần Jeans Xanh]" in low_exp
    assert "[Giày Sneaker Đen]" in low_exp

    # 2. Moderate score outfit (70%)
    mid_outfit = _make_ranked_outfit(1, [top, bottom, footwear], composite_score=0.70)
    mid_exp = generate_grounded_explanation_vi(mid_outfit, context)

    # 3. Rank alone must not invent differences for identical garments
    high_outfit_1 = _make_ranked_outfit(1, [top, bottom, footwear], composite_score=0.88)
    high_outfit_2 = _make_ranked_outfit(2, [top, bottom, footwear], composite_score=0.85)
    high_outfit_3 = _make_ranked_outfit(3, [top, bottom, footwear], composite_score=0.82)

    high_exp_1 = generate_grounded_explanation_vi(high_outfit_1, context)
    high_exp_2 = generate_grounded_explanation_vi(high_outfit_2, context)
    high_exp_3 = generate_grounded_explanation_vi(high_outfit_3, context)

    # Identical garments do not acquire fabricated differences from their rank.
    assert high_exp_1 == high_exp_2 == high_exp_3
    assert "thoáng mát" not in mid_exp
    assert "mềm mại" not in mid_exp


def test_grounded_llm_explanation_synthesis_and_anti_hallucination_fallback():
    """Verify LLM explanation is used when strictly grounded, and falls back deterministically on hallucination."""
    top = _make_slot("t_white", OutfitSlotRole.TOP, name="Áo thun trắng", color="white")
    bottom = _make_slot("b_khaki", OutfitSlotRole.BOTTOM, name="Quần tây khaki", color="khaki")
    footwear = _make_slot("f_white", OutfitSlotRole.FOOTWEAR, name="Giày sneaker trắng", color="white")
    outfit = _make_ranked_outfit(1, [top, bottom, footwear], composite_score=0.84)
    context = _make_context(occasion="cafe", weather_condition="cool", time_of_day="evening")

    class ValidGroundedLLM:
        def generate_outfit_explanation(self, **kwargs) -> str:
            return (
                "Sự kết hợp giữa [Áo thun] màu trắng, [Quần tây] màu khaki và [Giày sneaker] màu trắng "
                "tạo nên tổng thể gọn gàng, hài hòa cho buổi hẹn cafe tối trời mát."
            )

    class HallucinatingLLM:
        def generate_outfit_explanation(self, **kwargs) -> str:
            # Mentions an invented [Áo blazer đen] not in the outfit
            return "Phối [Áo thun], [Quần tây], [Giày sneaker] kèm [Áo blazer đen] lịch lãm."

    class ForbiddenWordLLM:
        def generate_outfit_explanation(self, **kwargs) -> str:
            # Uses forbidden subjective claim 'lý tưởng'
            return "Phối [Áo thun], [Quần tây] và [Giày sneaker] là lựa chọn lý tưởng cho buổi tối."

    valid_exp = generate_grounded_explanation_vi(outfit, context, llm_provider=ValidGroundedLLM())
    assert "tạo nên tổng thể gọn gàng, hài hòa" in valid_exp
    assert "[Áo thun]" in valid_exp and "[Quần tây]" in valid_exp and "[Giày sneaker]" in valid_exp

    fallback_hallucinated = generate_grounded_explanation_vi(outfit, context, llm_provider=HallucinatingLLM())
    assert "Áo blazer" not in fallback_hallucinated
    assert fallback_hallucinated == generate_grounded_explanation_vi(outfit, context)

    fallback_forbidden = generate_grounded_explanation_vi(outfit, context, llm_provider=ForbiddenWordLLM())
    assert "lý tưởng" not in fallback_forbidden
    assert fallback_forbidden == generate_grounded_explanation_vi(outfit, context)


def test_grounded_llm_batch_explanation_single_call_and_per_outfit_fallback():
    """Batch LLM explanation uses 1 request for multiple outfits and falls back per-outfit on hallucinations."""
    import json
    import httpx
    from pydantic import SecretStr
    from app.agents.coordinator import generate_grounded_explanations_batch
    from app.services.context_providers import GeminiContextProvider

    top1 = _make_slot("t_w1", OutfitSlotRole.TOP, name="Áo thun trắng", color="white")
    top2 = _make_slot("t_w2", OutfitSlotRole.TOP, name="Áo polo xanh navy", color="navy")
    top3 = _make_slot("t_w3", OutfitSlotRole.TOP, name="Áo sơ mi trắng", color="white")
    bottom = _make_slot("b_k1", OutfitSlotRole.BOTTOM, name="Quần tây khaki", color="khaki")
    footwear = _make_slot("f_s1", OutfitSlotRole.FOOTWEAR, name="Giày sneaker trắng", color="white")

    outfit_1 = _make_ranked_outfit(1, [top1, bottom, footwear], composite_score=0.88)
    outfit_2 = _make_ranked_outfit(2, [top2, bottom, footwear], composite_score=0.84)
    outfit_3 = _make_ranked_outfit(3, [top3, bottom, footwear], composite_score=0.80)
    context = _make_context(occasion="cafe", weather_condition="cool", time_of_day="evening")

    # 1. GeminiContextProvider batch method executes 1 HTTP request and falls back only on bad items
    http_calls = 0

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal http_calls
        http_calls += 1
        batch_json = json.dumps({
            "explanations": [
                "Bộ đầu kết hợp [Áo thun] trắng, [Quần tây] khaki và [Giày sneaker] trắng gọn gàng cho buổi cafe.",
                # Hallucinates [Áo blazer đen] not present in outfit 2
                "Phối [Áo polo], [Quần tây], [Giày sneaker] cùng [Áo blazer đen] nổi bật.",
                "Bộ ba gồm [Áo sơ mi] trắng, [Quần tây] khaki và [Giày sneaker] trắng cân đối cho tiết trời mát.",
            ]
        })
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": batch_json}]}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(_handler))
    provider = GeminiContextProvider(api_key=SecretStr("test-key"), model="gemini-test", client=client)

    results = generate_grounded_explanations_batch([outfit_1, outfit_2, outfit_3], context, llm_provider=provider)
    assert http_calls == 1
    assert len(results) == 3
    assert "gọn gàng cho buổi cafe" in results[0]
    assert "Áo blazer" not in results[1]
    assert results[1] == generate_grounded_explanation_vi(outfit_2, context)
    assert "cân đối cho tiết trời mát" in results[2]

    # 2. Custom provider implementing only single-outfit explanation still works concurrently in order
    class SingleOnlyLLM:
        def generate_outfit_explanation(self, *, items_description: list[str], **kwargs) -> str:
            return f"Gợi ý phối {', '.join(items_description)} cho buổi hẹn tối."

    single_results = generate_grounded_explanations_batch(
        [outfit_1, outfit_2, outfit_3], context, llm_provider=SingleOnlyLLM()
    )
    assert len(single_results) == 3
    assert "[Áo thun trắng]" in single_results[0]
    assert "[Áo polo xanh navy]" in single_results[1]
    assert "[Áo sơ mi trắng]" in single_results[2]


def test_critic_kept_original_description_matches_trigger_issue(db_session: Session):
    """CRITIC_KEPT_ORIGINAL conflict note must reflect whether Loop 2 was triggered by CONTEXT_GAP or ALL_RECENTLY_WORN."""
    from app.agents.coordinator import _kept_original_description_vi
    from app.agents.state import AgentTraceEvent

    rain_desc = _kept_original_description_vi([
        AgentTraceEvent(
            round=0,
            sender="coordinator",
            receiver="fashion",
            event_type="CRITIQUE_CONTEXT_GAP",
            summary_vi="Thời tiết mưa nhưng chưa tận dụng đồ chống thấm.",
        )
    ])
    assert "thời tiết" in rain_desc
    assert "lặp đồ" not in rain_desc

    repeat_desc = _kept_original_description_vi([
        AgentTraceEvent(
            round=0,
            sender="coordinator",
            receiver="fashion",
            event_type="CRITIQUE_ALL_RECENTLY_WORN",
            summary_vi="Cả 3 bộ đều chứa món vừa mặc trong 48h.",
        )
    ])
    assert "tránh lặp đồ" in repeat_desc

    # End-to-end check through coordinator_node when CONTEXT_GAP retry drops score by > 0.05
    user = User(id="user_ctx_gap_keep")
    db_session.add(user)
    db_session.commit()
    _seed_wardrobe_item(db_session, "t_cg", "user_ctx_gap_keep", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b_cg", "user_ctx_gap_keep", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s_cg1", "user_ctx_gap_keep", WardrobeCategory.FOOTWEAR)
    _seed_wardrobe_item(db_session, "s_cg2", "user_ctx_gap_keep", WardrobeCategory.FOOTWEAR)

    top = _make_slot("t_cg", OutfitSlotRole.TOP, name="Áo sơ mi trắng", color="white")
    bottom = _make_slot("b_cg", OutfitSlotRole.BOTTOM, name="Quần tây đen", color="black")
    shoe_orig = _make_slot("s_cg1", OutfitSlotRole.FOOTWEAR, name="Giày oxford đen", color="black")
    shoe_rain = _make_slot("s_cg2", OutfitSlotRole.FOOTWEAR, name="Giày boots xanh", color="green")

    orig_outfit = _make_ranked_outfit(1, [top, bottom, shoe_orig], composite_score=0.88)
    retry_outfit = _make_ranked_outfit(1, [top, bottom, shoe_rain], composite_score=0.72)

    state: StylistGraphState = {
        "user_id": "user_ctx_gap_keep",
        "request_id": "req-ctx-gap-keep",
        "user_query": "Trời mưa đi họp mặc gì?",
        "context": _make_context(occasion="work", weather_condition="rainy"),
        "candidate_pool": {"tops": [top], "bottoms": [bottom], "footwear": [shoe_orig, shoe_rain]},
        "ranked_outfits": [retry_outfit],
        "previous_ranked_outfits": [orig_outfit],
        "enable_agent_loops": True,
        "critique_round": 1,
        "agent_trace": [
            AgentTraceEvent(
                round=0,
                sender="coordinator",
                receiver="fashion",
                event_type="CRITIQUE_CONTEXT_GAP",
                summary_vi="Thời tiết mưa nhưng thiếu đồ chống thấm.",
            )
        ],
        "errors": [],
        "warnings": [],
    }
    res = coordinator_node(state, session=db_session)
    assert res["grounding_validated"] is True
    assert res["ranked_outfits"][0].items[2].item_id == "s_cg1"
    kept_notes = [n for n in res["conflict_notes"] if n.conflict_type == "CRITIC_KEPT_ORIGINAL"]
    assert len(kept_notes) == 1
    assert "thời tiết" in kept_notes[0].description_vi
    assert "lặp đồ" not in kept_notes[0].description_vi


def test_strict_llm_explanation_validator_rejects_ungrounded_attributes_and_claims():
    """Review #3: validator must reject wrong color, wrong material, unowned garments outside [...], and unsupported functional claims."""
    shirt = _make_slot("t_s1", OutfitSlotRole.TOP, name="Áo sơ mi trắng", color="white")
    shirt.material = "cotton"
    shirt.sub_category = "shirt"
    trousers = _make_slot("b_t1", OutfitSlotRole.BOTTOM, name="Quần tây đen", color="black")
    trousers.material = "wool"
    trousers.sub_category = "trousers"
    oxford = _make_slot("f_o1", OutfitSlotRole.FOOTWEAR, name="Giày oxford đen", color="black")
    oxford.material = "leather"
    oxford.sub_category = "oxford"
    outfit = _make_ranked_outfit(1, [shirt, trousers, oxford], composite_score=0.86)
    context = _make_context(occasion="work", weather_condition="rainy", time_of_day="morning")
    deterministic = generate_grounded_explanation_vi(outfit, context)

    class _StaticLLM:
        def __init__(self, text: str) -> None:
            self.text = text

        def generate_outfit_explanation(self, **kwargs) -> str:
            return self.text

    # 1. Exact reviewer counterexample (wrong color, wrong material, unowned bag, unsupported waterproof claim)
    reviewer_counter = (
        "[Áo sơ mi] màu đỏ chất lụa kết hợp [Quần tây] và [Giày oxford], "
        "phối thêm túi xách da và chống thấm mưa tốt."
    )
    assert generate_grounded_explanation_vi(outfit, context, llm_provider=_StaticLLM(reviewer_counter)) == deterministic

    # 2. Wrong color outside brackets
    wrong_color = "Bộ [Áo sơ mi] màu đỏ, [Quần tây] đen và [Giày oxford] đen gọn gàng cho buổi họp."
    assert generate_grounded_explanation_vi(outfit, context, llm_provider=_StaticLLM(wrong_color)) == deterministic

    # 3. Wrong material outside brackets
    wrong_material = "Bộ [Áo sơ mi] chất lụa trắng, [Quần tây] đen và [Giày oxford] đen lịch sự."
    assert generate_grounded_explanation_vi(outfit, context, llm_provider=_StaticLLM(wrong_material)) == deterministic

    # 4. Unowned accessory mentioned outside brackets
    unowned_item = "Bộ [Áo sơ mi] trắng, [Quần tây] đen và [Giày oxford] đen phối cùng túi xách nhỏ."
    assert generate_grounded_explanation_vi(outfit, context, llm_provider=_StaticLLM(unowned_item)) == deterministic

    # 5. Unsupported waterproof claim when functional_flags lacks water_resistant/rain
    unsupported_flag = "Bộ [Áo sơ mi] trắng, [Quần tây] đen và [Giày oxford] đen chống thấm mưa tốt."
    assert generate_grounded_explanation_vi(outfit, context, llm_provider=_StaticLLM(unsupported_flag)) == deterministic

    # 6. Grounded text referencing ONLY real attributes passes; waterproof passes when functional_flags includes water_resistant
    oxford.functional_flags = ["water_resistant", "rain"]
    grounded_with_flag = (
        "Bộ [Áo sơ mi] cotton trắng, [Quần tây] đen và [Giày oxford] da đen chống thấm nước tốt cho ngày mưa."
    )
    accepted = generate_grounded_explanation_vi(outfit, context, llm_provider=_StaticLLM(grounded_with_flag))
    assert "chống thấm nước tốt cho ngày mưa" in accepted


def test_coordinator_llm_explanation_is_opt_in_and_skips_after_context_failure(db_session: Session):
    """Coordinator defaults to deterministic explanations (0 extra LLM calls) and skips LLM when context provider failed."""
    user = User(id="user_llm_optin")
    db_session.add(user)
    db_session.commit()
    _seed_wardrobe_item(db_session, "t_opt", "user_llm_optin", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b_opt", "user_llm_optin", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s_opt", "user_llm_optin", WardrobeCategory.FOOTWEAR)

    top = _make_slot("t_opt", OutfitSlotRole.TOP, name="Áo sơ mi trắng", color="white")
    bottom = _make_slot("b_opt", OutfitSlotRole.BOTTOM, name="Quần tây đen", color="black")
    shoe = _make_slot("s_opt", OutfitSlotRole.FOOTWEAR, name="Giày oxford đen", color="black")

    class _CountingLLM:
        def __init__(self) -> None:
            self.calls = 0

        def generate_outfit_explanations(self, **kwargs) -> list[str]:
            self.calls += 1
            return ["Bộ [Áo sơ mi] trắng, [Quần tây] đen và [Giày oxford] đen gọn gàng cho buổi họp."]

    def _base_state(req_id: str, **extra: object) -> StylistGraphState:
        st: StylistGraphState = {
            "user_id": "user_llm_optin",
            "request_id": req_id,
            "user_query": "Đi họp sáng nay mặc gì?",
            "context": _make_context(occasion="work", weather_condition="cool"),
            "candidate_pool": {"tops": [top], "bottoms": [bottom], "footwear": [shoe]},
            "ranked_outfits": [_make_ranked_outfit(1, [top, bottom, shoe], composite_score=0.88)],
            "enable_agent_loops": False,
            "errors": [],
            "warnings": [],
        }
        st.update(extra)  # type: ignore[typeddict-item]
        return st

    # Default (config enable_llm_explanations=False): 0 LLM calls
    llm_default = _CountingLLM()
    res_default = coordinator_node(_base_state("req-opt-default"), session=db_session, llm_provider=llm_default)
    assert res_default["grounding_validated"] is True
    assert llm_default.calls == 0

    # Opt-in enabled + context healthy: 1 batched LLM call
    llm_enabled = _CountingLLM()
    res_enabled = coordinator_node(
        _base_state("req-opt-enabled", enable_llm_explanations=True),
        session=db_session,
        llm_provider=llm_enabled,
    )
    assert res_enabled["grounding_validated"] is True
    assert llm_enabled.calls == 1
    assert "gọn gàng cho buổi họp" in res_enabled["ranked_outfits"][0].explanation_vi

    # Opt-in enabled + context provider failed: 0 LLM calls
    llm_skipped = _CountingLLM()
    res_skipped = coordinator_node(
        _base_state("req-opt-ctx-fail", enable_llm_explanations=True, context_llm_failed=True),
        session=db_session,
        llm_provider=llm_skipped,
    )
    assert res_skipped["grounding_validated"] is True
    assert llm_skipped.calls == 0


def test_critic_kept_original_restores_original_conflict_notes_and_major_slot_worn_check(db_session: Session):
    """CRITIC_KEPT_ORIGINAL restores round-0 conflict_notes/warnings; ALL_RECENTLY_WORN ignores accessories & formats count."""
    from datetime import datetime, timedelta, timezone
    from app.agents.coordinator import evaluate_critic_signal
    from app.agents.state import AgentTraceEvent, ConflictNote

    ref_time = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
    worn_iso = (ref_time - timedelta(hours=12)).isoformat()

    top = _make_slot("t_m1", OutfitSlotRole.TOP, name="Áo sơ mi trắng", color="white")
    bottom = _make_slot("b_m1", OutfitSlotRole.BOTTOM, name="Quần tây đen", color="black")
    shoe = _make_slot("s_m1", OutfitSlotRole.FOOTWEAR, name="Giày oxford đen", color="black")
    acc_worn = _make_slot("a_m1", OutfitSlotRole.ACCESSORY, name="Đồng hồ nâu", color="brown")
    acc_worn.last_worn_at = worn_iso
    acc_fresh = _make_slot("a_m2", OutfitSlotRole.ACCESSORY, name="Thắt lưng đen", color="black")

    # 1. Recently worn accessory ONLY must NOT trigger ALL_RECENTLY_WORN (aligned with MAJOR_SLOT_ROLES)
    outfit_acc_worn = _make_ranked_outfit(1, [top, bottom, shoe, acc_worn], composite_score=0.85)
    signal_acc = evaluate_critic_signal(
        [outfit_acc_worn],
        {"tops": [top], "bottoms": [bottom], "footwear": [shoe], "accessories": [acc_worn, acc_fresh]},
        _make_context(occasion="work"),
        reference_time=ref_time,
    )
    assert signal_acc is None

    # 2. Single outfit with recently worn major item uses singular wording (not "Cả 3 phương án đầu")
    top_worn = _make_slot("t_m2", OutfitSlotRole.TOP, name="Áo polo trắng", color="white")
    top_worn.last_worn_at = worn_iso
    outfit_single = _make_ranked_outfit(1, [top_worn, bottom, shoe], composite_score=0.85)
    signal_single = evaluate_critic_signal(
        [outfit_single],
        {"tops": [top_worn, top], "bottoms": [bottom], "footwear": [shoe]},
        _make_context(occasion="work"),
        reference_time=ref_time,
    )
    assert signal_single is not None
    assert signal_single.issue_code == "ALL_RECENTLY_WORN"
    assert "Cả 3 phương án" not in signal_single.reason_vi

    # 3. CRITIC_KEPT_ORIGINAL restores previous_conflict_notes instead of leaking discarded retry notes
    user = User(id="user_keep_notes")
    db_session.add(user)
    db_session.commit()
    _seed_wardrobe_item(db_session, "t_m1", "user_keep_notes", WardrobeCategory.TOP)
    _seed_wardrobe_item(db_session, "b_m1", "user_keep_notes", WardrobeCategory.BOTTOM)
    _seed_wardrobe_item(db_session, "s_m1", "user_keep_notes", WardrobeCategory.FOOTWEAR)

    orig_note = ConflictNote(
        conflict_type="RECENT_WEAR_VS_BEST_FIT",
        description_vi="Ghi chú vòng gốc.",
        resolution_vi="Xử lý vòng gốc.",
    )
    discarded_retry_note = ConflictNote(
        conflict_type="PROFILE_AVOID_VS_REQUEST",
        description_vi="Ghi chú vòng retry bị bỏ.",
        resolution_vi="Không được giữ lại.",
    )
    orig_outfit = _make_ranked_outfit(1, [top, bottom, shoe], composite_score=0.90)
    retry_outfit = _make_ranked_outfit(1, [top, bottom, shoe], composite_score=0.70)

    state: StylistGraphState = {
        "user_id": "user_keep_notes",
        "request_id": "req-keep-notes",
        "user_query": "Đi làm sáng nay",
        "context": _make_context(occasion="work"),
        "candidate_pool": {"tops": [top], "bottoms": [bottom], "footwear": [shoe]},
        "ranked_outfits": [retry_outfit],
        "previous_ranked_outfits": [orig_outfit],
        "previous_conflict_notes": [orig_note],
        "previous_warnings": ["Cảnh báo vòng gốc."],
        "conflict_notes": [discarded_retry_note],
        "warnings": ["Cảnh báo vòng retry bị bỏ."],
        "enable_agent_loops": True,
        "critique_round": 1,
        "agent_trace": [
            AgentTraceEvent(
                round=0,
                sender="coordinator",
                receiver="fashion",
                event_type="CRITIQUE_ALL_RECENTLY_WORN",
                summary_vi="Phản biện lặp đồ.",
            )
        ],
        "errors": [],
    }
    res = coordinator_node(state, session=db_session)
    assert res["grounding_validated"] is True
    note_descs = [n.description_vi for n in res["conflict_notes"]]
    assert "Ghi chú vòng gốc." in note_descs
    assert "Ghi chú vòng retry bị bỏ." not in note_descs
    assert res["warnings"] == ["Cảnh báo vòng gốc."]

    # 4. disable_personalization=True skips ALL_RECENTLY_WORN but preserves situational CONTEXT_GAP
    signal_no_pers = evaluate_critic_signal(
        [outfit_single],
        {"tops": [top_worn, top], "bottoms": [bottom], "footwear": [shoe]},
        _make_context(occasion="work"),
        reference_time=ref_time,
        disable_personalization=True,
    )
    assert signal_no_pers is None

    jacket_rain = _make_slot("o_rain", OutfitSlotRole.OUTERWEAR, name="Áo khoác dù", color="navy")
    jacket_rain.functional_flags = ["water_resistant", "rain"]
    rain_ctx = _make_context(occasion="work", weather_condition="rainy")
    rain_ctx.target_functional_tags = ["water_resistant", "rain"]
    signal_rain_no_pers = evaluate_critic_signal(
        [outfit_single],
        {"tops": [top_worn, top], "bottoms": [bottom], "footwear": [shoe], "outerwear": [jacket_rain]},
        rain_ctx,
        reference_time=ref_time,
        disable_personalization=True,
    )
    assert signal_rain_no_pers is not None
    assert signal_rain_no_pers.issue_code == "CONTEXT_GAP"




def test_prepare_grounded_explanation_localizes_colors_while_preserving_khaki():
    """Ensure extended Vietnamese color localizations and raw/localized brackets work while preserving 'màu khaki'."""
    from app.agents.coordinator import (
        _prepare_grounded_explanation,
        _validate_grounded_llm_explanation,
    )

    pink_top = _make_slot("t_p", OutfitSlotRole.TOP, name="Áo ba lỗ", color="pink")
    khaki_bot = _make_slot("b_k", OutfitSlotRole.BOTTOM, name="Quần tây", color="khaki")
    light_blue_top = _make_slot("t_lb", OutfitSlotRole.TOP, name="Áo sơ mi", color="light_blue")
    cream_outer = _make_slot("o_c", OutfitSlotRole.OUTERWEAR, name="Áo cardigan", color="cream")
    footwear = _make_slot("f_w", OutfitSlotRole.FOOTWEAR, name="Giày sneaker", color="white")
    ctx = _make_context(occasion="cafe", weather_condition="cool", time_of_day="afternoon")

    outfit = _make_ranked_outfit(1, [pink_top, khaki_bot, footwear], composite_score=0.9)
    prepared = _prepare_grounded_explanation(outfit, ctx)
    assert "màu hồng" in prepared.deterministic_explanation
    assert "màu khaki" in prepared.deterministic_explanation
    assert _validate_grounded_llm_explanation(
        "Phối [Áo ba lỗ hồng], [Quần tây khaki] và [Giày sneaker trắng] gọn gàng cho buổi cafe.",
        prepared.item_allowed_brackets,
        outfit=outfit,
    )

    outfit2 = _make_ranked_outfit(1, [light_blue_top, khaki_bot, footwear, cream_outer], composite_score=0.9)
    prepared2 = _prepare_grounded_explanation(outfit2, ctx)
    assert "màu xanh nhạt" in prepared2.deterministic_explanation
    assert "màu kem" in prepared2.deterministic_explanation
    assert _validate_grounded_llm_explanation(
        "Kết hợp [Áo sơ mi xanh nhạt], [Quần tây khaki], [Giày sneaker trắng] và [Áo cardigan kem] cho buổi chiều.",
        prepared2.item_allowed_brackets,
        outfit=outfit2,
    )
