"""Add comfort_level, silhouette_level, and length to wardrobe_items.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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


def downgrade() -> None:
    with op.batch_alter_table("wardrobe_items") as batch:
        batch.drop_column("length")
        batch.drop_column("silhouette_level")
        batch.drop_column("comfort_level")
