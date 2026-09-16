"""add wear logs idempotency, feedback suppressed sessions, and delivered outfits

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Update wear_logs with idempotency_key and unique constraint
    with op.batch_alter_table("wear_logs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "idempotency_key",
                sqlmodel.sql.sqltypes.AutoString(length=36),
                nullable=True,
            )
        )
        batch_op.create_unique_constraint(
            "uq_wear_logs_user_idempotency",
            ["user_id", "idempotency_key"],
        )

    # 2. Create feedback_suppressed_sessions table
    op.create_table(
        "feedback_suppressed_sessions",
        sa.Column(
            "user_id",
            sqlmodel.sql.sqltypes.AutoString(length=36),
            nullable=False,
        ),
        sa.Column(
            "client_session_id",
            sqlmodel.sql.sqltypes.AutoString(length=36),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_feedback_suppressed_sessions_user",
        ),
        sa.PrimaryKeyConstraint("user_id", "client_session_id"),
    )
    with op.batch_alter_table("feedback_suppressed_sessions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_feedback_suppressed_sessions_user",
            ["user_id"],
            unique=False,
        )

    # 3. Create feedback_delivered_outfits table
    op.create_table(
        "feedback_delivered_outfits",
        sa.Column(
            "id",
            sqlmodel.sql.sqltypes.AutoString(length=36),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sqlmodel.sql.sqltypes.AutoString(length=36),
            nullable=False,
        ),
        sa.Column(
            "outfit_id",
            sqlmodel.sql.sqltypes.AutoString(length=36),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            sqlmodel.sql.sqltypes.AutoString(length=36),
            nullable=False,
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["outfit_id", "user_id"],
            ["outfit_recommendations.id", "outfit_recommendations.user_id"],
            name="fk_feedback_delivered_outfits_outfit_owner",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "outfit_id", name="uq_feedback_delivered_outfits_user_outfit"
        ),
    )
    with op.batch_alter_table("feedback_delivered_outfits", schema=None) as batch_op:
        batch_op.create_index(
            "ix_feedback_delivered_outfits_user",
            ["user_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("feedback_delivered_outfits", schema=None) as batch_op:
        batch_op.drop_index("ix_feedback_delivered_outfits_user")
    op.drop_table("feedback_delivered_outfits")

    with op.batch_alter_table("feedback_suppressed_sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_feedback_suppressed_sessions_user")
    op.drop_table("feedback_suppressed_sessions")

    with op.batch_alter_table("wear_logs", schema=None) as batch_op:
        batch_op.drop_constraint("uq_wear_logs_user_idempotency", type_="unique")
        batch_op.drop_column("idempotency_key")
