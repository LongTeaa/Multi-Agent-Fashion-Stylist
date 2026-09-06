from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.database import create_database_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]
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


@pytest.fixture
def migrated_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Config, Engine]]:
    database_path = tmp_path / "schema.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")
    engine = create_database_engine(database_url)

    try:
        yield alembic_config, engine
    finally:
        engine.dispose()
        get_settings.cache_clear()


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
