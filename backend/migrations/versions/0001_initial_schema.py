"""initial schema

Revision ID: 0001
Revises: None
Create Date: 2026-09-06 16:09:41.003915
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('users',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=320), nullable=True),
    sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('feedback_prompt_state',
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('eligible_count_since_prompt', sa.Integer(), nullable=False),
    sa.Column('next_threshold', sa.Integer(), nullable=False),
    sa.Column('cooldown_remaining', sa.Integer(), nullable=False),
    sa.Column('last_prompted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_rated_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('cooldown_remaining >= 0', name='ck_feedback_prompt_state_cooldown'),
    sa.CheckConstraint('eligible_count_since_prompt >= 0', name='ck_feedback_prompt_state_eligible_count'),
    sa.CheckConstraint('next_threshold BETWEEN 5 AND 10', name='ck_feedback_prompt_state_next_threshold'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('ingestion_batches',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('input_kind', sa.Enum('unknown', 'single_item', 'multi_item', 'worn_outfit', 'cluttered', name='input_kind', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('status', sa.Enum('uploaded', 'processing', 'needs_review', 'confirmed', 'failed', 'expired', name='ingestion_status', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('quality_warnings', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'user_id', name='uq_ingestion_batches_id_user')
    )
    with op.batch_alter_table('ingestion_batches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ingestion_batches_user_id'), ['user_id'], unique=False)

    op.create_table('outfit_recommendations',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('request_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_query', sa.Text(), nullable=False),
    sa.Column('context_snapshot', sa.JSON(), nullable=False),
    sa.Column('explanation_vi', sa.Text(), nullable=False),
    sa.Column('fashion_score', sa.Float(), nullable=False),
    sa.Column('personalization_score', sa.Float(), nullable=False),
    sa.Column('composite_score', sa.Float(), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('is_bookmarked', sa.Boolean(), nullable=False),
    sa.Column('rule_version', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('composite_score BETWEEN 0.0 AND 1.0', name='ck_outfit_recommendations_composite_score'),
    sa.CheckConstraint('fashion_score BETWEEN 0.0 AND 1.0', name='ck_outfit_recommendations_fashion_score'),
    sa.CheckConstraint('personalization_score BETWEEN 0.0 AND 1.0', name='ck_outfit_recommendations_personalization_score'),
    sa.CheckConstraint('rank BETWEEN 1 AND 3', name='ck_outfit_recommendations_rank'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'user_id', name='uq_outfit_recommendations_id_user')
    )
    with op.batch_alter_table('outfit_recommendations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_outfit_recommendations_request_id'), ['request_id'], unique=False)
        batch_op.create_index('ix_outfit_recommendations_user_created', ['user_id', 'created_at'], unique=False)

    op.create_table('user_preferences',
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('styles', sa.JSON(), nullable=False),
    sa.Column('color_palettes', sa.JSON(), nullable=False),
    sa.Column('priorities', sa.JSON(), nullable=False),
    sa.Column('avoid_colors', sa.JSON(), nullable=False),
    sa.Column('avoid_styles', sa.JSON(), nullable=False),
    sa.Column('fit_preferences', sa.JSON(), nullable=False),
    sa.Column('learned_feature_weights', sa.JSON(), nullable=False),
    sa.Column('ratings_count', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('ratings_count >= 0', name='ck_user_preferences_ratings_count'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('media_assets',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('ingestion_batch_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=True),
    sa.Column('kind', sa.Enum('original', 'crop', 'thumbnail', 'tryon', 'moodboard', name='media_kind', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('bucket', sqlmodel.sql.sqltypes.AutoString(length=63), nullable=False),
    sa.Column('object_key', sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=False),
    sa.Column('mime_type', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('sha256', sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('height > 0', name='ck_media_assets_height'),
    sa.CheckConstraint('length(sha256) = 64', name='ck_media_assets_sha256_length'),
    sa.CheckConstraint('size_bytes > 0', name='ck_media_assets_size_bytes'),
    sa.CheckConstraint('width > 0', name='ck_media_assets_width'),
    sa.ForeignKeyConstraint(['ingestion_batch_id', 'user_id'], ['ingestion_batches.id', 'ingestion_batches.user_id'], name='fk_media_assets_batch_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bucket', 'object_key', name='uq_media_assets_bucket_key'),
    sa.UniqueConstraint('id', 'user_id', name='uq_media_assets_id_user')
    )
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_assets_user_id'), ['user_id'], unique=False)

    op.create_table('ratings',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('outfit_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('stars', sa.Integer(), nullable=False),
    sa.Column('source', sa.Enum('prompted', 'manual', name='rating_source', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('stars BETWEEN 1 AND 5', name='ck_ratings_stars'),
    sa.ForeignKeyConstraint(['outfit_id', 'user_id'], ['outfit_recommendations.id', 'outfit_recommendations.user_id'], name='fk_ratings_outfit_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'outfit_id', name='uq_ratings_user_outfit')
    )
    with op.batch_alter_table('ratings', schema=None) as batch_op:
        batch_op.create_index('ix_ratings_user_created', ['user_id', 'created_at'], unique=False)

    op.create_table('wear_logs',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('outfit_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('worn_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['outfit_id', 'user_id'], ['outfit_recommendations.id', 'outfit_recommendations.user_id'], name='fk_wear_logs_outfit_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('wear_logs', schema=None) as batch_op:
        batch_op.create_index('ix_wear_logs_user_worn', ['user_id', 'worn_at'], unique=False)

    op.create_table('ingestion_detections',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('ingestion_batch_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('crop_media_asset_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=True),
    sa.Column('bounding_box', sa.JSON(), nullable=False),
    sa.Column('proposed_attributes', sa.JSON(), nullable=False),
    sa.Column('field_confidence', sa.JSON(), nullable=False),
    sa.Column('status', sa.Enum('proposed', 'accepted', 'rejected', name='detection_status', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['crop_media_asset_id', 'user_id'], ['media_assets.id', 'media_assets.user_id'], name='fk_ingestion_detections_crop_owner'),
    sa.ForeignKeyConstraint(['ingestion_batch_id', 'user_id'], ['ingestion_batches.id', 'ingestion_batches.user_id'], name='fk_ingestion_detections_batch_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'user_id', name='uq_ingestion_detections_id_user')
    )
    with op.batch_alter_table('ingestion_detections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ingestion_detections_ingestion_batch_id'), ['ingestion_batch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_ingestion_detections_user_id'), ['user_id'], unique=False)

    op.create_table('tryon_renders',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('outfit_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('media_asset_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
    sa.Column('model', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True),
    sa.Column('fallback_used', sa.Boolean(), nullable=False),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('duration_ms >= 0', name='ck_tryon_renders_duration_ms'),
    sa.ForeignKeyConstraint(['media_asset_id', 'user_id'], ['media_assets.id', 'media_assets.user_id'], name='fk_tryon_renders_media_owner'),
    sa.ForeignKeyConstraint(['outfit_id', 'user_id'], ['outfit_recommendations.id', 'outfit_recommendations.user_id'], name='fk_tryon_renders_outfit_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('tryon_renders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tryon_renders_user_id'), ['user_id'], unique=False)

    op.create_table('wardrobe_items',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('ingestion_batch_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=True),
    sa.Column('ingestion_detection_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=True),
    sa.Column('category', sa.Enum('top', 'bottom', 'dress', 'footwear', 'outerwear', 'accessory', name='wardrobe_category', native_enum=False, create_constraint=True), nullable=False),
    sa.Column('sub_category', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('primary_color', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('secondary_color', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
    sa.Column('pattern', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('material', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('style', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('fit', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('formality_level', sa.Integer(), nullable=False),
    sa.Column('season', sa.JSON(), nullable=False),
    sa.Column('weather_suitability', sa.JSON(), nullable=False),
    sa.Column('functional_flags', sa.JSON(), nullable=False),
    sa.Column('free_text_tags', sa.JSON(), nullable=False),
    sa.Column('field_confidence', sa.JSON(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_user_confirmed', sa.Boolean(), nullable=False),
    sa.Column('times_worn', sa.Integer(), nullable=False),
    sa.Column('last_worn_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('formality_level BETWEEN 1 AND 5', name='ck_wardrobe_items_formality_level'),
    sa.CheckConstraint('times_worn >= 0', name='ck_wardrobe_items_times_worn'),
    sa.ForeignKeyConstraint(['ingestion_batch_id', 'user_id'], ['ingestion_batches.id', 'ingestion_batches.user_id'], name='fk_wardrobe_items_batch_owner'),
    sa.ForeignKeyConstraint(['ingestion_detection_id', 'user_id'], ['ingestion_detections.id', 'ingestion_detections.user_id'], name='fk_wardrobe_items_detection_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'user_id', name='uq_wardrobe_items_id_user'),
    sa.UniqueConstraint('ingestion_detection_id', name='uq_wardrobe_items_ingestion_detection')
    )
    with op.batch_alter_table('wardrobe_items', schema=None) as batch_op:
        batch_op.create_index('ix_wardrobe_items_user_active_category', ['user_id', 'is_active', 'category'], unique=False)
        batch_op.create_index('ix_wardrobe_items_user_color_style', ['user_id', 'primary_color', 'style'], unique=False)

    op.create_table('item_media',
    sa.Column('wardrobe_item_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('media_asset_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('role', sa.Enum('primary', 'alternate', 'thumbnail', name='item_media_role', native_enum=False, create_constraint=True), nullable=False),
    sa.ForeignKeyConstraint(['media_asset_id', 'user_id'], ['media_assets.id', 'media_assets.user_id'], name='fk_item_media_asset_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['wardrobe_item_id', 'user_id'], ['wardrobe_items.id', 'wardrobe_items.user_id'], name='fk_item_media_item_owner'),
    sa.PrimaryKeyConstraint('wardrobe_item_id', 'media_asset_id')
    )
    with op.batch_alter_table('item_media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_item_media_user_id'), ['user_id'], unique=False)

    op.create_table('outfit_items',
    sa.Column('outfit_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('wardrobe_item_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(length=36), nullable=False),
    sa.Column('slot_role', sa.Enum('top', 'bottom', 'dress', 'footwear', 'outerwear', 'accessory', name='outfit_slot_role', native_enum=False, create_constraint=True), nullable=False),
    sa.ForeignKeyConstraint(['outfit_id', 'user_id'], ['outfit_recommendations.id', 'outfit_recommendations.user_id'], name='fk_outfit_items_outfit_owner'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['wardrobe_item_id', 'user_id'], ['wardrobe_items.id', 'wardrobe_items.user_id'], name='fk_outfit_items_item_owner'),
    sa.PrimaryKeyConstraint('outfit_id', 'wardrobe_item_id')
    )
    with op.batch_alter_table('outfit_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_outfit_items_user_id'), ['user_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('outfit_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_outfit_items_user_id'))

    op.drop_table('outfit_items')
    with op.batch_alter_table('item_media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_item_media_user_id'))

    op.drop_table('item_media')
    with op.batch_alter_table('wardrobe_items', schema=None) as batch_op:
        batch_op.drop_index('ix_wardrobe_items_user_color_style')
        batch_op.drop_index('ix_wardrobe_items_user_active_category')

    op.drop_table('wardrobe_items')
    with op.batch_alter_table('tryon_renders', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tryon_renders_user_id'))

    op.drop_table('tryon_renders')
    with op.batch_alter_table('ingestion_detections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ingestion_detections_user_id'))
        batch_op.drop_index(batch_op.f('ix_ingestion_detections_ingestion_batch_id'))

    op.drop_table('ingestion_detections')
    with op.batch_alter_table('wear_logs', schema=None) as batch_op:
        batch_op.drop_index('ix_wear_logs_user_worn')

    op.drop_table('wear_logs')
    with op.batch_alter_table('ratings', schema=None) as batch_op:
        batch_op.drop_index('ix_ratings_user_created')

    op.drop_table('ratings')
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_assets_user_id'))

    op.drop_table('media_assets')
    op.drop_table('user_preferences')
    with op.batch_alter_table('outfit_recommendations', schema=None) as batch_op:
        batch_op.drop_index('ix_outfit_recommendations_user_created')
        batch_op.drop_index(batch_op.f('ix_outfit_recommendations_request_id'))

    op.drop_table('outfit_recommendations')
    with op.batch_alter_table('ingestion_batches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ingestion_batches_user_id'))

    op.drop_table('ingestion_batches')
    op.drop_table('feedback_prompt_state')
    op.drop_table('users')
