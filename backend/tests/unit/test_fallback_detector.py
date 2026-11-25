"""Gemini detector with a lazily loaded YOLO-World fallback (roadmap Phase 5)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.core import dependencies
from app.core.config import Settings
from app.models.entities import InputKind
from app.services.fallback_detector import FallbackDetector
from app.schemas.common import ProviderError
from app.services.providers import BoundingBoxDetection, DetectionResult

SECRET_BODY = "upstream body with key AIzaSECRET"


class StubDetector:
    def __init__(self, result: DetectionResult | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def detect(self, image_bytes: bytes) -> DetectionResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def _result(label: str) -> DetectionResult:
    return DetectionResult(
        input_kind=InputKind.MULTI_ITEM,
        boxes=[BoundingBoxDetection(box=(0.1, 0.1, 0.5, 0.5), label=label, confidence=0.9)],
    )


def _fallback(primary: StubDetector, secondary: StubDetector) -> tuple[FallbackDetector, list[int]]:
    built: list[int] = []

    def factory() -> StubDetector:
        built.append(1)
        return secondary

    return FallbackDetector(primary, factory, primary_name="gemini", secondary_name="yolo_world"), built


def test_primary_success_never_builds_secondary() -> None:
    primary, secondary = StubDetector(_result("shirt")), StubDetector(_result("coat"))
    detector, built = _fallback(primary, secondary)

    assert detector.detect(b"img").boxes[0].label == "shirt"
    assert built == [] and secondary.calls == 0


def test_empty_primary_result_does_not_trigger_fallback() -> None:
    empty = DetectionResult(input_kind=InputKind.SINGLE_ITEM, boxes=[])
    primary, secondary = StubDetector(empty), StubDetector(_result("coat"))
    detector, built = _fallback(primary, secondary)

    assert detector.detect(b"img") is empty
    assert built == [] and secondary.calls == 0


@pytest.mark.parametrize("error", [ProviderError(SECRET_BODY), TimeoutError(), RuntimeError(SECRET_BODY)])
def test_primary_error_uses_secondary_once(error: Exception, caplog: pytest.LogCaptureFixture) -> None:
    primary, secondary = StubDetector(error=error), StubDetector(_result("coat"))
    detector, built = _fallback(primary, secondary)

    with caplog.at_level(logging.WARNING):
        result = detector.detect(b"img")

    assert result.boxes[0].label == "coat"
    assert secondary.calls == 1 and built == [1]
    assert "AIzaSECRET" not in caplog.text


def test_secondary_is_built_once_across_failures() -> None:
    primary, secondary = StubDetector(error=ProviderError("x")), StubDetector(_result("coat"))
    detector, built = _fallback(primary, secondary)

    detector.detect(b"a")
    detector.detect(b"b")

    assert built == [1] and secondary.calls == 2


def test_both_failing_raises_primary_error() -> None:
    primary_error = ProviderError("primary")
    primary = StubDetector(error=primary_error)
    secondary = StubDetector(error=RuntimeError("secondary"))
    detector, _ = _fallback(primary, secondary)

    with pytest.raises(ProviderError) as raised:
        detector.detect(b"img")
    assert raised.value is primary_error


def _gemini_settings(tmp_path: Path, **overrides: object) -> Settings:
    model = tmp_path / "yolo.onnx"
    model.write_bytes(b"onnx")
    values: dict[str, object] = dict(
        vision_provider="gemini",
        detector_backend="gemini",
        gemini_api_key=SecretStr("mock-key"),
        vision_model="gemini-test",
        yolo_world_model_path=str(model),
    )
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _get_detector_with(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> object:
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    return dependencies.get_detector()


def test_default_settings_keep_plain_gemini_detector(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.services.gemini_provider import GeminiDetector

    detector = _get_detector_with(monkeypatch, _gemini_settings(tmp_path))
    assert isinstance(detector, GeminiDetector)


def test_yolo_fallback_wraps_gemini_without_loading_yolo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    loaded: list[Settings] = []
    monkeypatch.setattr(dependencies, "get_yolo_world_detector", lambda s=None: loaded.append(s))

    detector = _get_detector_with(
        monkeypatch, _gemini_settings(tmp_path, detector_fallback_backend="yolo_world")
    )

    assert isinstance(detector, FallbackDetector)
    assert detector.primary_name == "gemini" and detector.secondary_name == "yolo_world"
    assert loaded == []


def test_missing_yolo_model_skips_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.services.gemini_provider import GeminiDetector

    settings = _gemini_settings(
        tmp_path,
        detector_fallback_backend="yolo_world",
        yolo_world_model_path=str(tmp_path / "missing.onnx"),
    )
    assert isinstance(_get_detector_with(monkeypatch, settings), GeminiDetector)


def test_fallback_setting_does_not_affect_yolo_backend(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sentinel = StubDetector(_result("shirt"))
    monkeypatch.setattr(dependencies, "get_yolo_world_detector", lambda s=None: sentinel)

    settings = _gemini_settings(
        tmp_path, detector_backend="yolo_world", detector_fallback_backend="yolo_world"
    )
    assert _get_detector_with(monkeypatch, settings) is sentinel
