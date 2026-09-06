from functools import lru_cache

from sqlalchemy import Engine, event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool import ConnectionPoolEntry
from sqlmodel import create_engine

from app.core.config import get_settings


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

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, echo=echo, connect_args=connect_args)

    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)

    return engine


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide database engine."""

    return create_database_engine(get_settings().database_url)
