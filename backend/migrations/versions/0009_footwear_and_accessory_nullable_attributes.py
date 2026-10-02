"""Make fit, silhouette_level, and length nullable for footwear and accessories.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql.selectable import TableClause

revision: str = "0009"
down_revision: str | None = "0008"
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


def _wardrobe_items_table() -> TableClause:
    return sa.table(
        "wardrobe_items",
        sa.column("id", sa.String()),
        sa.column("category", sa.String()),
        sa.column("fit", sa.String()),
        sa.column("silhouette_level", sa.Integer()),
        sa.column("length", sa.String()),
    )


def upgrade() -> None:
    with op.batch_alter_table("wardrobe_items") as batch:
        batch.drop_constraint("ck_wardrobe_items_length", type_="check")
        batch.drop_constraint("ck_wardrobe_items_silhouette_level", type_="check")
        batch.alter_column(
            "fit",
            existing_type=sa.String(length=100),
            nullable=True,
        )
        batch.alter_column(
            "silhouette_level",
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
        )
        batch.alter_column(
            "length",
            existing_type=sa.String(length=50),
            nullable=True,
            server_default=None,
        )
        batch.create_check_constraint(
            "ck_wardrobe_items_silhouette_level",
            "silhouette_level IS NULL OR (silhouette_level BETWEEN 1 AND 5)",
        )
        batch.create_check_constraint(
            "ck_wardrobe_items_length",
            "length IS NULL OR (length IN ('cropped', 'waist', 'hip', 'long'))",
        )

    # Clean existing data for footwear and accessories
    connection = op.get_bind()
    items_table = _wardrobe_items_table()
    connection.execute(
        items_table.update()
        .where(items_table.c.category.in_(["footwear", "accessory"]))
        .values(fit=None, silhouette_level=None, length=None)
    )

    # Sync retrieval documents for existing footwear & accessory items
    docs_table = _retrieval_documents_table()
    doc_rows = [
        dict(row)
        for row in connection.execute(
            sa.select(docs_table, items_table.c.category)
            .select_from(
                docs_table.join(
                    items_table,
                    docs_table.c.wardrobe_item_id == items_table.c.id,
                )
            )
            .where(items_table.c.category.in_(["footwear", "accessory"]))
        ).mappings()
    ]

    for row in doc_rows:
        metadata = dict(row.get("metadata_snapshot") or {})
        metadata["fit"] = None
        metadata["silhouette_level"] = None
        metadata["length"] = None

        searchable_text = str(row.get("searchable_text") or "")
        cleaned_tokens = [
            token
            for token in searchable_text.split()
            if not token.startswith("silhouette_")
            and not token.startswith("length_")
            and token not in {"cropped", "waist", "hip", "long"}
        ]
        new_searchable_text = " ".join(cleaned_tokens)

        connection.execute(
            docs_table.update()
            .where(docs_table.c.wardrobe_item_id == row["wardrobe_item_id"])
            .values(
                searchable_text=new_searchable_text,
                metadata_snapshot=metadata,
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    items_table = _wardrobe_items_table()
    # Backfill default values for any rows where fit, silhouette_level, or length is NULL
    connection.execute(
        items_table.update()
        .where(items_table.c.fit.is_(None))
        .values(fit="regular")
    )
    connection.execute(
        items_table.update()
        .where(items_table.c.silhouette_level.is_(None))
        .values(silhouette_level=3)
    )
    connection.execute(
        items_table.update()
        .where(items_table.c.length.is_(None))
        .values(length="hip")
    )

    with op.batch_alter_table("wardrobe_items") as batch:
        batch.drop_constraint("ck_wardrobe_items_length", type_="check")
        batch.drop_constraint("ck_wardrobe_items_silhouette_level", type_="check")
        batch.alter_column(
            "fit",
            existing_type=sa.String(length=100),
            nullable=False,
            server_default="regular",
        )
        batch.alter_column(
            "silhouette_level",
            existing_type=sa.Integer(),
            nullable=False,
            server_default="3",
        )
        batch.alter_column(
            "length",
            existing_type=sa.String(length=50),
            nullable=False,
            server_default="hip",
        )
        batch.create_check_constraint(
            "ck_wardrobe_items_silhouette_level",
            "silhouette_level BETWEEN 1 AND 5",
        )
        batch.create_check_constraint(
            "ck_wardrobe_items_length",
            "length IN ('cropped', 'waist', 'hip', 'long')",
        )
