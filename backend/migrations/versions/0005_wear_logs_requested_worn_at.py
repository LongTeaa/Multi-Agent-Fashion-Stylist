"""add requested_worn_at to wear_logs

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("wear_logs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "requested_worn_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("wear_logs", schema=None) as batch_op:
        batch_op.drop_column("requested_worn_at")
