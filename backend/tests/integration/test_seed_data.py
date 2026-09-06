from __future__ import annotations

import pytest
from alembic.config import Config
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.core.seed import (
    GOLDEN_USER_ID,
    SeedConflictError,
    SeedResult,
    seed_golden_wardrobe,
)
from app.models import User, WardrobeCategory, WardrobeItem

EXPECTED_GOLDEN_ITEMS = {
    "item-top-01": (
        WardrobeCategory.TOP,
        "polo",
        "white",
        "solid",
        "cotton",
        "smart_casual",
        3,
        ["warm", "cool"],
    ),
    "item-top-02": (
        WardrobeCategory.TOP,
        "button_down_shirt",
        "black",
        "unknown",
        "unknown",
        "smart_casual",
        3,
        ["warm", "cool", "cold"],
    ),
    "item-top-03": (
        WardrobeCategory.TOP,
        "tee",
        "grey",
        "graphic",
        "unknown",
        "streetwear",
        1,
        ["hot", "warm"],
    ),
    "item-bottom-01": (
        WardrobeCategory.BOTTOM,
        "chinos",
        "navy",
        "unknown",
        "unknown",
        "smart_casual",
        3,
        ["warm", "cool"],
    ),
    "item-bottom-02": (
        WardrobeCategory.BOTTOM,
        "trousers",
        "black",
        "unknown",
        "wool",
        "formal",
        4,
        ["warm", "cool", "cold"],
    ),
    "item-bottom-03": (
        WardrobeCategory.BOTTOM,
        "shorts",
        "unknown",
        "unknown",
        "denim",
        "casual",
        1,
        ["hot", "warm"],
    ),
    "item-shoes-01": (
        WardrobeCategory.FOOTWEAR,
        "sneakers",
        "white",
        "unknown",
        "leather",
        "minimalist",
        2,
        ["hot", "warm", "cool"],
    ),
    "item-shoes-02": (
        WardrobeCategory.FOOTWEAR,
        "oxford_shoes",
        "brown",
        "unknown",
        "leather",
        "formal",
        4,
        ["warm", "cool", "cold"],
    ),
}


def test_seed_is_idempotent_and_matches_the_golden_fixture(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database

    first_result = seed_golden_wardrobe(engine)
    second_result = seed_golden_wardrobe(engine)

    assert first_result == SeedResult(
        user_created=True,
        items_created=8,
        items_updated=0,
    )
    assert second_result == SeedResult(
        user_created=False,
        items_created=0,
        items_updated=8,
    )

    with Session(engine) as session:
        users = session.exec(select(User)).all()
        items = session.exec(select(WardrobeItem).order_by(WardrobeItem.id)).all()

    assert [user.id for user in users] == [GOLDEN_USER_ID]
    assert len(items) == 8
    actual_golden_items = {
        item.id: (
            item.category,
            item.sub_category,
            item.primary_color,
            item.pattern,
            item.material,
            item.style,
            item.formality_level,
            item.weather_suitability,
        )
        for item in items
    }
    assert actual_golden_items == EXPECTED_GOLDEN_ITEMS

    for item in items:
        assert item.user_id == GOLDEN_USER_ID
        assert item.is_active is True
        assert item.is_user_confirmed is True
        assert item.deleted_at is None


def test_seed_restores_modified_golden_item(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    seed_golden_wardrobe(engine)
    target_id = "item-top-01"

    with Session(engine) as session:
        item = session.get(WardrobeItem, target_id)
        assert item is not None
        item.primary_color = "modified"
        item.is_active = False
        item.is_user_confirmed = False
        session.add(item)
        session.commit()

    seed_golden_wardrobe(engine)

    with Session(engine) as session:
        restored_item = session.get(WardrobeItem, target_id)
        assert restored_item is not None
        assert restored_item.primary_color == "white"
        assert restored_item.is_active is True
        assert restored_item.is_user_confirmed is True


def test_seed_rolls_back_when_golden_item_belongs_to_another_user(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    conflicting_id = "item-top-01"
    other_user = User()
    conflicting_item = WardrobeItem(
        id=conflicting_id,
        user_id=other_user.id,
        category=WardrobeCategory.TOP,
        sub_category="polo",
        primary_color="white",
        pattern="solid",
        material="cotton",
        style="smart_casual",
        fit="unknown",
        formality_level=3,
    )

    with Session(engine) as session:
        session.add_all((other_user, conflicting_item))
        session.commit()

    with pytest.raises(SeedConflictError):
        seed_golden_wardrobe(engine)

    with Session(engine) as session:
        assert session.get(User, GOLDEN_USER_ID) is None
        items = session.exec(select(WardrobeItem)).all()

    assert [item.id for item in items] == [conflicting_id]
