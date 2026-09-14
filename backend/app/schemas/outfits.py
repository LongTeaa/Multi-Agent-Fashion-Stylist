from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.entities import OutfitSlotRole, RatingSource, WardrobeCategory


def _validate_uuid_v4(val: str, field_name: str) -> str:
    trimmed = val.strip()
    try:
        parsed = uuid.UUID(trimmed)
        if parsed.version != 4:
            raise ValueError(f"{field_name} must be a valid UUID v4.")
    except Exception:
        raise ValueError(f"{field_name} must be a valid UUID v4.")
    return str(parsed)


class OutfitItemDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot_role: OutfitSlotRole
    wardrobe_item_id: str = Field(min_length=36, max_length=36)
    name: str = Field(min_length=1, max_length=150)
    category: WardrobeCategory
    sub_category: str = Field(min_length=1, max_length=100)
    primary_color: str = Field(min_length=1, max_length=50)
    secondary_color: str | None = Field(default=None, max_length=50)
    pattern: str = Field(min_length=1, max_length=100)
    material: str = Field(min_length=1, max_length=100)
    style: str = Field(min_length=1, max_length=100)
    image_url: str | None = None
    is_active: bool = True


class OutfitDetailResponseData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(min_length=36, max_length=36)
    request_id: str = Field(min_length=36, max_length=36)
    user_query: str
    explanation_vi: str
    fashion_score: float = Field(ge=0.0, le=1.0)
    personalization_score: float = Field(ge=0.0, le=1.0)
    composite_score: float = Field(ge=0.0, le=1.0)
    rank: int = Field(ge=1, le=3)
    is_bookmarked: bool = False
    times_worn: int = Field(default=0, ge=0)
    last_worn_at: datetime | None = None
    user_rating: int | None = Field(default=None, ge=1, le=5)
    items: list[OutfitItemDetailResponse] = Field(default_factory=list)
    created_at: datetime


class SavedOutfitsResponseData(BaseModel):
    items: list[OutfitDetailResponseData] = Field(default_factory=list)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=50)
    total: int = Field(ge=0)


class BookmarkOutfitRequest(BaseModel):
    is_bookmarked: bool = Field(..., strict=True)


class BookmarkOutfitResponseData(BaseModel):
    outfit_id: str = Field(min_length=36, max_length=36)
    is_bookmarked: bool
    updated_at: datetime


class WornOutfitRequest(BaseModel):
    idempotency_key: str = Field(
        ...,
        description="UUID v4 idempotency key for preventing duplicate wear logs on retry",
    )
    worn_at: datetime | None = Field(
        default=None,
        description="Optional timezone-aware UTC datetime. Defaults to current server time if omitted.",
    )

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, v: str) -> str:
        return _validate_uuid_v4(v, "idempotency_key")

    @field_validator("worn_at")
    @classmethod
    def validate_worn_at(cls, v: datetime | None) -> datetime | None:
        if v is None:
            return None
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("worn_at must be a timezone-aware UTC datetime.")
        if v > datetime.now(timezone.utc):
            raise ValueError("worn_at cannot be in the future.")
        return v


class WornOutfitResponseData(BaseModel):
    wear_log_id: str = Field(min_length=36, max_length=36)
    outfit_id: str = Field(min_length=36, max_length=36)
    worn_at: datetime
    times_worn: int = Field(ge=1)
    already_processed: bool = False


class OutfitRatingRequest(BaseModel):
    stars: int = Field(
        ...,
        ge=1,
        le=5,
        strict=True,
        description="Integer rating from 1 to 5. Strict integer only (no boolean/float).",
    )
    source: RatingSource = Field(default=RatingSource.PROMPTED)
    client_session_id: str | None = Field(
        default=None,
        max_length=64,
        description="Opaque client session UUID v4. Required when source='prompted'.",
    )

    @field_validator("client_session_id")
    @classmethod
    def validate_client_session_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        return _validate_uuid_v4(trimmed, "client_session_id")

    @model_validator(mode="after")
    def validate_prompted_requires_session(self) -> OutfitRatingRequest:
        if self.source == RatingSource.PROMPTED and not self.client_session_id:
            raise ValueError("client_session_id is required when source is 'prompted'.")
        return self


class OutfitRatingResponseData(BaseModel):
    rating_id: str = Field(min_length=36, max_length=36)
    outfit_id: str = Field(min_length=36, max_length=36)
    stars: int = Field(ge=1, le=5)
    source: RatingSource
    ratings_count: int = Field(
        ge=0,
        description="Total number of distinct outfits rated by this user. Updating an existing rating does not increment this count.",
    )
    created_at: datetime
    updated_at: datetime
