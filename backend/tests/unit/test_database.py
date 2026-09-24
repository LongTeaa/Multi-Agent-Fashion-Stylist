from pathlib import Path
import pytest
from sqlalchemy import create_engine
from app.core.config import REPOSITORY_ROOT
from app.core.database import resolve_sqlite_url, validate_database_schema_revision


def test_resolve_sqlite_url_relative_path() -> None:
    raw_url = "sqlite:///./data/fashion_stylist.db"
    resolved = resolve_sqlite_url(raw_url)
    expected_path = (REPOSITORY_ROOT / "data" / "fashion_stylist.db").resolve().as_posix()
    assert resolved == f"sqlite:///{expected_path}"


def test_resolve_sqlite_url_absolute_path() -> None:
    abs_url = "sqlite:////tmp/some_absolute_path/test.db"
    resolved = resolve_sqlite_url(abs_url)
    assert resolved == abs_url


def test_resolve_sqlite_url_in_memory() -> None:
    mem_url = "sqlite:///:memory:"
    assert resolve_sqlite_url(mem_url) == mem_url


def test_resolve_sqlite_url_non_sqlite() -> None:
    pg_url = "postgresql://user:pass@localhost:5432/db"
    assert resolve_sqlite_url(pg_url) == pg_url


def test_validate_database_schema_revision_success() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        conn.exec_driver_sql("INSERT INTO alembic_version (version_num) VALUES ('0007')")

    # Should not raise
    validate_database_schema_revision(engine, expected_head="0007")


def test_validate_database_schema_revision_mismatch_raises() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
        conn.exec_driver_sql("INSERT INTO alembic_version (version_num) VALUES ('0005')")

    with pytest.raises(RuntimeError, match="Database schema revision mismatch"):
        validate_database_schema_revision(engine, expected_head="0007")


def test_validate_database_schema_revision_missing_table_raises() -> None:
    engine = create_engine("sqlite:///:memory:")
    with pytest.raises(RuntimeError, match="revision is unavailable"):
        validate_database_schema_revision(engine, expected_head="0007")


def test_validate_database_schema_revision_empty_table_raises() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="revision mismatch"):
        validate_database_schema_revision(engine, expected_head="0007")
