"""Merge wardrobe records from a legacy SQLite file into the canonical database.

The source is never modified. The default mode only reports what would be copied.
Stop the API and cleanup scheduler before running with --apply.
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


TABLES = (
    "users",
    "ingestion_batches",
    "media_assets",
    "ingestion_detections",
    "wardrobe_items",
    "item_media",
    "wardrobe_retrieval_documents",
)
EXPECTED_REVISION = "0007"


def _revision(connection: sqlite3.Connection) -> str | None:
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.DatabaseError as error:
        raise ValueError("Database has no readable Alembic revision") from error
    return row[0] if row else None


def _primary_key(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
    if not columns:
        raise ValueError(f"Missing table: {table}")
    return tuple(column[1] for column in sorted(columns, key=lambda column: column[5]) if column[5])


def merge_wardrobe_databases(source_path: Path, target_path: Path, *, apply: bool = False) -> dict[str, int]:
    source_path = source_path.resolve(strict=True)
    target_path = target_path.resolve(strict=True)
    if source_path == target_path:
        raise ValueError("Source and target databases must be different files")

    source = sqlite3.connect(f"file:{source_path.as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(f"file:{target_path.as_posix()}?mode=rw", uri=True)
    source.row_factory = sqlite3.Row
    target.row_factory = sqlite3.Row
    try:
        source.execute("PRAGMA foreign_keys=ON")
        target.execute("PRAGMA foreign_keys=ON")
        if _revision(source) != EXPECTED_REVISION or _revision(target) != EXPECTED_REVISION:
            raise ValueError(f"Both databases must be at revision {EXPECTED_REVISION}")
        if source.execute("PRAGMA foreign_key_check").fetchone() or target.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("A database already contains broken foreign keys")

        user_ids = [row[0] for row in source.execute("SELECT DISTINCT user_id FROM wardrobe_items")]
        counts = {table: 0 for table in TABLES}
        if not user_ids:
            return counts

        # A single transaction ensures no partial import if a key conflicts.
        # The API must be stopped so the backup and write see one stable state.
        if apply:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            for label, connection, path in (("source", source, source_path), ("target", target, target_path)):
                backup_path = path.with_name(f"{path.stem}.{label}.before_merge_{stamp}{path.suffix}")
                with sqlite3.connect(backup_path) as backup:
                    connection.backup(backup)
                print(f"Backup: {backup_path}")
            target.execute("BEGIN IMMEDIATE")

        placeholders = ", ".join("?" for _ in user_ids)
        for table in TABLES:
            key = "id" if table == "users" else "user_id"
            rows = source.execute(
                f"SELECT * FROM {table} WHERE {key} IN ({placeholders})", user_ids
            ).fetchall()
            primary_key = _primary_key(target, table)
            for row in rows:
                predicate = " AND ".join(f"{column} = ?" for column in primary_key)
                existing = target.execute(
                    f"SELECT * FROM {table} WHERE {predicate}",
                    [row[column] for column in primary_key],
                ).fetchone()
                if existing:
                    if table == "media_assets" and (
                        existing["user_id"] != row["user_id"]
                        or existing["bucket"] != row["bucket"]
                        or existing["object_key"] != row["object_key"]
                    ):
                        raise ValueError("Conflicting media asset identity; import aborted")
                    if table not in ("users", "media_assets") and "user_id" in row.keys() and existing["user_id"] != row["user_id"]:
                        raise ValueError(f"Conflicting owner in {table}; import aborted")
                    continue
                counts[table] += 1
                if apply:
                    columns = row.keys()
                    target.execute(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                        tuple(row),
                    )

        if apply:
            violations = target.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise ValueError(f"Import would break {len(violations)} foreign keys")
            target.commit()
        return counts
    except Exception:
        target.rollback()
        raise
    finally:
        source.close()
        target.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Legacy SQLite database")
    parser.add_argument("target", type=Path, help="Canonical SQLite database")
    parser.add_argument("--apply", action="store_true", help="Back up both files and import missing records")
    args = parser.parse_args()
    counts = merge_wardrobe_databases(args.source, args.target, apply=args.apply)
    print("Missing records: " + ", ".join(f"{table}={count}" for table, count in counts.items()))
    if not args.apply:
        print("Dry run only. Stop the API, then rerun with --apply to import.")


if __name__ == "__main__":
    main()
