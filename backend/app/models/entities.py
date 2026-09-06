from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, TypeVar
from uuid import uuid4

from pydantic import Field as PydanticField
from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SqlEnum,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


def new_uuid() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


ConfidenceValue = Annotated[float, PydanticField(ge=0.0, le=1.0)]
EnumType = TypeVar("EnumType", bound=StrEnum)
BoundingBox = tuple[
    ConfidenceValue,
    ConfidenceValue,
    ConfidenceValue,
    ConfidenceValue,
]


def enum_column(enum_type: type[EnumType], name: str) -> Column[EnumType]:
    return Column(
        SqlEnum(
            enum_type,
            name=name,
            native_enum=False,
            create_constraint=True,
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
    )


class InputKind(StrEnum):
    UNKNOWN = "unknown"
    SINGLE_ITEM = "single_item"
    MULTI_ITEM = "multi_item"
    WORN_OUTFIT = "worn_outfit"
    CLUTTERED = "cluttered"


class IngestionStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    EXPIRED = "expired"


class DetectionStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MediaKind(StrEnum):
    ORIGINAL = "original"
    CROP = "crop"
    THUMBNAIL = "thumbnail"
    TRYON = "tryon"
    MOODBOARD = "moodboard"


class WardrobeCategory(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    DRESS = "dress"
    FOOTWEAR = "footwear"
    OUTERWEAR = "outerwear"
    ACCESSORY = "accessory"


class ItemMediaRole(StrEnum):
    PRIMARY = "primary"
    ALTERNATE = "alternate"
    THUMBNAIL = "thumbnail"


class OutfitSlotRole(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    DRESS = "dress"
    FOOTWEAR = "footwear"
    OUTERWEAR = "outerwear"
    ACCESSORY = "accessory"


class RatingSource(StrEnum):
    PROMPTED = "prompted"
    MANUAL = "manual"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    email: str | None = Field(default=None, max_length=320, unique=True)
    full_name: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class UserPreference(SQLModel, table=True):
    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("ratings_count >= 0", name="ck_user_preferences_ratings_count"),
    )

    user_id: str = Field(foreign_key="users.id", primary_key=True, max_length=36)
    styles: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    color_palettes: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    priorities: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    avoid_colors: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    avoid_styles: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    fit_preferences: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    learned_feature_weights: dict[str, object] = Field(
        default_factory=lambda: {"version": 1, "weights": {}},
        sa_column=Column(JSON, nullable=False),
    )
    ratings_count: int = Field(default=0, ge=0)
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class IngestionBatch(SQLModel, table=True):
    __tablename__ = "ingestion_batches"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_ingestion_batches_id_user"),)

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", index=True, max_length=36)
    input_kind: InputKind = Field(
        default=InputKind.UNKNOWN,
        sa_column=enum_column(InputKind, "input_kind"),
    )
    status: IngestionStatus = Field(
        default=IngestionStatus.UPLOADED,
        sa_column=enum_column(IngestionStatus, "ingestion_status"),
    )
    quality_warnings: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class MediaAsset(SQLModel, table=True):
    __tablename__ = "media_assets"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_media_assets_id_user"),
        UniqueConstraint("bucket", "object_key", name="uq_media_assets_bucket_key"),
        ForeignKeyConstraint(
            ["ingestion_batch_id", "user_id"],
            ["ingestion_batches.id", "ingestion_batches.user_id"],
            name="fk_media_assets_batch_owner",
        ),
        CheckConstraint("size_bytes > 0", name="ck_media_assets_size_bytes"),
        CheckConstraint("width > 0", name="ck_media_assets_width"),
        CheckConstraint("height > 0", name="ck_media_assets_height"),
        CheckConstraint("length(sha256) = 64", name="ck_media_assets_sha256_length"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", index=True, max_length=36)
    ingestion_batch_id: str | None = Field(default=None, max_length=36)
    kind: MediaKind = Field(sa_column=enum_column(MediaKind, "media_kind"))
    bucket: str = Field(max_length=63)
    object_key: str = Field(max_length=1024)
    mime_type: str = Field(max_length=100)
    size_bytes: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class IngestionDetection(SQLModel, table=True):
    __tablename__ = "ingestion_detections"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_ingestion_detections_id_user"),
        ForeignKeyConstraint(
            ["ingestion_batch_id", "user_id"],
            ["ingestion_batches.id", "ingestion_batches.user_id"],
            name="fk_ingestion_detections_batch_owner",
        ),
        ForeignKeyConstraint(
            ["crop_media_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            name="fk_ingestion_detections_crop_owner",
        ),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", index=True, max_length=36)
    ingestion_batch_id: str = Field(index=True, max_length=36)
    crop_media_asset_id: str | None = Field(default=None, max_length=36)
    bounding_box: BoundingBox = Field(sa_column=Column(JSON, nullable=False))
    proposed_attributes: dict[str, object] = Field(sa_column=Column(JSON, nullable=False))
    field_confidence: dict[str, ConfidenceValue] = Field(
        sa_column=Column(JSON, nullable=False),
    )
    status: DetectionStatus = Field(
        default=DetectionStatus.PROPOSED,
        sa_column=enum_column(DetectionStatus, "detection_status"),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class WardrobeItem(SQLModel, table=True):
    __tablename__ = "wardrobe_items"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_wardrobe_items_id_user"),
        UniqueConstraint(
            "ingestion_detection_id",
            name="uq_wardrobe_items_ingestion_detection",
        ),
        ForeignKeyConstraint(
            ["ingestion_batch_id", "user_id"],
            ["ingestion_batches.id", "ingestion_batches.user_id"],
            name="fk_wardrobe_items_batch_owner",
        ),
        ForeignKeyConstraint(
            ["ingestion_detection_id", "user_id"],
            ["ingestion_detections.id", "ingestion_detections.user_id"],
            name="fk_wardrobe_items_detection_owner",
        ),
        Index("ix_wardrobe_items_user_active_category", "user_id", "is_active", "category"),
        Index("ix_wardrobe_items_user_color_style", "user_id", "primary_color", "style"),
        CheckConstraint(
            "formality_level BETWEEN 1 AND 5",
            name="ck_wardrobe_items_formality_level",
        ),
        CheckConstraint("times_worn >= 0", name="ck_wardrobe_items_times_worn"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", max_length=36)
    ingestion_batch_id: str | None = Field(default=None, max_length=36)
    ingestion_detection_id: str | None = Field(default=None, max_length=36)
    category: WardrobeCategory = Field(
        sa_column=enum_column(WardrobeCategory, "wardrobe_category"),
    )
    sub_category: str = Field(max_length=100)
    primary_color: str = Field(max_length=50)
    secondary_color: str | None = Field(default=None, max_length=50)
    pattern: str = Field(max_length=100)
    material: str = Field(max_length=100)
    style: str = Field(max_length=100)
    fit: str = Field(max_length=100)
    formality_level: int = Field(ge=1, le=5)
    season: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    weather_suitability: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    functional_flags: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    free_text_tags: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    field_confidence: dict[str, ConfidenceValue] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    is_active: bool = Field(default=True)
    is_user_confirmed: bool = Field(default=False)
    times_worn: int = Field(default=0, ge=0)
    last_worn_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    deleted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class ItemMedia(SQLModel, table=True):
    __tablename__ = "item_media"
    __table_args__ = (
        ForeignKeyConstraint(
            ["wardrobe_item_id", "user_id"],
            ["wardrobe_items.id", "wardrobe_items.user_id"],
            name="fk_item_media_item_owner",
        ),
        ForeignKeyConstraint(
            ["media_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            name="fk_item_media_asset_owner",
        ),
    )

    wardrobe_item_id: str = Field(primary_key=True, max_length=36)
    media_asset_id: str = Field(primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", index=True, max_length=36)
    role: ItemMediaRole = Field(
        sa_column=enum_column(ItemMediaRole, "item_media_role"),
    )


class OutfitRecommendation(SQLModel, table=True):
    __tablename__ = "outfit_recommendations"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_outfit_recommendations_id_user"),
        Index("ix_outfit_recommendations_user_created", "user_id", "created_at"),
        CheckConstraint(
            "fashion_score BETWEEN 0.0 AND 1.0",
            name="ck_outfit_recommendations_fashion_score",
        ),
        CheckConstraint(
            "personalization_score BETWEEN 0.0 AND 1.0",
            name="ck_outfit_recommendations_personalization_score",
        ),
        CheckConstraint(
            "composite_score BETWEEN 0.0 AND 1.0",
            name="ck_outfit_recommendations_composite_score",
        ),
        CheckConstraint("rank BETWEEN 1 AND 3", name="ck_outfit_recommendations_rank"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", max_length=36)
    request_id: str = Field(index=True, max_length=36)
    user_query: str = Field(sa_column=Column(Text, nullable=False))
    context_snapshot: dict[str, object] = Field(sa_column=Column(JSON, nullable=False))
    explanation_vi: str = Field(sa_column=Column(Text, nullable=False))
    fashion_score: float = Field(ge=0.0, le=1.0)
    personalization_score: float = Field(ge=0.0, le=1.0)
    composite_score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1, le=3)
    is_bookmarked: bool = Field(default=False)
    rule_version: str = Field(max_length=50)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class OutfitItem(SQLModel, table=True):
    __tablename__ = "outfit_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outfit_id", "user_id"],
            ["outfit_recommendations.id", "outfit_recommendations.user_id"],
            name="fk_outfit_items_outfit_owner",
        ),
        ForeignKeyConstraint(
            ["wardrobe_item_id", "user_id"],
            ["wardrobe_items.id", "wardrobe_items.user_id"],
            name="fk_outfit_items_item_owner",
        ),
    )

    outfit_id: str = Field(primary_key=True, max_length=36)
    wardrobe_item_id: str = Field(primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", index=True, max_length=36)
    slot_role: OutfitSlotRole = Field(
        sa_column=enum_column(OutfitSlotRole, "outfit_slot_role"),
    )


class Rating(SQLModel, table=True):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "outfit_id", name="uq_ratings_user_outfit"),
        ForeignKeyConstraint(
            ["outfit_id", "user_id"],
            ["outfit_recommendations.id", "outfit_recommendations.user_id"],
            name="fk_ratings_outfit_owner",
        ),
        Index("ix_ratings_user_created", "user_id", "created_at"),
        CheckConstraint("stars BETWEEN 1 AND 5", name="ck_ratings_stars"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", max_length=36)
    outfit_id: str = Field(max_length=36)
    stars: int = Field(ge=1, le=5)
    source: RatingSource = Field(
        sa_column=enum_column(RatingSource, "rating_source"),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class FeedbackPromptState(SQLModel, table=True):
    __tablename__ = "feedback_prompt_state"
    __table_args__ = (
        CheckConstraint(
            "eligible_count_since_prompt >= 0",
            name="ck_feedback_prompt_state_eligible_count",
        ),
        CheckConstraint(
            "next_threshold BETWEEN 5 AND 10",
            name="ck_feedback_prompt_state_next_threshold",
        ),
        CheckConstraint(
            "cooldown_remaining >= 0",
            name="ck_feedback_prompt_state_cooldown",
        ),
    )

    user_id: str = Field(foreign_key="users.id", primary_key=True, max_length=36)
    eligible_count_since_prompt: int = Field(default=0, ge=0)
    next_threshold: int = Field(ge=5, le=10)
    cooldown_remaining: int = Field(default=0, ge=0)
    last_prompted_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_rated_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class WearLog(SQLModel, table=True):
    __tablename__ = "wear_logs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outfit_id", "user_id"],
            ["outfit_recommendations.id", "outfit_recommendations.user_id"],
            name="fk_wear_logs_outfit_owner",
        ),
        Index("ix_wear_logs_user_worn", "user_id", "worn_at"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", max_length=36)
    outfit_id: str = Field(max_length=36)
    worn_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class TryOnRender(SQLModel, table=True):
    __tablename__ = "tryon_renders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["outfit_id", "user_id"],
            ["outfit_recommendations.id", "outfit_recommendations.user_id"],
            name="fk_tryon_renders_outfit_owner",
        ),
        ForeignKeyConstraint(
            ["media_asset_id", "user_id"],
            ["media_assets.id", "media_assets.user_id"],
            name="fk_tryon_renders_media_owner",
        ),
        CheckConstraint("duration_ms >= 0", name="ck_tryon_renders_duration_ms"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=36)
    user_id: str = Field(foreign_key="users.id", index=True, max_length=36)
    outfit_id: str = Field(max_length=36)
    media_asset_id: str = Field(max_length=36)
    provider: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    fallback_used: bool = Field(default=False)
    duration_ms: int = Field(ge=0)
    status: str = Field(max_length=50)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
