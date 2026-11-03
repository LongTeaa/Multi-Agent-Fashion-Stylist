"""Canonical UUIDs for existing golden items without losing references or media."""
from uuid import NAMESPACE_URL, uuid5
import json

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

OWNER = str(uuid5(NAMESPACE_URL, "https://multi-agent-fashion-stylist.local/fixtures/golden-user"))
NAMES = [f"item-{kind}-{index:02}" for kind, size in (("top", 3), ("bottom", 3), ("shoes", 2))
         for index in range(1, size + 1)]


def _rewrite(value: object, mapping: dict[str, str], field: str = "") -> object:
    if isinstance(value, str):
        return mapping.get(value, value) if field in {"item_id", "wardrobe_item_id", "item_ids", "wardrobe_item_ids"} else value
    if isinstance(value, list):
        return [_rewrite(item, mapping, field) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite(item, mapping, key) for key, item in value.items()}
    return value


def _migrate(mapping: dict[str, str]) -> None:
    connection = op.get_bind()
    # pysqlite can have a SQLAlchemy transaction without a real SQLite BEGIN
    # after schema/version reads. Deferral must live inside the data transaction.
    if not connection.connection.driver_connection.in_transaction:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
    connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
    actual: dict[str, str] = {}
    for old, new in mapping.items():
        exists = connection.execute(sa.text("SELECT id FROM wardrobe_items WHERE id=:id AND user_id=:owner"),
                                    {"id": old, "owner": OWNER}).first()
        if not exists:
            continue
        if connection.execute(sa.text("SELECT id FROM wardrobe_items WHERE id=:id"), {"id": new}).first():
            raise RuntimeError("Seed identifier collision; refusing to merge wardrobe data")
        actual[old] = new
        connection.execute(sa.text("UPDATE wardrobe_items SET id=:new WHERE id=:old AND user_id=:owner"),
                           {"new": new, "old": old, "owner": OWNER})
        for table in ("item_media", "outfit_items", "wardrobe_retrieval_documents"):
            connection.execute(sa.text(f"UPDATE {table} SET wardrobe_item_id=:new WHERE wardrobe_item_id=:old AND user_id=:owner"),
                               {"new": new, "old": old, "owner": OWNER})
    for table, column, keys in (("outfit_recommendations", "context_snapshot", ["id"]),
                                ("recommendation_requests", "response_data", ["user_id", "request_id"])):
        rows = connection.execute(sa.text(f"SELECT * FROM {table} WHERE user_id=:owner"), {"owner": OWNER}).mappings().all()
        for row in rows:
            if row[column] is None:
                continue
            data = json.loads(row[column]) if isinstance(row[column], str) else row[column]
            updated = _rewrite(data, actual)
            if updated != data:
                where = " AND ".join(f"{key}=:{key}" for key in keys)
                connection.execute(sa.text(f"UPDATE {table} SET {column}=:data WHERE {where}"),
                    {**{key: row[key] for key in keys}, "data": json.dumps(updated)})
    if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
        raise RuntimeError("Seed migration violated foreign keys")


def upgrade() -> None:
    _migrate({name: str(uuid5(NAMESPACE_URL, "multi-agent-fashion-stylist:golden:" + name)) for name in NAMES})


def downgrade() -> None:
    _migrate({str(uuid5(NAMESPACE_URL, "multi-agent-fashion-stylist:golden:" + name)): name for name in NAMES})
