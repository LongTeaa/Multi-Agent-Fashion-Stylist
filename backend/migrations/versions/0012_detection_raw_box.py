"""Retain raw detector bounds independently of padded or manually edited crops."""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Unknown historical raw bounds must stay null, never guessed from edited boxes.
    op.execute("ALTER TABLE ingestion_detections ADD COLUMN raw_bounding_box JSON")


def downgrade() -> None:
    op.drop_column("ingestion_detections", "raw_bounding_box")
