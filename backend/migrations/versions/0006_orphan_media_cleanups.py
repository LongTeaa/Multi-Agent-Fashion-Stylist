"""create orphan_media_cleanups table

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-19
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orphan_media_cleanups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("bucket", sa.String(length=100), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_orphan_media_cleanups_user"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orphan_media_cleanups_user", "orphan_media_cleanups", ["user_id"])
    op.create_index("ix_orphan_media_cleanups_created", "orphan_media_cleanups", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_orphan_media_cleanups_created", table_name="orphan_media_cleanups")
    op.drop_index("ix_orphan_media_cleanups_user", table_name="orphan_media_cleanups")
    op.drop_table("orphan_media_cleanups")
