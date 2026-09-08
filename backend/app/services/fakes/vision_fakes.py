from __future__ import annotations

from typing import Any

from app.models.entities import InputKind
from app.schemas.common import ProviderError
from app.services.providers import (
    BoundingBoxDetection,
    DetectionResult,
    VisionExtractionResult,
)


class FakeDetector:
    """Deterministic fake detector for offline development and unit/integration testing."""

    def __init__(self, mode: str = "single_item") -> None:
        self.mode = mode

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def detect(self, image_bytes: bytes) -> DetectionResult:
        if self.mode == "timeout":
            raise TimeoutError("AI detector request timed out.")

        if self.mode == "provider_error":
            raise ProviderError("Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau.")

        if self.mode == "single_item":
            return DetectionResult(
                input_kind=InputKind.SINGLE_ITEM,
                boxes=[
                    BoundingBoxDetection(
                        box=(0.1, 0.1, 0.9, 0.9),
                        label="top",
                        confidence=0.98,
                    )
                ],
                quality_warnings=[],
            )

        if self.mode == "multi_item":
            return DetectionResult(
                input_kind=InputKind.MULTI_ITEM,
                boxes=[
                    BoundingBoxDetection(
                        box=(0.05, 0.1, 0.48, 0.9),
                        label="top",
                        confidence=0.96,
                    ),
                    BoundingBoxDetection(
                        box=(0.50, 0.1, 0.95, 0.9),
                        label="bottom",
                        confidence=0.94,
                    ),
                ],
                quality_warnings=[],
            )

        if self.mode == "worn_outfit":
            return DetectionResult(
                input_kind=InputKind.WORN_OUTFIT,
                boxes=[
                    BoundingBoxDetection(
                        box=(0.15, 0.20, 0.55, 0.80),
                        label="top",
                        confidence=0.92,
                    ),
                    BoundingBoxDetection(
                        box=(0.52, 0.25, 0.95, 0.75),
                        label="bottom",
                        confidence=0.90,
                    ),
                ],
                quality_warnings=[],
            )

        if self.mode == "cluttered":
            return DetectionResult(
                input_kind=InputKind.CLUTTERED,
                boxes=[],
                quality_warnings=[
                    "Không thể tách rời từng món do ảnh quá nhiều chi tiết hoặc bị che khuất."
                ],
            )

        if self.mode == "low_quality":
            return DetectionResult(
                input_kind=InputKind.SINGLE_ITEM,
                boxes=[
                    BoundingBoxDetection(
                        box=(0.1, 0.1, 0.9, 0.9),
                        label="top",
                        confidence=0.65,
                    )
                ],
                quality_warnings=["Ảnh chụp thiếu sáng hoặc bị mờ."],
            )

        return DetectionResult(
            input_kind=InputKind.UNKNOWN,
            boxes=[],
            quality_warnings=["Không nhận diện được vật thể."],
        )


class FakeVisionProvider:
    """Deterministic fake vision provider returning canonical fashion attributes and confidences."""

    def __init__(self, scenario: str = "golden_polo") -> None:
        self.scenario = scenario

    def set_scenario(self, scenario: str) -> None:
        self.scenario = scenario

    def extract_attributes(self, crop_bytes: bytes) -> VisionExtractionResult:
        if self.scenario == "timeout":
            raise TimeoutError("AI vision provider timed out.")

        if self.scenario == "provider_error":
            raise ProviderError("Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau.")

        if self.scenario == "low_confidence":
            attributes = {
                "category": "top",
                "sub_category": "polo",
                "primary_color": "white",
                "secondary_color": None,
                "pattern": "solid",
                "material": "cotton",
                "style": "smart_casual",
                "fit": "regular",
                "formality_level": 3,
                "season": ["spring", "summer"],
                "weather_suitability": ["warm", "cool"],
                "functional_flags": [],
                "free_text_tags": ["white polo"],
            }
            confidences = {
                "category": 0.95,
                "sub_category": 0.90,
                "primary_color": 0.92,
                "pattern": 0.55,  # < 0.70 flag
                "material": 0.60,  # < 0.70 flag
                "style": 0.65,     # < 0.70 flag
                "fit": 0.80,
                "formality_level": 0.85,
                "season": 0.75,
                "weather_suitability": 0.75,
            }
            return VisionExtractionResult(
                attributes=attributes,
                field_confidence=confidences,
                quality_warnings=["Một số thuộc tính có độ tin cậy thấp."],
            )

        if self.scenario == "chinos":
            attributes = {
                "category": "bottom",
                "sub_category": "chinos",
                "primary_color": "navy",
                "secondary_color": None,
                "pattern": "solid",
                "material": "cotton",
                "style": "smart_casual",
                "fit": "slim",
                "formality_level": 3,
                "season": ["all_year"],
                "weather_suitability": ["warm", "cool"],
                "functional_flags": [],
                "free_text_tags": ["navy chinos"],
            }
            confidences = {
                "category": 0.99,
                "sub_category": 0.94,
                "primary_color": 0.98,
                "pattern": 0.95,
                "material": 0.88,
                "style": 0.92,
                "fit": 0.85,
                "formality_level": 0.90,
                "season": 0.90,
                "weather_suitability": 0.90,
            }
            return VisionExtractionResult(
                attributes=attributes,
                field_confidence=confidences,
                quality_warnings=[],
            )

        # Default "golden_polo"
        attributes = {
            "category": "top",
            "sub_category": "polo",
            "primary_color": "white",
            "secondary_color": None,
            "pattern": "solid",
            "material": "cotton",
            "style": "smart_casual",
            "fit": "regular",
            "formality_level": 3,
            "season": ["spring", "summer"],
            "weather_suitability": ["warm", "cool"],
            "functional_flags": [],
            "free_text_tags": ["white polo"],
        }
        confidences = {
            "category": 0.98,
            "sub_category": 0.95,
            "primary_color": 0.96,
            "pattern": 0.90,
            "material": 0.85,
            "style": 0.92,
            "fit": 0.88,
            "formality_level": 0.90,
            "season": 0.88,
            "weather_suitability": 0.88,
        }
        return VisionExtractionResult(
            attributes=attributes,
            field_confidence=confidences,
            quality_warnings=[],
        )
