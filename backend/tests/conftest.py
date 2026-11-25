"""Shared pytest fixtures for the backend test suite."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from app.core.config import get_settings
from app.core.database import create_database_engine, get_engine
from app.main import app

BACKEND_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline_context_weather(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Local live-provider configuration must never turn default regression into API calls."""
    if request.node.get_closest_marker("live_provider") is None:
        monkeypatch.setenv("CONTEXT_PROVIDER", "fallback")
        monkeypatch.setenv("WEATHER_PROVIDER", "disabled")
        monkeypatch.setenv("DETECTOR_BACKEND", "auto")
        monkeypatch.setenv("DETECTOR_FALLBACK_BACKEND", "none")
        # An empty value overrides a local .env entry; blank falls back to VISION_MODEL.
        monkeypatch.setenv("DETECTOR_MODEL", "")
        monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_settings.cache_clear()
    _reset_engine_cache()
    yield
    get_settings.cache_clear()
    _reset_engine_cache()


def _reset_engine_cache() -> None:
    """get_engine() is process-cached; a stale engine would keep pointing at whatever
    DATABASE_URL an earlier test (or the developer's .env) configured."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    get_engine.cache_clear()


@pytest.fixture(autouse=True)
def clean_dependency_overrides() -> Iterator[None]:
    try:
        yield
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def migrated_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[Config, Engine]]:
    database_path = tmp_path / "schema.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    _reset_engine_cache()

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    command.upgrade(alembic_config, "head")
    engine = create_database_engine(database_url)
    try:
        yield alembic_config, engine
    finally:
        engine.dispose()
