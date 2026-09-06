"""Shared pytest fixtures for the backend test suite."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from app.core.config import get_settings
from app.core.database import create_database_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]


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
