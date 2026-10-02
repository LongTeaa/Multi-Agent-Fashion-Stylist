from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from app.agents.fashion_scoring import calculate_proportion_score
from app.agents.state import OutfitItemSlot
from app.models.entities import (
    MediaAsset,
    MediaKind,
    OutfitSlotRole,
    User,
    WardrobeCategory,
    WardrobeItem,
    WardrobeRetrievalDocument,
)
from app.schemas.wardrobe import (
    WardrobeItemAttributes,
    WardrobeItemCreate,
    WardrobeItemResponseData,
)
from app.services.retrieval_document_service import build_retrieval_document
from app.services.wardrobe_service import create_wardrobe_item


@pytest.fixture
def memory_db_session() -> Session:
    """Create an in-memory SQLite database with enforced foreign keys & check constraints."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(id="user-footwear-1", email="footwear_test@example.com")
        session.add(user)
        session.commit()
        yield session


def test_footwear_and_accessory_schema_normalizes_garment_fields_to_none() -> None:
    """Footwear and accessories must have fit, silhouette_level, and length set to None."""
    footwear_attr = WardrobeItemAttributes(
        category=WardrobeCategory.FOOTWEAR,
        sub_category="sneakers",
        primary_color="white",
        pattern="solid",
        material="leather",
        style="casual",
        fit="regular",  # passed explicitly
        silhouette_level=3,  # passed explicitly
        length="hip",  # passed explicitly
        formality_level=2,
    )
    assert footwear_attr.fit is None
    assert footwear_attr.silhouette_level is None
    assert footwear_attr.length is None

    accessory_attr = WardrobeItemAttributes(
        category=WardrobeCategory.ACCESSORY,
        sub_category="belt",
        primary_color="black",
        pattern="solid",
        material="leather",
        style="formal",
        fit="slim",
        silhouette_level=2,
        length="waist",
        formality_level=4,
    )
    assert accessory_attr.fit is None
    assert accessory_attr.silhouette_level is None
    assert accessory_attr.length is None


def test_garment_fields_are_preserved_for_clothing() -> None:
    """Garments like tops and bottoms retain fit, silhouette_level, and length."""
    top_attr = WardrobeItemAttributes(
        category=WardrobeCategory.TOP,
        sub_category="shirt",
        primary_color="blue",
        pattern="solid",
        material="cotton",
        style="casual",
        fit="regular",
        silhouette_level=3,
        length="hip",
        formality_level=3,
    )
    assert top_attr.fit == "regular"
    assert top_attr.silhouette_level == 3
    assert top_attr.length == "hip"


def test_db_check_constraints_permit_null_for_footwear_and_accessories(memory_db_session: Session) -> None:
    """Database check constraints must permit NULL for silhouette_level, length, and fit."""
    shoe = WardrobeItem(
        id="shoe-1",
        user_id="user-footwear-1",
        category=WardrobeCategory.FOOTWEAR,
        sub_category="loafers",
        primary_color="brown",
        pattern="solid",
        material="leather",
        style="smart_casual",
        fit=None,
        silhouette_level=None,
        length=None,
        formality_level=3,
        comfort_level=4,
    )
    memory_db_session.add(shoe)
    memory_db_session.commit()

    saved_shoe = memory_db_session.get(WardrobeItem, "shoe-1")
    assert saved_shoe is not None
    assert saved_shoe.fit is None
    assert saved_shoe.silhouette_level is None
    assert saved_shoe.length is None


def test_db_check_constraints_still_reject_invalid_non_null_values(memory_db_session: Session) -> None:
    """Database check constraints must still enforce bounds if values are not null."""
    invalid_item = WardrobeItem(
        id="bad-item-1",
        user_id="user-footwear-1",
        category=WardrobeCategory.TOP,
        sub_category="jacket",
        primary_color="black",
        pattern="solid",
        material="polyester",
        style="casual",
        fit="regular",
        silhouette_level=99,  # invalid bound
        length="hip",
        formality_level=3,
        comfort_level=3,
    )
    memory_db_session.add(invalid_item)
    with pytest.raises(IntegrityError):
        memory_db_session.commit()
    memory_db_session.rollback()


def test_retrieval_document_omits_silhouette_and_length_tokens_for_footwear() -> None:
    """Retrieval document for footwear should not index silhouette or length tokens."""
    shoe = WardrobeItem(
        id="shoe-doc-1",
        user_id="user-footwear-1",
        category=WardrobeCategory.FOOTWEAR,
        sub_category="sneakers",
        primary_color="white",
        pattern="solid",
        material="leather",
        style="streetwear",
        fit=None,
        silhouette_level=None,
        length=None,
        formality_level=1,
        comfort_level=5,
    )
    searchable_text, metadata = build_retrieval_document(shoe)

    assert metadata["fit"] is None
    assert metadata["silhouette_level"] is None
    assert metadata["length"] is None
    assert "comfort_5" in searchable_text
    assert "formality_1" in searchable_text
    assert "silhouette_" not in searchable_text
    assert "length_" not in searchable_text


def test_fashion_scoring_does_not_warn_for_footwear_without_fit() -> None:
    """Footwear with fit=None must not trigger 'fit_unknown' warning in proportion evaluation."""
    top_slot = OutfitItemSlot(
        item_id="top-1",
        slot_role=OutfitSlotRole.TOP,
        name="Áo thun trắng",
        sub_category="t-shirt",
        primary_color="white",
        style="casual",
        category=WardrobeCategory.TOP,
        fit="regular",
        silhouette_level=3,
        length="hip",
        formality_level=2,
    )
    bot_slot = OutfitItemSlot(
        item_id="bot-1",
        slot_role=OutfitSlotRole.BOTTOM,
        name="Quần jean xanh",
        sub_category="jeans",
        primary_color="blue",
        style="casual",
        category=WardrobeCategory.BOTTOM,
        fit="regular",
        silhouette_level=3,
        length="long",
        formality_level=2,
    )
    shoe_slot = OutfitItemSlot(
        item_id="shoe-1",
        slot_role=OutfitSlotRole.FOOTWEAR,
        name="Giày sneaker trắng",
        sub_category="sneakers",
        primary_color="white",
        style="casual",
        category=WardrobeCategory.FOOTWEAR,
        fit=None,  # null for shoes
        silhouette_level=None,
        length=None,
        formality_level=2,
    )

    score, warnings = calculate_proportion_score(
        items=[top_slot, bot_slot, shoe_slot],
        target_style="casual",
    )
    assert "fit_unknown" not in warnings
    assert score >= 0.8
