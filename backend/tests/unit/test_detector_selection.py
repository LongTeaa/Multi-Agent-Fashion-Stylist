from unittest.mock import patch

import pytest
from pydantic import SecretStr

from app.core.config import Settings, validate_detector_configuration
from app.core.dependencies import get_detector
from app.services.fakes.vision_fakes import FakeDetector
from app.services.gemini_provider import GeminiDetector


@pytest.mark.parametrize("vision_provider", ["fake", "gemini"])
def test_auto_detector_follows_vision_provider(vision_provider: str) -> None:
    settings = Settings(
        _env_file=None,
        detector_backend="auto",
        vision_provider=vision_provider,
        gemini_api_key=SecretStr("test-only-key"),
        vision_model="test-model",
    )
    with patch("app.core.dependencies.get_settings", return_value=settings):
        detector = get_detector()
    expected = FakeDetector if vision_provider == "fake" else GeminiDetector
    assert isinstance(detector, expected)


def test_explicit_gemini_detector_supports_fake_attribute_extraction() -> None:
    settings = Settings(
        _env_file=None,
        detector_backend="gemini",
        vision_provider="fake",
        gemini_api_key=SecretStr("test-only-key"),
        detector_model="detector-test-model",
    )
    with patch("app.core.dependencies.get_settings", return_value=settings):
        detector = get_detector()
    assert isinstance(detector, GeminiDetector)
    assert detector.model == "detector-test-model"


def test_explicit_fake_detector_does_not_require_gemini_credentials() -> None:
    settings = Settings(
        _env_file=None,
        detector_backend="fake",
        vision_provider="gemini",
        gemini_api_key=None,
    )
    with patch("app.core.dependencies.get_settings", return_value=settings):
        assert isinstance(get_detector(), FakeDetector)


def test_auto_gemini_detector_validates_credentials() -> None:
    settings = Settings(
        _env_file=None,
        detector_backend="auto",
        vision_provider="gemini",
        gemini_api_key=None,
    )
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        validate_detector_configuration(settings)
