import logging
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry
from sqlmodel import create_engine

from app.core.config import REPOSITORY_ROOT, get_settings

logger = logging.getLogger(__name__)


def resolve_sqlite_url(database_url: str) -> str:
    """Resolve relative SQLite database URLs against the repository root."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return database_url

    raw_path = database_url[len(prefix):]
    if not raw_path or raw_path == ":memory:":
        return database_url

    p = Path(raw_path)
    if p.is_absolute():
        return database_url

    resolved_path = (REPOSITORY_ROOT / raw_path).resolve()
    return f"sqlite:///{resolved_path.as_posix()}"


def _enable_sqlite_foreign_keys(
    dbapi_connection: DBAPIConnection,
    _: ConnectionPoolEntry,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_database_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create an engine that enforces SQLite foreign-key constraints."""

    canonical_url = resolve_sqlite_url(database_url)
    connect_args = {"check_same_thread": False} if canonical_url.startswith("sqlite") else {}
    engine = create_engine(canonical_url, echo=echo, connect_args=connect_args)

    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)

    return engine


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide database engine."""

    return create_database_engine(get_settings().database_url)


def validate_database_schema_revision(engine: Engine, expected_head: str = "0007") -> None:
    """Ensure the database schema has been migrated to the expected head revision."""
    with engine.connect() as connection:
        try:
            result = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
        except Exception as err:
            logger.warning("Could not read alembic_version table: %s", err)
            return

        if result is not None and result != expected_head:
            raise RuntimeError(
                f"Database schema revision mismatch: current database is at revision {result!r}, "
                f"but application requires {expected_head!r}. "
                "Please run 'alembic upgrade head' before starting the application."
            )
