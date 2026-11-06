"""Add tryon_avatars table and expand tryon_renders for virtual tryon.

Revision ID: 0013
Revises: 0012
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create tryon_avatars table
    op.create_table(
        "tryon_avatars",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column("user_id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
        sa.Column("media_asset_id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=True),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False, server_default="Ảnh của tôi"),
        sa.Column("is_preset", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("preset_gender", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_tryon_avatars_user"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tryon_avatars_user", "tryon_avatars", ["user_id"], unique=False)

    # 2. Add columns and index to tryon_renders
    op.add_column("tryon_renders", sa.Column("avatar_id", sqlmodel.sql.sqltypes.AutoString(length=36), nullable=True))
    op.add_column("tryon_renders", sa.Column("selected_item_ids", sa.JSON(), nullable=True))
    op.add_column("tryon_renders", sa.Column("cache_key", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True))
    op.add_column("tryon_renders", sa.Column("render_mode", sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False, server_default="lookbook"))
    op.add_column("tryon_renders", sa.Column("error_code", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True))
    op.create_index("ix_tryon_renders_cache", "tryon_renders", ["user_id", "cache_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tryon_renders_cache", table_name="tryon_renders")
    with op.batch_alter_table("tryon_renders", schema=None) as batch_op:
        batch_op.drop_column("error_code")
        batch_op.drop_column("render_mode")
        batch_op.drop_column("cache_key")
        batch_op.drop_column("selected_item_ids")
        batch_op.drop_column("avatar_id")

    op.drop_index("ix_tryon_avatars_user", table_name="tryon_avatars")
    op.drop_table("tryon_avatars")
