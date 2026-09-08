from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.dependencies import get_detector, get_vision_provider
from app.models.entities import InputKind
from app.schemas.common import ProviderError
from app.services.classifier import classify_scene
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider
from app.services.gemini_provider import GeminiDetector, GeminiVisionProvider
from app.services.providers import BoundingBoxDetection, DetectionResult


class TestProviderSelection:
    """Unit tests verifying provider selection and configuration guards."""

    def test_fake_mode_returns_fake_providers(self) -> None:
        fake_settings = Settings(
            vision_provider="fake",
        )
        with patch("app.core.dependencies.get_settings", return_value=fake_settings):
            detector = get_detector()
            vision = get_vision_provider()
            assert isinstance(detector, FakeDetector)
            assert isinstance(vision, FakeVisionProvider)

    def test_gemini_mode_returns_gemini_providers(self) -> None:
        gemini_settings = Settings(
            vision_provider="gemini",
            gemini_api_key=SecretStr("test-key-12345"),
            vision_model="gemini-1.5-flash",
            vision_timeout_seconds=15,
        )
        with patch("app.core.dependencies.get_settings", return_value=gemini_settings):
            detector = get_detector()
            vision = get_vision_provider()
            assert isinstance(detector, GeminiDetector)
            assert isinstance(vision, GeminiVisionProvider)
            assert detector.model == "gemini-1.5-flash"
            assert detector.timeout_seconds == 15.0
            assert vision.model == "gemini-1.5-flash"
            assert vision.timeout_seconds == 15.0

    def test_gemini_missing_api_key_raises_error(self) -> None:
        missing_key_settings = Settings(
            vision_provider="gemini",
            gemini_api_key=None,
            vision_model="gemini-1.5-flash",
        )
        with patch("app.core.dependencies.get_settings", return_value=missing_key_settings):
            with pytest.raises(ValueError) as exc_detector:
                get_detector()
            assert "GEMINI_API_KEY is not configured" in str(exc_detector.value)

            with pytest.raises(ValueError) as exc_vision:
                get_vision_provider()
            assert "GEMINI_API_KEY is not configured" in str(exc_vision.value)

    def test_gemini_missing_model_raises_error(self) -> None:
        missing_model_settings = Settings(
            vision_provider="gemini",
            gemini_api_key=SecretStr("test-key-12345"),
            vision_model=None,
        )
        with patch("app.core.dependencies.get_settings", return_value=missing_model_settings):
            with pytest.raises(ValueError) as exc_detector:
                get_detector()
            assert "VISION_MODEL is not configured" in str(exc_detector.value)

            with pytest.raises(ValueError) as exc_vision:
                get_vision_provider()
            assert "VISION_MODEL is not configured" in str(exc_vision.value)


class TestClassifySceneResolution:
    """Unit tests verifying classify_scene resolution heuristics."""

    def test_unknown_resolves_to_declared_kind(self) -> None:
        detector = FakeDetector(mode="unknown")
        result = classify_scene(
            detector=detector,
            image_bytes=b"dummy",
            declared_input_kind=InputKind.WORN_OUTFIT,
        )
        assert result.input_kind == InputKind.WORN_OUTFIT

    def test_unknown_with_zero_boxes_resolves_to_cluttered(self) -> None:
        detector = FakeDetector(mode="unknown")
        result = classify_scene(
            detector=detector,
            image_bytes=b"dummy",
            declared_input_kind=None,
        )
        assert result.input_kind == InputKind.CLUTTERED

    def test_unknown_with_one_box_resolves_to_single_item(self) -> None:
        class OneBoxUnknownDetector:
            def detect(self, image_bytes: bytes) -> DetectionResult:
                return DetectionResult(
                    input_kind=InputKind.UNKNOWN,
                    boxes=[
                        BoundingBoxDetection(box=(0.1, 0.1, 0.8, 0.8), label="top", confidence=0.9)
                    ],
                )

        result = classify_scene(
            detector=OneBoxUnknownDetector(),
            image_bytes=b"dummy",
            declared_input_kind=None,
        )
        assert result.input_kind == InputKind.SINGLE_ITEM
        assert len(result.boxes) == 1

    def test_unknown_with_multiple_boxes_resolves_to_multi_item(self) -> None:
        class MultiBoxUnknownDetector:
            def detect(self, image_bytes: bytes) -> DetectionResult:
                return DetectionResult(
                    input_kind=InputKind.UNKNOWN,
                    boxes=[
                        BoundingBoxDetection(box=(0.1, 0.1, 0.4, 0.8), label="top", confidence=0.9),
                        BoundingBoxDetection(box=(0.5, 0.1, 0.9, 0.8), label="bottom", confidence=0.9),
                    ],
                )

        result = classify_scene(
            detector=MultiBoxUnknownDetector(),
            image_bytes=b"dummy",
            declared_input_kind=None,
        )
        assert result.input_kind == InputKind.MULTI_ITEM
        assert len(result.boxes) == 2


class TestGeminiProviderAdapter:
    """Unit tests for GeminiDetector and GeminiVisionProvider with mocked HTTP."""

    def test_gemini_detector_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            gemini_body = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "input_kind": "single_item",
                                            "boxes": [
                                                {
                                                    "box": [0.1, 0.1, 0.9, 0.9],
                                                    "label": "top",
                                                    "confidence": 0.96,
                                                }
                                            ],
                                            "quality_warnings": [],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
            return httpx.Response(200, json=gemini_body)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        detector = GeminiDetector(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        res = detector.detect(b"image-bytes")
        assert res.input_kind == InputKind.SINGLE_ITEM
        assert len(res.boxes) == 1
        assert res.boxes[0].box == (0.1, 0.1, 0.9, 0.9)
        assert res.boxes[0].label == "top"
        assert res.boxes[0].confidence == 0.96

    def test_gemini_detector_handles_markdown_code_block(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            content_json = json.dumps(
                {
                    "input_kind": "multi_item",
                    "boxes": [
                        {"box": [0.1, 0.1, 0.4, 0.8], "label": "top", "confidence": 0.92},
                        {"box": [0.5, 0.1, 0.9, 0.8], "label": "bottom", "confidence": 0.90},
                    ],
                    "quality_warnings": ["Trang phục hơi nhăn."],
                }
            )
            wrapped_text = f"```json\n{content_json}\n```"
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": wrapped_text}]}}]},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        detector = GeminiDetector(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        res = detector.detect(b"image-bytes")
        assert res.input_kind == InputKind.MULTI_ITEM
        assert len(res.boxes) == 2
        assert "Trang phục hơi nhăn." in res.quality_warnings

    def test_gemini_detector_invalid_json_raises_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "Not a valid json response"}]}}]},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        detector = GeminiDetector(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        with pytest.raises(ProviderError):
            detector.detect(b"image-bytes")

    def test_gemini_detector_timeout_raises_timeout_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Timeout connecting to Gemini")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        detector = GeminiDetector(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        with pytest.raises(TimeoutError):
            detector.detect(b"image-bytes")

    def test_gemini_detector_http_500_raises_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        detector = GeminiDetector(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        with pytest.raises(ProviderError) as exc_info:
            detector.detect(b"image-bytes")
        assert "500" in str(exc_info.value.message)

    def test_gemini_vision_provider_success(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            gemini_body = {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "attributes": {
                                                "category": "top",
                                                "sub_category": "t_shirt",
                                                "primary_color": "black",
                                                "style": "casual",
                                            },
                                            "field_confidence": {
                                                "category": 0.98,
                                                "sub_category": 0.95,
                                                "primary_color": 0.90,
                                                "style": 0.85,
                                            },
                                            "quality_warnings": [],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
            return httpx.Response(200, json=gemini_body)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        vision = GeminiVisionProvider(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        res = vision.extract_attributes(b"crop-bytes")
        assert res.attributes["category"] == "top"
        assert res.attributes["primary_color"] == "black"
        assert res.field_confidence["category"] == 0.98

    def test_gemini_vision_provider_timeout_raises_timeout_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("Timeout during attribute extraction")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        vision = GeminiVisionProvider(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        with pytest.raises(TimeoutError):
            vision.extract_attributes(b"crop-bytes")

    def test_gemini_vision_provider_invalid_json_raises_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": "{malformed json"}]}}]},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        vision = GeminiVisionProvider(
            api_key=SecretStr("mock-key"),
            model="gemini-1.5-flash",
            client=client,
        )

        with pytest.raises(ProviderError):
            vision.extract_attributes(b"crop-bytes")
