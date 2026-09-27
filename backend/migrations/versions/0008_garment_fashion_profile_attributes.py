"""Add comfort_level, silhouette_level, and length to wardrobe_items.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.selectable import TableClause

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _retrieval_documents_table() -> TableClause:
    return sa.table(
        "wardrobe_retrieval_documents",
        sa.column("wardrobe_item_id", sa.String()),
        sa.column("user_id", sa.String()),
        sa.column("searchable_text", sa.Text()),
        sa.column("metadata_snapshot", sa.JSON()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _snapshot_retrieval_documents() -> list[dict[str, object]]:
    connection = op.get_bind()
    table = _retrieval_documents_table()
    return [dict(row) for row in connection.execute(sa.select(table)).mappings()]


def _restore_retrieval_documents(
    rows: list[dict[str, object]],
    *,
    include_profile_defaults: bool,
) -> None:
    if not rows:
        return
    connection = op.get_bind()
    table = _retrieval_documents_table()
    connection.execute(table.delete())
    for row in rows:
        metadata = dict(row.get("metadata_snapshot") or {})
        searchable_text = str(row.get("searchable_text") or "")
        if include_profile_defaults:
            metadata.update(
                comfort_level=3,
                silhouette_level=3,
                length="hip",
            )
            searchable_text = " ".join(
                token
                for token in (
                    searchable_text,
                    "comfort_3",
                    "silhouette_3",
                    "length_hip",
                    "hip",
                )
                if token
            )
        connection.execute(
            table.insert().values(
                wardrobe_item_id=row["wardrobe_item_id"],
                user_id=row["user_id"],
                searchable_text=searchable_text,
                metadata_snapshot=metadata,
                updated_at=row["updated_at"],
            )
        )


def upgrade() -> None:
    retrieval_documents = _snapshot_retrieval_documents()
    with op.batch_alter_table("wardrobe_items") as batch:
        batch.add_column(
            sa.Column(
                "comfort_level",
                sa.Integer(),
                nullable=False,
                server_default="3",
            )
        )
        batch.add_column(
            sa.Column(
                "silhouette_level",
                sa.Integer(),
                nullable=False,
                server_default="3",
            )
        )
        batch.add_column(
            sa.Column(
                "length",
                sa.String(length=50),
                nullable=False,
                server_default="hip",
            )
        )
        batch.create_check_constraint(
            "ck_wardrobe_items_comfort_level",
            "comfort_level BETWEEN 1 AND 5",
        )
        batch.create_check_constraint(
            "ck_wardrobe_items_silhouette_level",
            "silhouette_level BETWEEN 1 AND 5",
        )
        batch.create_check_constraint(
            "ck_wardrobe_items_length",
            "length IN ('cropped', 'waist', 'hip', 'long')",
        )
    _restore_retrieval_documents(
        retrieval_documents,
        include_profile_defaults=True,
    )


def downgrade() -> None:
    retrieval_documents = _snapshot_retrieval_documents()
    with op.batch_alter_table("wardrobe_items") as batch:
        batch.drop_constraint("ck_wardrobe_items_length", type_="check")
        batch.drop_constraint("ck_wardrobe_items_silhouette_level", type_="check")
        batch.drop_constraint("ck_wardrobe_items_comfort_level", type_="check")
        batch.drop_column("length")
        batch.drop_column("silhouette_level")
        batch.drop_column("comfort_level")
    _restore_retrieval_documents(
        retrieval_documents,
        include_profile_defaults=False,
    )
