from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.models.entities import BoundingBox, ConfidenceValue, InputKind


@dataclass(frozen=True)
class BoundingBoxDetection:
    """A detected item region with normalized coordinates [ymin, xmin, ymax, xmax] in [0.0, 1.0]."""

    box: BoundingBox
    label: str
    confidence: ConfidenceValue = 0.95


@dataclass(frozen=True)
class DetectionResult:
    """Result of object detection and input scene classification."""

    input_kind: InputKind
    boxes: list[BoundingBoxDetection] = field(default_factory=list)
    quality_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class VisionExtractionResult:
    """Structured fashion attributes and per-field confidence extracted from an item crop."""

    attributes: dict[str, Any]
    field_confidence: dict[str, ConfidenceValue]
    quality_warnings: list[str] = field(default_factory=list)


@runtime_checkable
class DetectorProtocol(Protocol):
    """Protocol for detecting garment regions and classifying input scene types."""

    def detect(self, image_bytes: bytes) -> DetectionResult: ...


@runtime_checkable
class VisionProviderProtocol(Protocol):
    """Protocol for extracting fashion attributes and confidence scores from an item crop."""

    def extract_attributes(self, crop_bytes: bytes) -> VisionExtractionResult: ...
