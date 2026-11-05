"""Link detections to their original image without guessing ambiguous legacy batches."""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite permits an inline nullable reference without rebuilding a table
    # referenced by confirmed wardrobe items.
    op.execute("ALTER TABLE ingestion_detections ADD COLUMN source_media_asset_id VARCHAR(36) REFERENCES media_assets(id)")
    op.execute("""UPDATE ingestion_detections SET source_media_asset_id = (
        SELECT MIN(id) FROM media_assets WHERE ingestion_batch_id = ingestion_detections.ingestion_batch_id
        AND user_id = ingestion_detections.user_id AND kind = 'original')
        WHERE (SELECT COUNT(*) FROM media_assets
        WHERE ingestion_batch_id = ingestion_detections.ingestion_batch_id
        AND user_id = ingestion_detections.user_id AND kind = 'original') = 1""")


def downgrade() -> None:
    op.drop_column("ingestion_detections", "source_media_asset_id")
