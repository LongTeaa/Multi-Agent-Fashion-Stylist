from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from PIL import Image
from pydantic import SecretStr
import pytest

from scripts import evaluate_real_ingestion as runner
from app.models.entities import InputKind
from app.services.providers import BoundingBoxDetection, DetectionResult


@pytest.mark.parametrize("label,expected_size", [("top", (60, 120)), ("shoes", (64, 128))])
def test_selected_live_case_saves_crop_and_reports_only_selected_denominator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str, expected_size: tuple[int, int],
) -> None:
    buffer = BytesIO()
    Image.new("RGB", (100, 200), "blue").save(buffer, format="PNG")
    raw = buffer.getvalue()
    (tmp_path / "a.png").write_bytes(raw)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(dict(dataset_version="test", annotation_kind="test",
        iou_threshold=.5, cases=[dict(id=name, file="a.png", sha256=sha256(raw).hexdigest(),
            regions=[dict(category="footwear" if label == "shoes" else "top", box=[.1, .2, .7, .8])], expected_box_count=1)
            for name in ("a", "b")])), encoding="utf-8")
    calls: list[bytes] = []

    class Detector:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def detect(self, image_bytes: bytes) -> DetectionResult:
            calls.append(image_bytes)
            return DetectionResult(input_kind=InputKind.SINGLE_ITEM,
                boxes=[BoundingBoxDetection(box=(.1, .2, .7, .8), label=label)])

    monkeypatch.setattr(runner, "GeminiDetector", Detector)
    monkeypatch.setattr(runner, "replay_pipeline", lambda cases, output: {"status": "test_stub"})
    monkeypatch.setattr(runner, "get_settings", lambda: SimpleNamespace(
        gemini_api_key=SecretStr("test"), vision_model="test", vision_provider="gemini"))
    monkeypatch.setattr(sys, "argv", ["evaluate", "--manifest", str(manifest),
        "--input-dir", str(tmp_path), "--live", "--case", "b"])
    assert runner.main() == 0
    assert calls == [raw]
    directory = next(tmp_path.glob("run-*"))
    result = json.loads((directory / "report.json").read_text(encoding="utf-8"))["live"]
    assert result["total_cases"] == result["available_cases"] == 1
    assert result["selected_case_ids"] == ["b"]
    assert result["manifest_sha256"] == sha256(manifest.read_bytes()).hexdigest()
    crop = result["results"][0]["crops"][0]
    assert (crop["width"], crop["height"]) == expected_size
    assert result["crop_policy"] == "isolated-footwear-margin-v1"
    assert result["results"][0]["raw_boxes"][0]["box"] == [.1, .2, .7, .8]
    assert result["results"][0]["input_kind_inferred"] is False
    assert sha256((directory / crop["file"]).read_bytes()).hexdigest() == crop["sha256"]
