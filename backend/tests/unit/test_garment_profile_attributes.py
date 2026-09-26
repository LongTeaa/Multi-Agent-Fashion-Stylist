from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from app.agents.state import OutfitItemSlot
from app.models import (
    MediaAsset,
    MediaKind,
    OutfitSlotRole,
    User,
    VALID_FUNCTIONAL_FLAGS,
    VALID_LENGTH_VALUES,
    WardrobeCategory,
    WardrobeItem,
    WardrobeRetrievalDocument,
)
from app.schemas.ingestion import CustomAttributesUpdate, IngestionConfirmRequest
from app.schemas.wardrobe import (
    WardrobeItemAttributes,
    WardrobeItemCreate,
    WardrobeItemResponseData,
    WardrobeItemUpdate,
)
from app.services.retrieval_document_service import build_retrieval_document, refresh_retrieval_document
from app.services.wardrobe_service import create_wardrobe_item, update_wardrobe_item


# ============================================================================
# 1. TAXONOMY & ENUM CONSTRAINTS
# ============================================================================

def test_taxonomy_constants_contain_expert_guidelines() -> None:
    """Taxonomy constants for functional flags and lengths must reflect the Expert's feedback."""
    expected_flags = {"movement", "outdoor", "rain", "sun", "work", "sport", "protection"}
    assert expected_flags.issubset(VALID_FUNCTIONAL_FLAGS)

    expected_lengths = {"cropped", "waist", "hip", "long"}
    assert expected_lengths.issubset(VALID_LENGTH_VALUES)


def test_invalid_length_is_rejected_by_schemas() -> None:
    """Invalid length values must be rejected by Pydantic schemas."""
    with pytest.raises(ValidationError) as exc:
        WardrobeItemAttributes(
            category=WardrobeCategory.TOP,
            sub_category="t-shirt",
            primary_color="white",
            pattern="solid",
            material="cotton",
            style="casual",
            fit="regular",
            formality_level=2,
            length="invalid_floor_length_xyz",
        )
    assert "Độ dài (length) phải thuộc" in str(exc.value)

    with pytest.raises(ValidationError) as exc2:
        CustomAttributesUpdate(length="unknown_length")
    assert "Độ dài (length) phải thuộc" in str(exc2.value)


def test_functional_flags_are_lowercased_and_trimmed() -> None:
    """Functional flags must automatically be lowercased and whitespace-trimmed."""
    attr = WardrobeItemAttributes(
        category=WardrobeCategory.TOP,
        sub_category="jacket",
        primary_color="black",
        pattern="solid",
        material="polyester",
        style="casual",
        fit="regular",
        formality_level=2,
        functional_flags=["  OUTDOOR ", "Movement ", "SUN"],
    )
    assert attr.functional_flags == ["outdoor", "movement", "sun"]


# ============================================================================
# 2. REAL SQLITE DATABASE CONSTRAINTS (CheckConstraint enforcement)
# ============================================================================

@pytest.fixture
def memory_db_session() -> Session:
    """Create an in-memory SQLite database with enforced foreign keys & check constraints."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Enable SQLite CHECK constraints
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys = ON")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Create test owner user
        user = User(id="user-test-1", email="test@example.com")
        session.add(user)
        session.commit()
        yield session


def test_db_check_constraint_rejects_out_of_bound_comfort(memory_db_session: Session) -> None:
    """Database CHECK constraint ck_wardrobe_items_comfort_level must reject values < 1 or > 5."""
    item_invalid_low = WardrobeItem(
        id="item-low",
        user_id="user-test-1",
        category=WardrobeCategory.TOP,
        sub_category="shirt",
        primary_color="blue",
        pattern="solid",
        material="cotton",
        style="casual",
        fit="regular",
        formality_level=3,
        comfort_level=0,  # Violates CHECK (comfort_level BETWEEN 1 AND 5)
        silhouette_level=3,
        length="hip",
    )
    memory_db_session.add(item_invalid_low)
    with pytest.raises(IntegrityError):
        memory_db_session.commit()
    memory_db_session.rollback()

    item_invalid_high = WardrobeItem(
        id="item-high",
        user_id="user-test-1",
        category=WardrobeCategory.TOP,
        sub_category="shirt",
        primary_color="blue",
        pattern="solid",
        material="cotton",
        style="casual",
        fit="regular",
        formality_level=3,
        comfort_level=6,  # Violates CHECK
        silhouette_level=3,
        length="hip",
    )
    memory_db_session.add(item_invalid_high)
    with pytest.raises(IntegrityError):
        memory_db_session.commit()
    memory_db_session.rollback()


def test_db_check_constraint_rejects_out_of_bound_silhouette(memory_db_session: Session) -> None:
    """Database CHECK constraint ck_wardrobe_items_silhouette_level must reject values < 1 or > 5."""
    item_invalid = WardrobeItem(
        id="item-sil-bad",
        user_id="user-test-1",
        category=WardrobeCategory.BOTTOM,
        sub_category="jeans",
        primary_color="navy",
        pattern="solid",
        material="denim",
        style="casual",
        fit="regular",
        formality_level=3,
        comfort_level=3,
        silhouette_level=10,  # Violates CHECK
        length="long",
    )
    memory_db_session.add(item_invalid)
    with pytest.raises(IntegrityError):
        memory_db_session.commit()
    memory_db_session.rollback()


# ============================================================================
# 3. WARDROBE SERVICE CRUD & RETRIEVAL DOCUMENT SYNCHRONIZATION
# ============================================================================

def test_wardrobe_service_crud_persists_profile_fields(memory_db_session: Session) -> None:
    """create_wardrobe_item and update_wardrobe_item must persist and return all 3 profile fields."""
    # 1. Create a media asset first
    asset = MediaAsset(
        id="asset-1",
        user_id="user-test-1",
        kind=MediaKind.ORIGINAL,
        bucket="wardrobe-private",
        object_key="test.jpg",
        mime_type="image/jpeg",
        size_bytes=1024,
        width=200,
        height=200,
        sha256="a" * 64,
    )
    memory_db_session.add(asset)
    memory_db_session.commit()

    # 2. Create WardrobeItem via service
    create_payload = WardrobeItemCreate(
        category=WardrobeCategory.TOP,
        sub_category="blouse",
        primary_color="white",
        pattern="solid",
        material="silk",
        style="formal",
        fit="fitted",
        formality_level=4,
        comfort_level=5,
        silhouette_level=2,
        length="waist",
        functional_flags=["work"],
        media_asset_id="asset-1",
    )
    response = create_wardrobe_item(
        session=memory_db_session,
        user_id="user-test-1",
        payload=create_payload,
    )
    assert response.comfort_level == 5
    assert response.silhouette_level == 2
    assert response.length == "waist"

    # Verify directly from Database
    db_item = memory_db_session.get(WardrobeItem, response.id)
    assert db_item is not None
    assert db_item.comfort_level == 5
    assert db_item.silhouette_level == 2
    assert db_item.length == "waist"

    # Verify Retrieval Document synchronization
    retrieval_doc = memory_db_session.get(WardrobeRetrievalDocument, response.id)
    assert retrieval_doc is not None
    assert retrieval_doc.metadata_snapshot["comfort_level"] == 5
    assert retrieval_doc.metadata_snapshot["silhouette_level"] == 2
    assert retrieval_doc.metadata_snapshot["length"] == "waist"
    assert "comfort_5" in retrieval_doc.searchable_text
    assert "silhouette_2" in retrieval_doc.searchable_text
    assert "length_waist" in retrieval_doc.searchable_text
    assert "waist" in retrieval_doc.searchable_text

    # 3. Update WardrobeItem via service
    update_payload = WardrobeItemUpdate(
        comfort_level=4,
        silhouette_level=3,
        length="hip",
    )
    updated_response = update_wardrobe_item(
        session=memory_db_session,
        user_id="user-test-1",
        item_id=response.id,
        payload=update_payload,
    )
    assert updated_response.comfort_level == 4
    assert updated_response.silhouette_level == 3
    assert updated_response.length == "hip"

    # Verify DB update
    memory_db_session.refresh(db_item)
    assert db_item.comfort_level == 4
    assert db_item.silhouette_level == 3
    assert db_item.length == "hip"

    # Verify Retrieval Document updated
    memory_db_session.refresh(retrieval_doc)
    assert retrieval_doc.metadata_snapshot["comfort_level"] == 4
    assert "comfort_4" in retrieval_doc.searchable_text


# ============================================================================
# 4. INGESTION CONFIRMATION VALIDATION CONSTRAINTS
# ============================================================================

def test_ingestion_confirm_validates_profile_attributes() -> None:
    """Ingestion confirmation must reject invalid comfort_level, silhouette_level, and length."""
    # Invalid comfort_level
    with pytest.raises(ValidationError) as exc1:
        IngestionConfirmRequest.model_validate(
            {
                "confirmations": [
                    {
                        "detection_id": "det-1",
                        "accepted": True,
                        "custom_attributes": {"comfort_level": 0},
                    }
                ]
            }
        )
    assert any("comfort_level" in str(err["loc"]) for err in exc1.value.errors())

    # Invalid silhouette_level
    with pytest.raises(ValidationError) as exc2:
        IngestionConfirmRequest.model_validate(
            {
                "confirmations": [
                    {
                        "detection_id": "det-1",
                        "accepted": True,
                        "custom_attributes": {"silhouette_level": 6},
                    }
                ]
            }
        )
    assert any("silhouette_level" in str(err["loc"]) for err in exc2.value.errors())

    # Invalid length
    with pytest.raises(ValidationError) as exc3:
        IngestionConfirmRequest.model_validate(
            {
                "confirmations": [
                    {
                        "detection_id": "det-1",
                        "accepted": True,
                        "custom_attributes": {"length": "extremely_long"},
                    }
                ]
            }
        )
    assert "Độ dài (length) phải thuộc" in str(exc3.value)


# ============================================================================
# 5. REAL DATABASE BACKWARD COMPATIBILITY TEST (data/fashion_stylist.db)
# ============================================================================

def test_real_database_migration_backward_compatibility() -> None:
    """Verify that all existing records in data/fashion_stylist.db safely migrated to valid defaults."""
    db_path = Path(__file__).resolve().parents[3] / "data" / "fashion_stylist.db"
    if not db_path.exists():
        pytest.skip("data/fashion_stylist.db not present in workspace")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check migration version is 0008
    cursor.execute("SELECT version_num FROM alembic_version")
    version = cursor.fetchone()
    assert version is not None and version[0] == "0008"

    # Query all existing items
    cursor.execute(
        "SELECT id, category, formality_level, comfort_level, silhouette_level, length FROM wardrobe_items"
    )
    items = cursor.fetchall()
    assert len(items) > 0, "Database should contain existing test items"

    for item_id, category, formality, comfort, silhouette, length in items:
        # Must be valid integers within [1, 5]
        assert 1 <= formality <= 5, f"Item {item_id} has invalid formality_level {formality}"
        assert 1 <= comfort <= 5, f"Item {item_id} has invalid comfort_level {comfort}"
        assert 1 <= silhouette <= 5, f"Item {item_id} has invalid silhouette_level {silhouette}"
        # Must have valid length value
        assert length in VALID_LENGTH_VALUES, f"Item {item_id} has invalid length {length}"
        # Default migrated records must have standard default values
        assert comfort == 3
        assert silhouette == 3
        assert length == "hip"

    conn.close()
