"""Guard the real-image evaluation script against provider-protocol drift.

The private photos are git-ignored, so this runs the script's offline replay on
synthetic images. It failed silently once: the pipeline started passing
``spatial_context`` to ``extract_attributes``, the replay provider rejected it, the
error was swallowed, and confirmation then failed on ``category="unknown"``.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import ModuleType

from PIL import Image

from app.services.providers import VisionProviderProtocol

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_real_ingestion.py"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("evaluate_real_ingestion", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Pydantic resolves postponed annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _jpeg(width: int, height: int, blocks: list[tuple[tuple[int, int, int, int], str]]) -> bytes:
    image = Image.new("RGB", (width, height), "white")
    for (x1, y1, x2, y2), color in blocks:
        image.paste(Image.new("RGB", (x2 - x1, y2 - y1), color), (x1, y1))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def test_replay_provider_matches_the_vision_protocol_signature() -> None:
    script = _load_script()
    replay_params = list(inspect.signature(script.AnnotatedReplay.extract_attributes).parameters)
    protocol_params = list(inspect.signature(VisionProviderProtocol.extract_attributes).parameters)
    assert replay_params == protocol_params


def test_offline_replay_confirms_every_annotated_region(tmp_path: Path) -> None:
    script = _load_script()
    single = _jpeg(400, 600, [((80, 120, 320, 480), "navy")])
    multi = _jpeg(600, 400, [((40, 60, 260, 340), "red"), ((340, 80, 560, 360), "green")])
    cases = [
        (
            script.Case(
                id="synthetic-single",
                file="single.jpg",
                sha256=sha256(single).hexdigest(),
                regions=[script.Region(category="top", box=(0.2, 0.2, 0.8, 0.8))],
                expected_box_count=1,
            ),
            single,
        ),
        (
            script.Case(
                id="synthetic-multi",
                file="multi.jpg",
                sha256=sha256(multi).hexdigest(),
                regions=[
                    script.Region(category="top", box=(0.06, 0.15, 0.44, 0.85)),
                    script.Region(category="bottom", box=(0.56, 0.2, 0.94, 0.9)),
                ],
                expected_box_count=2,
            ),
            multi,
        ),
    ]

    result = script.replay_pipeline(cases, tmp_path)

    assert result["status"] == "passed"
    assert result["crops"] == 3
    assert result["no_item_before_confirmation"] is True
    assert result["idempotent_confirmation"] is True
