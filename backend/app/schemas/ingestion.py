from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.models.entities import BoundingBox, ConfidenceValue, IngestionStatus, InputKind


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


class DetectionConfirmationItem(BaseModel):
    detection_id: str
    accepted: bool = True
    custom_attributes: dict[str, Any] | None = None


class IngestionConfirmRequest(BaseModel):
    idempotency_token: str | None = None
    confirmations: list[DetectionConfirmationItem] = Field(default_factory=list)


class IngestionConfirmResponseData(BaseModel):
    batch_id: str
    status: str
    wardrobe_item_ids: list[str] = Field(default_factory=list)


class IngestionDeleteResponseData(BaseModel):
    batch_id: str
    status: str
