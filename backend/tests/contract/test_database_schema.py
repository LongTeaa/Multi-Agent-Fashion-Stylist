from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, Session

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import create_database_engine
from app.models import (
    DetectionStatus,
    IngestionBatch,
    IngestionDetection,
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    Rating,
    RatingSource,
    TryOnRender,
    User,
    WardrobeCategory,
    WardrobeItem,
)
from app.models.entities import utc_now

ENTITY_TABLES = {
    "users",
    "user_preferences",
    "ingestion_batches",
    "ingestion_detections",
    "media_assets",
    "wardrobe_items",
    "item_media",
    "outfit_recommendations",
    "outfit_items",
    "ratings",
    "feedback_prompt_state",
    "wear_logs",
    "tryon_renders",
}
REQUIRED_INDEXES = {
    "wardrobe_items": {
        "ix_wardrobe_items_user_active_category",
        "ix_wardrobe_items_user_color_style",
    },
    "outfit_recommendations": {"ix_outfit_recommendations_user_created"},
    "ratings": {"ix_ratings_user_created"},
    "wear_logs": {"ix_wear_logs_user_worn"},
}
OWNERSHIP_FOREIGN_KEYS = {
    "fk_ingestion_detections_batch_owner",
    "fk_ingestion_detections_crop_owner",
    "fk_item_media_asset_owner",
    "fk_item_media_item_owner",
    "fk_media_assets_batch_owner",
    "fk_outfit_items_item_owner",
    "fk_outfit_items_outfit_owner",
    "fk_ratings_outfit_owner",
    "fk_tryon_renders_media_owner",
    "fk_tryon_renders_outfit_owner",
    "fk_wardrobe_items_batch_owner",
    "fk_wardrobe_items_detection_owner",
    "fk_wear_logs_outfit_owner",
}


def test_migration_creates_all_mvp_tables_and_indexes(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    inspector = inspect(engine)

    assert ENTITY_TABLES <= set(inspector.get_table_names())
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    for table_name, expected_indexes in REQUIRED_INDEXES.items():
        index_names = {index["name"] for index in inspector.get_indexes(table_name)}
        assert expected_indexes <= index_names

    media_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("media_assets")
    }
    assert ("bucket", "object_key") in media_unique_constraints

    wardrobe_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("wardrobe_items")
    }
    assert ("ingestion_detection_id",) in wardrobe_unique_constraints


def test_migration_contains_database_constraints_for_normative_bounds(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    inspector = inspect(engine)

    constraint_names = {
        constraint["name"]
        for table_name in ENTITY_TABLES
        for constraint in inspector.get_check_constraints(table_name)
    }
    assert {
        "ck_feedback_prompt_state_next_threshold",
        "ck_media_assets_size_bytes",
        "ck_outfit_recommendations_composite_score",
        "ck_ratings_stars",
        "ck_tryon_renders_duration_ms",
        "ck_wardrobe_items_formality_level",
    } <= constraint_names

    foreign_key_names = {
        foreign_key["name"]
        for table_name in ENTITY_TABLES
        for foreign_key in inspector.get_foreign_keys(table_name)
        if foreign_key["name"] is not None
    }
    assert OWNERSHIP_FOREIGN_KEYS <= foreign_key_names


def test_migration_matches_sqlmodel_metadata(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database

    with engine.connect() as connection:
        migration_context = MigrationContext.configure(connection)
        differences = compare_metadata(migration_context, SQLModel.metadata)

    assert differences == []


def test_migration_can_downgrade_to_base(
    migrated_database: tuple[Config, Engine],
) -> None:
    alembic_config, engine = migrated_database
    engine.dispose()

    command.downgrade(alembic_config, "base")

    database_url = get_settings().database_url
    downgraded_engine = create_engine(database_url)
    try:
        remaining_tables = set(inspect(downgraded_engine).get_table_names())
    finally:
        downgraded_engine.dispose()

    assert ENTITY_TABLES.isdisjoint(remaining_tables)


def _new_user() -> User:
    return User(id=str(uuid4()))


def _new_wardrobe_item(user_id: str, *, item_id: str | None = None) -> WardrobeItem:
    return WardrobeItem(
        id=item_id or str(uuid4()),
        user_id=user_id,
        category=WardrobeCategory.TOP,
        sub_category="shirt",
        primary_color="white",
        pattern="solid",
        material="cotton",
        style="casual",
        fit="regular",
        formality_level=2,
        is_active=True,
        is_user_confirmed=True,
    )


def _new_outfit(user_id: str) -> OutfitRecommendation:
    return OutfitRecommendation(
        id=str(uuid4()),
        user_id=user_id,
        request_id=str(uuid4()),
        user_query="Test query",
        context_snapshot={},
        explanation_vi="Trang phục kiểm thử.",
        fashion_score=0.8,
        personalization_score=0.7,
        composite_score=0.75,
        rank=1,
        rule_version="test-v1",
    )


def _new_media_asset(user_id: str) -> MediaAsset:
    asset_id = str(uuid4())
    return MediaAsset(
        id=asset_id,
        user_id=user_id,
        kind=MediaKind.CROP,
        bucket="wardrobe-private",
        object_key=f"users/{user_id}/items/{asset_id}/crop/v1.png",
        mime_type="image/png",
        size_bytes=4,
        width=1,
        height=1,
        sha256="0" * 64,
    )


def test_outfit_item_rejects_cross_user_wardrobe_reference(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    owner = _new_user()
    other_user = _new_user()
    item = _new_wardrobe_item(owner.id)
    outfit = _new_outfit(other_user.id)

    with Session(engine) as session:
        session.add_all((owner, other_user))
        session.flush()
        session.add_all((item, outfit))
        session.commit()
        session.add(
            OutfitItem(
                outfit_id=outfit.id,
                wardrobe_item_id=item.id,
                user_id=other_user.id,
                slot_role=OutfitSlotRole.TOP,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_rating_rejects_cross_user_outfit_reference(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    owner = _new_user()
    other_user = _new_user()
    outfit = _new_outfit(owner.id)

    with Session(engine) as session:
        session.add_all((owner, other_user))
        session.flush()
        session.add(outfit)
        session.commit()
        session.add(
            Rating(
                user_id=other_user.id,
                outfit_id=outfit.id,
                stars=5,
                source=RatingSource.MANUAL,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_item_media_rejects_cross_user_item_reference(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    media_owner = _new_user()
    item_owner = _new_user()
    media = _new_media_asset(media_owner.id)
    item = _new_wardrobe_item(item_owner.id)

    with Session(engine) as session:
        session.add_all((media_owner, item_owner))
        session.flush()
        session.add_all((media, item))
        session.commit()
        session.add(
            ItemMedia(
                wardrobe_item_id=item.id,
                media_asset_id=media.id,
                user_id=media_owner.id,
                role=ItemMediaRole.PRIMARY,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_tryon_render_rejects_cross_user_media_reference(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    outfit_owner = _new_user()
    media_owner = _new_user()
    outfit = _new_outfit(outfit_owner.id)
    media = _new_media_asset(media_owner.id)

    with Session(engine) as session:
        session.add_all((outfit_owner, media_owner))
        session.flush()
        session.add_all((outfit, media))
        session.commit()
        session.add(
            TryOnRender(
                user_id=outfit_owner.id,
                outfit_id=outfit.id,
                media_asset_id=media.id,
                duration_ms=10,
                status="completed",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_detection_cannot_create_more_than_one_wardrobe_item(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    user = _new_user()
    batch = IngestionBatch(
        id=str(uuid4()),
        user_id=user.id,
        expires_at=utc_now() + timedelta(hours=24),
    )
    detection = IngestionDetection(
        id=str(uuid4()),
        user_id=user.id,
        ingestion_batch_id=batch.id,
        bounding_box=(0.0, 0.0, 1.0, 1.0),
        proposed_attributes={},
        field_confidence={},
        status=DetectionStatus.ACCEPTED,
    )
    first_item = _new_wardrobe_item(user.id)
    first_item.ingestion_batch_id = batch.id
    first_item.ingestion_detection_id = detection.id
    second_item = _new_wardrobe_item(user.id)
    second_item.ingestion_batch_id = batch.id
    second_item.ingestion_detection_id = detection.id

    with Session(engine) as session:
        session.add(user)
        session.flush()
        session.add(batch)
        session.flush()
        session.add(detection)
        session.flush()
        session.add_all((first_item, second_item))
        with pytest.raises(
            IntegrityError,
            match="UNIQUE constraint failed: wardrobe_items.ingestion_detection_id",
        ):
            session.commit()
