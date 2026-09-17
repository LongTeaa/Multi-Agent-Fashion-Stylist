from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol, runtime_checkable

from app.models.entities import BoundingBox, ConfidenceValue, InputKind


@dataclass(frozen=True)
class BoundingBoxDetection:
    """A detected item region with normalized coordinates [x_min, y_min, x_max, y_max] in [0.0, 1.0]."""

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


@dataclass(frozen=True)
class ImageReference:
    """Private item-crop bytes supplied to an image provider for one request."""

    asset_id: str
    image_bytes: bytes
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]


@dataclass(frozen=True)
class ImageGenerationRequest:
    """Provider-neutral request for an illustrative lookbook image."""

    prompt: str
    reference_images: tuple[ImageReference, ...] = ()


@dataclass(frozen=True)
class ImageGenerationResult:
    """Normalized generated image and benchmark identifiers."""

    image_bytes: bytes
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    provider: str
    model: str


@runtime_checkable
class ImageProviderProtocol(Protocol):
    """Protocol for optional external illustrative-lookbook generation."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model(self) -> str: ...

    @property
    def supports_reference_images(self) -> bool: ...

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult: ...


@dataclass(frozen=True)
class WeatherContextResult:
    """Normalized weather enrichment returned by a weather provider."""

    condition: Literal["hot", "warm", "cool", "cold", "rainy"]
    temperature_celsius: float | None = None


@runtime_checkable
class ContextLLMProviderProtocol(Protocol):
    """Protocol for extracting a structured context payload from a Vietnamese query."""

    def extract_context(
        self,
        *,
        query: str,
        location: str | None,
        current_date: date,
    ) -> dict[str, Any]: ...


@runtime_checkable
class WeatherProviderProtocol(Protocol):
    """Protocol for enriching context with normalized weather data."""

    def get_weather(
        self,
        *,
        location: str,
        event_date: date,
    ) -> WeatherContextResult: ...
