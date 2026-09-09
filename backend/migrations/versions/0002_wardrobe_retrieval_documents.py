"""add wardrobe retrieval documents

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-09
"""

from collections.abc import Sequence
from datetime import datetime, timezone
import unicodedata

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize(value: object) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", str(value or "")).strip().lower().split()
    )


def upgrade() -> None:
    op.create_table(
        "wardrobe_retrieval_documents",
        sa.Column(
            "wardrobe_item_id",
            sqlmodel.sql.sqltypes.AutoString(length=36),
            nullable=False,
        ),
        sa.Column(
            "user_id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False
        ),
        sa.Column("searchable_text", sa.Text(), nullable=False),
        sa.Column("metadata_snapshot", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_wardrobe_retrieval_documents_user"
        ),
        sa.ForeignKeyConstraint(
            ["wardrobe_item_id", "user_id"],
            ["wardrobe_items.id", "wardrobe_items.user_id"],
            name="fk_wardrobe_retrieval_documents_item_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("wardrobe_item_id"),
    )
    with op.batch_alter_table("wardrobe_retrieval_documents") as batch_op:
        batch_op.create_index(
            "ix_wardrobe_retrieval_documents_user_id", ["user_id"], unique=False
        )
        batch_op.create_index(
            "ix_wardrobe_retrieval_documents_user_updated",
            ["user_id", "updated_at"],
            unique=False,
        )

    connection = op.get_bind()
    wardrobe_items = sa.table(
        "wardrobe_items",
        sa.column("id", sa.String()),
        sa.column("user_id", sa.String()),
        sa.column("category", sa.String()),
        sa.column("sub_category", sa.String()),
        sa.column("primary_color", sa.String()),
        sa.column("secondary_color", sa.String()),
        sa.column("pattern", sa.String()),
        sa.column("material", sa.String()),
        sa.column("style", sa.String()),
        sa.column("fit", sa.String()),
        sa.column("formality_level", sa.Integer()),
        sa.column("season", sa.JSON()),
        sa.column("weather_suitability", sa.JSON()),
        sa.column("functional_flags", sa.JSON()),
        sa.column("free_text_tags", sa.JSON()),
        sa.column("is_active", sa.Boolean()),
        sa.column("is_user_confirmed", sa.Boolean()),
        sa.column("deleted_at", sa.DateTime()),
    )
    retrieval_documents = sa.table(
        "wardrobe_retrieval_documents",
        sa.column("wardrobe_item_id", sa.String()),
        sa.column("user_id", sa.String()),
        sa.column("searchable_text", sa.Text()),
        sa.column("metadata_snapshot", sa.JSON()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    rows = connection.execute(
        sa.select(wardrobe_items).where(
            wardrobe_items.c.is_active.is_(True),
            wardrobe_items.c.is_user_confirmed.is_(True),
            wardrobe_items.c.deleted_at.is_(None),
        )
    ).mappings()
    scalar_fields = (
        "category",
        "sub_category",
        "primary_color",
        "secondary_color",
        "pattern",
        "material",
        "style",
        "fit",
    )
    list_fields = (
        "season",
        "weather_suitability",
        "functional_flags",
        "free_text_tags",
    )
    for row in rows:
        metadata = {field: row[field] for field in scalar_fields}
        metadata.update({field: list(row[field] or []) for field in list_fields})
        metadata["formality_level"] = row["formality_level"]
        tokens = [_normalize(metadata[field]) for field in scalar_fields]
        for field in list_fields:
            tokens.extend(_normalize(value) for value in metadata[field])
        tokens.append(f"formality_{row['formality_level']}")
        connection.execute(
            retrieval_documents.insert().values(
                wardrobe_item_id=row["id"],
                user_id=row["user_id"],
                searchable_text=" ".join(
                    dict.fromkeys(token for token in tokens if token)
                ),
                metadata_snapshot=metadata,
                updated_at=datetime.now(timezone.utc),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("wardrobe_retrieval_documents") as batch_op:
        batch_op.drop_index("ix_wardrobe_retrieval_documents_user_updated")
        batch_op.drop_index("ix_wardrobe_retrieval_documents_user_id")
    op.drop_table("wardrobe_retrieval_documents")
