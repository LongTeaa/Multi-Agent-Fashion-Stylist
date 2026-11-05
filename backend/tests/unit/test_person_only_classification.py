"""Person rectangles remain spatial references rather than wardrobe candidates."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.models.entities import InputKind
from app.services.classifier import classify_scene
from app.services.providers import BoundingBoxDetection, DetectionResult


@pytest.mark.parametrize("label", ["person", "human", "model", "man", "woman", "boy", "girl", " PERSON "])
@pytest.mark.parametrize("kind", [InputKind.UNKNOWN, InputKind.WORN_OUTFIT, InputKind.SINGLE_ITEM])
def test_person_only_detection_requires_warned_manual_review(label: str, kind: InputKind) -> None:
    person_box = (0.2, 0.05, 0.8, 0.95)
    original_warnings = ["Ảnh có người."]
    detector = Mock()
    detector.detect.return_value = DetectionResult(
        input_kind=kind,
        boxes=[BoundingBoxDetection(box=person_box, label=label, confidence=0.99)],
        quality_warnings=original_warnings,
    )

    result = classify_scene(detector, b"person-only")

    assert result.boxes == []
    assert result.person_box == person_box
    assert result.quality_warnings[0] == "Ảnh có người."
    assert any("tách riêng trang phục" in warning for warning in result.quality_warnings)
    assert original_warnings == ["Ảnh có người."]


def test_person_reference_without_garment_boxes_is_also_warned() -> None:
    person_box = (0.2, 0.05, 0.8, 0.95)
    detector = Mock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.WORN_OUTFIT,
        person_box=person_box,
    )

    result = classify_scene(detector, b"person-reference-only")

    assert result.person_box == person_box
    assert result.boxes == []
    assert any("tách riêng trang phục" in warning for warning in result.quality_warnings)


def test_person_reference_is_excluded_when_garment_is_detected() -> None:
    person_box = (0.2, 0.05, 0.8, 0.95)
    garment = BoundingBoxDetection(box=(0.3, 0.25, 0.7, 0.55), label="shirt", confidence=0.95)
    detector = Mock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.WORN_OUTFIT,
        boxes=[BoundingBoxDetection(box=person_box, label="person", confidence=0.99), garment],
    )

    result = classify_scene(detector, b"person-and-garment")

    assert result.person_box == person_box
    assert result.boxes == [garment]
    assert result.quality_warnings == []


def test_existing_separation_warning_is_not_duplicated() -> None:
    warning = "Không thể tách riêng trang phục trên người. Vui lòng chỉnh vùng cắt hoặc tải ảnh rõ hơn."
    detector = Mock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.WORN_OUTFIT,
        person_box=(0.2, 0.05, 0.8, 0.95),
        quality_warnings=[warning],
    )

    result = classify_scene(detector, b"already-warned")

    assert result.boxes == []
    assert result.quality_warnings == [warning]
