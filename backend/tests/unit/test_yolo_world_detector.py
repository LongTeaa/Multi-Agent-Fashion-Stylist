"""Unit tests for YoloWorldDetector, letterbox preprocessing, NMS, and provider integration."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image
from pydantic import SecretStr

from app.core.config import Settings
from app.core.dependencies import get_detector, get_yolo_world_detector
from app.models.entities import InputKind
from app.services.classifier import classify_scene
from app.services.gemini_provider import GeminiDetector
from app.services.providers import DetectionResult, DetectorProtocol
from app.services.yolo_world_detector import (
    DEFAULT_FASHION_CLASSES,
    YoloWorldDetector,
    _nms,
)


def _create_test_image_bytes(
    width: int = 800,
    height: int = 600,
    color: tuple[int, int, int] = (200, 100, 50),
) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestYoloWorldDetectorPreprocessing:
    """Tests for image loading, orientation, letterbox resizing, and normalization."""

    def test_protocol_conformance(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]

        detector = YoloWorldDetector(session=mock_sess)
        assert isinstance(detector, DetectorProtocol)

    def test_letterbox_landscape_aspect_ratio(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]
        detector = YoloWorldDetector(session=mock_sess)

        # 800x400 image (w > h)
        image_bytes = _create_test_image_bytes(width=800, height=400)
        tensor, scale, pad_x, pad_y, orig_w, orig_h = detector._preprocess(image_bytes, target_size=(640, 640))

        assert tensor.shape == (1, 3, 640, 640)
        assert tensor.dtype == np.float32
        assert float(np.min(tensor)) >= 0.0
        assert float(np.max(tensor)) <= 1.0
        assert orig_w == 800
        assert orig_h == 400
        # Scale is 640 / 800 = 0.8
        assert pytest.approx(scale, 0.001) == 0.8
        # Scaled height: 400 * 0.8 = 320 -> pad_y = (640 - 320) / 2 = 160
        assert pytest.approx(pad_x, 0.001) == 0.0
        assert pytest.approx(pad_y, 0.001) == 160.0

    def test_letterbox_portrait_aspect_ratio(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]
        detector = YoloWorldDetector(session=mock_sess)

        # 400x800 image (h > w)
        image_bytes = _create_test_image_bytes(width=400, height=800)
        tensor, scale, pad_x, pad_y, orig_w, orig_h = detector._preprocess(image_bytes, target_size=(640, 640))

        assert tensor.shape == (1, 3, 640, 640)
        assert orig_w == 400
        assert orig_h == 800
        # Scale is 640 / 800 = 0.8
        assert pytest.approx(scale, 0.001) == 0.8
        # Scaled width: 400 * 0.8 = 320 -> pad_x = (640 - 320) / 2 = 160
        assert pytest.approx(pad_x, 0.001) == 160.0
        assert pytest.approx(pad_y, 0.001) == 0.0

    def test_preprocess_invalid_bytes_raises_value_error(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]
        detector = YoloWorldDetector(session=mock_sess)

        with pytest.raises(ValueError, match="Failed to decode image bytes"):
            detector._preprocess(b"corrupted_invalid_data")


class TestYoloWorldNmsAndRawCoordinates:
    """Tests for NMS suppression and unexpanded detector rectangles."""

    def test_nms_suppresses_high_iou_duplicates(self) -> None:
        # Two boxes heavily overlapping (IoU > 0.8)
        boxes = np.array([
            [100.0, 100.0, 200.0, 200.0],
            [105.0, 105.0, 202.0, 202.0],
        ], dtype=np.float32)
        scores = np.array([0.95, 0.80], dtype=np.float32)

        keep = _nms(boxes, scores, iou_threshold=0.45)
        assert keep == [0]

    def test_nms_retains_disjoint_boxes(self) -> None:
        # Two distinct boxes
        boxes = np.array([
            [50.0, 50.0, 100.0, 100.0],
            [300.0, 300.0, 400.0, 400.0],
        ], dtype=np.float32)
        scores = np.array([0.90, 0.85], dtype=np.float32)

        keep = _nms(boxes, scores, iou_threshold=0.45)
        assert sorted(keep) == [0, 1]

    def test_nms_empty_input(self) -> None:
        keep = _nms(np.empty((0, 4), dtype=np.float32), np.empty((0,), dtype=np.float32), 0.45)
        assert keep == []

    def test_raw_bbox_and_canonical_clamping(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]
        detector = YoloWorldDetector(session=mock_sess)

        raw = np.zeros((1, 22, 1), dtype=np.float32)
        raw[0, 0, 0] = 55.0   # cx
        raw[0, 1, 0] = 55.0   # cy
        raw[0, 2, 0] = 90.0   # w
        raw[0, 3, 0] = 90.0   # h
        raw[0, 4, 0] = 0.95   # class 0 (person)

        boxes = detector._postprocess(
            raw_outputs=[raw],
            scale=0.64,
            pad_x=0.0,
            pad_y=0.0,
            orig_w=1000,
            orig_h=1000,
        )

        assert len(boxes) == 1
        b = boxes[0]
        for coord in b.box:
            assert 0.0 <= coord <= 1.0
        assert b.box[0] <= b.box[2]
        assert b.box[1] <= b.box[3]
        assert b.box == pytest.approx((0.0156, 0.0156, 0.1562, 0.1562))

    @pytest.mark.parametrize(
        ("source_size", "raw_box", "scale", "pad_x", "pad_y"),
        [
            ((400, 800), (240, 160, 400, 320), 0.8, 160.0, 0.0),
            ((800, 400), (160, 240, 320, 400), 0.8, 0.0, 160.0),
        ],
    )
    def test_raw_source_rectangle_survives_letterbox_mapping(
        self,
        source_size: tuple[int, int],
        raw_box: tuple[int, int, int, int],
        scale: float,
        pad_x: float,
        pad_y: float,
    ) -> None:
        session = MagicMock()
        session.get_inputs.return_value = [MagicMock(name="images")]
        detector = YoloWorldDetector(session=session)
        raw = np.array([[*raw_box, 0.95, 3]], dtype=np.float32)

        boxes = detector._postprocess(
            [raw], scale, pad_x, pad_y, source_size[0], source_size[1]
        )

        assert len(boxes) == 1
        expected = (0.25, 0.25, 0.75, 0.5) if source_size[0] == 400 else (0.25, 0.25, 0.5, 0.75)
        assert boxes[0].box == pytest.approx(expected)

    @pytest.mark.parametrize("class_pair", [(5, 3), (3, 4), (7, 4), (1, 5)])
    def test_nms_preserves_distinct_overlapping_layers(
        self, class_pair: tuple[int, int]
    ) -> None:
        session = MagicMock()
        session.get_inputs.return_value = [MagicMock(name="images")]
        detector = YoloWorldDetector(session=session)
        raw = np.array([
            [150, 120, 450, 420, 0.95, class_pair[0]],
            [160, 130, 440, 410, 0.90, class_pair[1]],
        ], dtype=np.float32)

        boxes = detector._postprocess([raw], 1.0, 0.0, 0.0, 640, 640)

        assert {b.label for b in boxes} == {DEFAULT_FASHION_CLASSES[i] for i in class_pair}
        assert len(boxes) == 2

    def test_disjoint_alias_boxes_remain_separate_items(self) -> None:
        session = MagicMock()
        session.get_inputs.return_value = [MagicMock(name="images")]
        detector = YoloWorldDetector(session=session)
        raw = np.array([
            [50, 50, 150, 250, 0.95, 8],
            [350, 50, 450, 250, 0.90, 9],
        ], dtype=np.float32)

        boxes = detector._postprocess([raw], 1.0, 0.0, 0.0, 640, 640)

        assert [b.label for b in boxes] == ["pants", "trousers"]

    def test_outside_source_boxes_are_clipped_without_expansion(self) -> None:
        session = MagicMock()
        session.get_inputs.return_value = [MagicMock(name="images")]
        detector = YoloWorldDetector(session=session)
        raw = np.array([[-10, -20, 650, 660, 0.95, 3]], dtype=np.float32)

        boxes = detector._postprocess([raw], 1.0, 0.0, 0.0, 640, 640)

        assert len(boxes) == 1
        assert boxes[0].box == (0.0, 0.0, 1.0, 1.0)


class TestYoloWorldEndToEndInference:
    """Tests end-to-end detect() pipeline with mock ONNX tensor outputs."""

    def test_detect_produces_garments_and_person(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]

        raw = np.zeros((1, 22, 8400), dtype=np.float32)
        # Person box
        raw[0, 0, 0] = 320.0
        raw[0, 1, 0] = 320.0
        raw[0, 2, 0] = 200.0
        raw[0, 3, 0] = 400.0
        raw[0, 4, 0] = 0.92  # person (class 0)
        # Top box
        raw[0, 0, 1] = 320.0
        raw[0, 1, 1] = 250.0
        raw[0, 2, 1] = 120.0
        raw[0, 3, 1] = 150.0
        raw[0, 4 + 2, 1] = 0.88  # top (class 2)

        mock_sess.run.return_value = [raw]
        detector = YoloWorldDetector(session=mock_sess)

        image_bytes = _create_test_image_bytes(800, 600)
        res = detector.detect(image_bytes)

        assert isinstance(res, DetectionResult)
        assert res.input_kind == InputKind.UNKNOWN
        assert len(res.boxes) == 2
        labels = [b.label for b in res.boxes]
        assert "person" in labels
        assert "top" in labels
        assert len(res.quality_warnings) == 0

    def test_detect_cross_class_garment_deduplication_suppresses_synonyms(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]

        raw = np.zeros((1, 22, 8400), dtype=np.float32)
        # Pants box (class 8)
        raw[0, 0, 0] = 320.0
        raw[0, 1, 0] = 450.0
        raw[0, 2, 0] = 160.0
        raw[0, 3, 0] = 250.0
        raw[0, 4 + 8, 0] = 0.90
        # Trousers box (class 9, heavily overlapping at the same spot)
        raw[0, 0, 1] = 322.0
        raw[0, 1, 1] = 452.0
        raw[0, 2, 1] = 158.0
        raw[0, 3, 1] = 248.0
        raw[0, 4 + 9, 1] = 0.85

        mock_sess.run.return_value = [raw]
        detector = YoloWorldDetector(session=mock_sess)

        image_bytes = _create_test_image_bytes(800, 600)
        res = detector.detect(image_bytes)

        # Cross-class NMS should suppress trousers (0.85) in favor of pants (0.90)
        assert len(res.boxes) == 1
        assert res.boxes[0].label == "pants"

    def test_detect_cross_class_footwear_synonyms_and_near_identical_contours(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]

        raw = np.zeros((1, 22, 8400), dtype=np.float32)
        # Shoes box (class 13)
        raw[0, 0, 0] = 320.0
        raw[0, 1, 0] = 320.0
        raw[0, 2, 0] = 300.0
        raw[0, 3, 0] = 200.0
        raw[0, 4 + 13, 0] = 0.72
        # Boots box (class 15, overlapping pair of shoes)
        raw[0, 0, 1] = 321.0
        raw[0, 1, 1] = 321.0
        raw[0, 2, 1] = 298.0
        raw[0, 3, 1] = 198.0
        raw[0, 4 + 15, 1] = 0.58

        mock_sess.run.return_value = [raw]
        detector = YoloWorldDetector(session=mock_sess)

        image_bytes = _create_test_image_bytes(800, 600)
        res = detector.detect(image_bytes)

        assert len(res.boxes) == 1
        assert res.boxes[0].label == "shoes"

    def test_detect_no_boxes_generates_quality_warning(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]

        raw = np.zeros((1, 22, 8400), dtype=np.float32)
        mock_sess.run.return_value = [raw]
        detector = YoloWorldDetector(session=mock_sess, confidence_threshold=0.5)

        image_bytes = _create_test_image_bytes(640, 640)
        res = detector.detect(image_bytes)

        assert len(res.boxes) == 0
        assert len(res.quality_warnings) == 1
        assert "No garments" in res.quality_warnings[0]


class TestYoloWorldPipelineAndClassifierIntegration:
    """Tests integration of YoloWorldDetector with classify_scene scene resolver."""

    def test_classify_scene_resolves_worn_outfit_from_yolo_world(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]

        raw = np.zeros((1, 22, 8400), dtype=np.float32)
        # Person covering center
        raw[0, 0, 0] = 320.0
        raw[0, 1, 0] = 320.0
        raw[0, 2, 0] = 250.0
        raw[0, 3, 0] = 500.0
        raw[0, 4, 0] = 0.95  # person
        # Top overlapping on wearer
        raw[0, 0, 1] = 320.0
        raw[0, 1, 1] = 260.0
        raw[0, 2, 1] = 180.0
        raw[0, 3, 1] = 200.0
        raw[0, 4 + 2, 1] = 0.90  # top

        mock_sess.run.return_value = [raw]
        detector = YoloWorldDetector(session=mock_sess)
        image_bytes = _create_test_image_bytes(640, 640)

        scene_result = classify_scene(detector=detector, image_bytes=image_bytes)
        assert scene_result.input_kind == InputKind.WORN_OUTFIT
        assert scene_result.person_box is not None
        assert len(scene_result.boxes) == 1
        assert scene_result.boxes[0].label == "top"

    def test_classify_scene_resolves_multi_item_when_no_person(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]

        raw = np.zeros((1, 22, 8400), dtype=np.float32)
        # Top
        raw[0, 0, 0] = 200.0
        raw[0, 1, 0] = 200.0
        raw[0, 2, 0] = 150.0
        raw[0, 3, 0] = 150.0
        raw[0, 4 + 2, 0] = 0.90  # top
        # Pants
        raw[0, 0, 1] = 450.0
        raw[0, 1, 1] = 450.0
        raw[0, 2, 1] = 150.0
        raw[0, 3, 1] = 200.0
        raw[0, 4 + 8, 1] = 0.90  # pants

        mock_sess.run.return_value = [raw]
        detector = YoloWorldDetector(session=mock_sess)
        image_bytes = _create_test_image_bytes(640, 640)

        scene_result = classify_scene(detector=detector, image_bytes=image_bytes)
        assert scene_result.input_kind == InputKind.MULTI_ITEM
        assert scene_result.person_box is None
        assert len(scene_result.boxes) == 2


class TestYoloWorldDependencyInjection:
    """Tests DI provider selection, caching, and fallback logic."""

    def test_get_detector_yolo_world_success(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]
        mock_detector = YoloWorldDetector(session=mock_sess)

        settings = Settings(detector_backend="yolo_world", yolo_world_model_path="models/test.onnx")
        with patch("app.core.dependencies.get_settings", return_value=settings), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("app.core.dependencies.get_yolo_world_detector", return_value=mock_detector):
            d = get_detector()
            assert d is mock_detector

    def test_get_detector_yolo_world_fallback_to_gemini(self) -> None:
        settings = Settings(
            detector_backend="yolo_world",
            yolo_world_model_path="models/missing.onnx",
            gemini_api_key=SecretStr("gemini-test-key"),
            detector_model="gemini-1.5-flash",
        )
        with patch("app.core.dependencies.get_settings", return_value=settings), \
             patch("pathlib.Path.is_file", return_value=False):
            d = get_detector()
            assert isinstance(d, GeminiDetector)

    def test_get_yolo_world_detector_singleton_cache(self) -> None:
        mock_sess = MagicMock()
        mock_input = MagicMock()
        mock_input.name = "images"
        mock_sess.get_inputs.return_value = [mock_input]

        with patch("onnxruntime.InferenceSession", return_value=mock_sess), \
             patch("pathlib.Path.is_file", return_value=True):
            settings = Settings(detector_backend="yolo_world", yolo_world_model_path="models/cached.onnx")
            d1 = get_yolo_world_detector(settings)
            d2 = get_yolo_world_detector(settings)
            assert d1 is d2
