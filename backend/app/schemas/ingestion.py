from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.models.entities import (
    BoundingBox,
    ConfidenceValue,
    IngestionStatus,
    InputKind,
    WardrobeCategory,
)


class IngestionUploadResponseData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: str
    status: str


class MediaAssetResponseData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    sha256: str


class DetectionReviewItem(BaseModel):
    detection_id: str
    crop_url: str
    bounding_box: BoundingBox
    attributes: dict[str, Any]
    field_confidence: dict[str, ConfidenceValue]


class IngestionBatchReviewResponseData(BaseModel):
    batch_id: str
    input_kind: str
    status: str
    detections: list[DetectionReviewItem] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    original_media_url: str | None = None


class CustomAttributesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: WardrobeCategory | None = None
    sub_category: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    pattern: str | None = None
    material: str | None = None
    style: str | None = None
    fit: str | None = None
    formality_level: int | None = Field(default=None, ge=1, le=5)
    comfort_level: int | None = Field(default=None, ge=1, le=5)
    silhouette_level: int | None = Field(default=None, ge=1, le=5)
    length: str | None = None
    season: list[str] | None = None
    weather_suitability: list[str] | None = None
    functional_flags: list[str] | None = None
    free_text_tags: list[str] | None = None

    @field_validator("length")
    @classmethod
    def validate_length_taxonomy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        norm = value.strip().lower()
        from app.models.entities import VALID_LENGTH_VALUES
        if norm not in VALID_LENGTH_VALUES:
            allowed = ", ".join(sorted(VALID_LENGTH_VALUES))
            raise ValueError(f"Độ dài (length) phải thuộc một trong các giá trị: {allowed}.")
        return norm

    @field_validator("functional_flags")
    @classmethod
    def validate_functional_flags(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return [v.strip().lower() for v in values if v.strip()]


class DetectionConfirmationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detection_id: str
    accepted: bool = True
    custom_attributes: CustomAttributesUpdate | None = None


class IngestionConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_token: str | None = Field(default=None, min_length=1, max_length=64)
    confirmations: list[DetectionConfirmationItem] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_confirmations(self) -> IngestionConfirmRequest:
        detection_ids = [c.detection_id for c in self.confirmations]
        if len(detection_ids) != len(set(detection_ids)):
            raise ValueError("Duplicate detection_id found in confirmations.")

        has_accepted = any(c.accepted for c in self.confirmations)
        if not has_accepted:
            raise ValueError("At least one detection must be accepted in confirmation.")

        return self


class IngestionConfirmResponseData(BaseModel):
    batch_id: str
    status: str
    wardrobe_item_ids: list[str] = Field(default_factory=list)


class IngestionDeleteResponseData(BaseModel):
    batch_id: str
    status: str
