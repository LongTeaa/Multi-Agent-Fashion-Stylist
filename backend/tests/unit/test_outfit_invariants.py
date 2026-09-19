from __future__ import annotations

import pytest
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

from app.agents.state import OutfitItemSlot, RankedOutfit
from app.models.entities import (
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    User,
    WardrobeCategory,
    WardrobeItem,
    new_uuid,
    utc_now,
)
from app.services.outfit_persistence import (
    OutfitInvariantError,
    persist_outfit_recommendations,
    validate_outfit_invariants,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(id="user-inv-1", email="inv1@example.com", full_name="User 1")
        other_user = User(id="user-inv-2", email="inv2@example.com", full_name="User 2")
        s.add(user)
        s.add(other_user)

        top = WardrobeItem(
            id="item-top",
            user_id="user-inv-1",
            category=WardrobeCategory.TOP,
            sub_category="t-shirt",
            primary_color="white",
            pattern="solid",
            material="cotton",
            style="casual",
            fit="regular",
            formality_level=2,
            is_active=True,
        )
        bot = WardrobeItem(
            id="item-bot",
            user_id="user-inv-1",
            category=WardrobeCategory.BOTTOM,
            sub_category="jeans",
            primary_color="blue",
            pattern="solid",
            material="denim",
            style="casual",
            fit="regular",
            formality_level=2,
            is_active=True,
        )
        dress = WardrobeItem(
            id="item-dress",
            user_id="user-inv-1",
            category=WardrobeCategory.DRESS,
            sub_category="midi",
            primary_color="black",
            pattern="solid",
            material="silk",
            style="formal",
            fit="regular",
            formality_level=4,
            is_active=True,
        )
        inactive = WardrobeItem(
            id="item-inactive",
            user_id="user-inv-1",
            category=WardrobeCategory.TOP,
            sub_category="shirt",
            primary_color="red",
            pattern="solid",
            material="cotton",
            style="casual",
            fit="regular",
            formality_level=2,
            is_active=False,
        )
        other_top = WardrobeItem(
            id="item-other-top",
            user_id="user-inv-2",
            category=WardrobeCategory.TOP,
            sub_category="polo",
            primary_color="green",
            pattern="solid",
            material="cotton",
            style="casual",
            fit="regular",
            formality_level=3,
            is_active=True,
        )
        s.add_all([top, bot, dress, inactive, other_top])
        s.commit()
        yield s


def _make_slot(item_id: str, slot_role: OutfitSlotRole, category: WardrobeCategory) -> OutfitItemSlot:
    return OutfitItemSlot(
        item_id=item_id,
        slot_role=slot_role,
        name="Test item",
        primary_color="blue",
        style="casual",
        category=category,
    )


def test_validate_valid_two_piece(session: Session):
    items = [
        _make_slot("item-top", OutfitSlotRole.TOP, WardrobeCategory.TOP),
        _make_slot("item-bot", OutfitSlotRole.BOTTOM, WardrobeCategory.BOTTOM),
    ]
    # Should not raise
    validate_outfit_invariants(session, "user-inv-1", items)


def test_validate_valid_dress(session: Session):
    items = [
        _make_slot("item-dress", OutfitSlotRole.DRESS, WardrobeCategory.DRESS),
    ]
    # Should not raise
    validate_outfit_invariants(session, "user-inv-1", items)


def test_validate_branch_xor_violation_top_only(session: Session):
    items = [
        _make_slot("item-top", OutfitSlotRole.TOP, WardrobeCategory.TOP),
    ]
    with pytest.raises(OutfitInvariantError, match="branch XOR rule"):
        validate_outfit_invariants(session, "user-inv-1", items)


def test_validate_branch_xor_violation_dress_and_top(session: Session):
    items = [
        _make_slot("item-dress", OutfitSlotRole.DRESS, WardrobeCategory.DRESS),
        _make_slot("item-top", OutfitSlotRole.TOP, WardrobeCategory.TOP),
    ]
    with pytest.raises(OutfitInvariantError, match="branch XOR rule"):
        validate_outfit_invariants(session, "user-inv-1", items)


def test_validate_duplicate_slot(session: Session):
    items = [
        _make_slot("item-top", OutfitSlotRole.TOP, WardrobeCategory.TOP),
        _make_slot("item-top", OutfitSlotRole.TOP, WardrobeCategory.TOP),
        _make_slot("item-bot", OutfitSlotRole.BOTTOM, WardrobeCategory.BOTTOM),
    ]
    with pytest.raises(OutfitInvariantError, match="Duplicate item for slot"):
        validate_outfit_invariants(session, "user-inv-1", items)


def test_validate_user_isolation(session: Session):
    items = [
        _make_slot("item-other-top", OutfitSlotRole.TOP, WardrobeCategory.TOP),
        _make_slot("item-bot", OutfitSlotRole.BOTTOM, WardrobeCategory.BOTTOM),
    ]
    with pytest.raises(OutfitInvariantError, match="does not belong to user"):
        validate_outfit_invariants(session, "user-inv-1", items)


def test_validate_inactive_item(session: Session):
    items = [
        _make_slot("item-inactive", OutfitSlotRole.TOP, WardrobeCategory.TOP),
        _make_slot("item-bot", OutfitSlotRole.BOTTOM, WardrobeCategory.BOTTOM),
    ]
    with pytest.raises(OutfitInvariantError, match="is inactive or deleted"):
        validate_outfit_invariants(session, "user-inv-1", items)


def test_persist_outfit_atomic_rollback_on_failure(session: Session):
    ranked = [
        RankedOutfit(
            rank=1,
            composite_score=0.9,
            explanation_vi="Good outfit",
            items=[
                _make_slot("item-top", OutfitSlotRole.TOP, WardrobeCategory.TOP),
                _make_slot("item-bot", OutfitSlotRole.BOTTOM, WardrobeCategory.BOTTOM),
            ],
        ),
        RankedOutfit(
            rank=2,
            composite_score=0.8,
            explanation_vi="Bad outfit with other user item",
            items=[
                _make_slot("item-other-top", OutfitSlotRole.TOP, WardrobeCategory.TOP),
                _make_slot("item-bot", OutfitSlotRole.BOTTOM, WardrobeCategory.BOTTOM),
            ],
        ),
    ]
    success, ids = persist_outfit_recommendations(
        session=session,
        user_id="user-inv-1",
        request_id="req-test-atomic",
        user_query="Casual style",
        context_snapshot={},
        ranked_outfits=ranked,
    )
    assert success is False
    assert ids == []
    # Verify rollback: 0 recommendations and 0 outfit items saved
    recs = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.request_id == "req-test-atomic")).all()
    assert len(recs) == 0
