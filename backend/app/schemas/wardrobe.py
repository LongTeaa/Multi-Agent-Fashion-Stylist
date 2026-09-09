from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.entities import ConfidenceValue, WardrobeCategory


class WardrobeItemAttributes(BaseModel):
    category: WardrobeCategory
    sub_category: str = Field(min_length=1, max_length=100)
    primary_color: str = Field(min_length=1, max_length=50)
    secondary_color: str | None = Field(default=None, max_length=50)
    pattern: str = Field(min_length=1, max_length=100)
    material: str = Field(min_length=1, max_length=100)
    style: str = Field(min_length=1, max_length=100)
    fit: str = Field(min_length=1, max_length=100)
    formality_level: int = Field(ge=1, le=5)
    season: list[str] = Field(default_factory=list, max_length=10)
    weather_suitability: list[str] = Field(default_factory=list, max_length=10)
    functional_flags: list[str] = Field(default_factory=list, max_length=20)
    free_text_tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator(
        "season", "weather_suitability", "functional_flags", "free_text_tags"
    )
    @classmethod
    def validate_bounded_strings(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 100 for value in normalized):
            raise ValueError("List values must contain 1 to 100 characters.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("List values must be unique.")
        return normalized


class WardrobeItemCreate(WardrobeItemAttributes):
    media_asset_id: str


class WardrobeItemUpdate(BaseModel):
    category: WardrobeCategory | None = None
    sub_category: str | None = Field(default=None, min_length=1, max_length=100)
    primary_color: str | None = Field(default=None, min_length=1, max_length=50)
    secondary_color: str | None = Field(default=None, max_length=50)
    pattern: str | None = Field(default=None, min_length=1, max_length=100)
    material: str | None = Field(default=None, min_length=1, max_length=100)
    style: str | None = Field(default=None, min_length=1, max_length=100)
    fit: str | None = Field(default=None, min_length=1, max_length=100)
    formality_level: int | None = Field(default=None, ge=1, le=5)
    season: list[str] | None = Field(default=None, max_length=10)
    weather_suitability: list[str] | None = Field(default=None, max_length=10)
    functional_flags: list[str] | None = Field(default=None, max_length=20)
    free_text_tags: list[str] | None = Field(default=None, max_length=20)

    @field_validator(
        "season", "weather_suitability", "functional_flags", "free_text_tags"
    )
    @classmethod
    def validate_bounded_strings(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return WardrobeItemAttributes.validate_bounded_strings(values)


class WardrobeItemResponseData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    category: WardrobeCategory
    sub_category: str
    primary_color: str
    secondary_color: str | None
    pattern: str
    material: str
    style: str
    fit: str
    formality_level: int
    season: list[str]
    weather_suitability: list[str]
    functional_flags: list[str]
    free_text_tags: list[str]
    field_confidence: dict[str, ConfidenceValue]
    is_active: bool
    is_user_confirmed: bool
    times_worn: int
    last_worn_at: datetime | None
    media_url: str | None
    created_at: datetime
    updated_at: datetime


class WardrobeItemListResponseData(BaseModel):
    items: list[WardrobeItemResponseData] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class WardrobeItemDeleteResponseData(BaseModel):
    item_id: str
    is_active: bool
