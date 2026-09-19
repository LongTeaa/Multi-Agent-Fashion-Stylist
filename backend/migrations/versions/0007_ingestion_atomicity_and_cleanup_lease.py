"""Store confirmation identity and delay cleanup of in-flight uploads.

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ingestion_batches") as batch:
        batch.add_column(sa.Column("confirmation_token", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("confirmation_fingerprint", sa.String(length=64), nullable=True))
    with op.batch_alter_table("orphan_media_cleanups") as batch:
        batch.add_column(
            sa.Column(
                "not_before",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("orphan_media_cleanups") as batch:
        batch.drop_column("not_before")
    with op.batch_alter_table("ingestion_batches") as batch:
        batch.drop_column("confirmation_fingerprint")
        batch.drop_column("confirmation_token")
