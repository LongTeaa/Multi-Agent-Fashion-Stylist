from io import BytesIO
import json

import httpx
from PIL import Image
from pydantic import SecretStr, ValidationError
import pytest

from app.services.crop_engine import crop_item_and_generate_thumbnail
from app.services.gemini_provider import GeminiBoxDetection, GeminiDetector
from app.services.vision_evaluation import region_retention


def test_native_asymmetric_coordinates_are_converted_before_cropping() -> None:
    # Actual worn-polo response was [251, 298, 729, 692] in Gemini YXYX.
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        schema = payload["generationConfig"]["responseSchema"]
        assert "box_2d" in schema["properties"]["boxes"]["items"]["required"]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps({
            "input_kind": "worn_outfit", "boxes": [{"box_2d": [251, 298, 729, 692], "label": "top"}],
            "quality_warnings": [],
        })}]}}]})

    raw = BytesIO()
    Image.new("RGB", (900, 900), "white").save(raw, format="PNG")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        detected = GeminiDetector(SecretStr("test-key"), "test-model", client=client).detect(raw.getvalue())
    assert detected.boxes[0].box == (.298, .251, .692, .729)
    crop = crop_item_and_generate_thumbnail(raw.getvalue(), detected.boxes[0].box)
    assert (crop.crop_width, crop.crop_height) == (354, 431)


@pytest.mark.parametrize("values", [
    {"box": [251, 298, 729, 692]},  # Ambiguous old field must not be guessed.
    {"box_2d": [-1, 100, 900, 900]},
    {"box_2d": [100, 100, 1001, 900]},
    {"box_2d": [500, 100, 200, 900]},
    {"box": [.1, .1, .1, .9]},
    {"box": [.1, .1, .9, .9], "box_2d": [100, 100, 900, 900]},
    {},
])
def test_ambiguous_out_of_range_or_degenerate_boxes_are_rejected(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GeminiBoxDetection.model_validate({"label": "top", **values})


def test_explicit_legacy_canonical_box_is_not_transposed() -> None:
    assert GeminiBoxDetection(box=(.1, .2, .7, .8), label="top").canonical_box() == (.1, .2, .7, .8)


def test_sneaker_pair_retains_both_shoes_after_axis_conversion() -> None:
    expected = (.085, .26, .92, .86)
    old_misinterpreted = (.27, .093, .86, .91)
    corrected = GeminiBoxDetection(box_2d=(270, 93, 860, 910), label="shoes").canonical_box()
    assert region_retention(expected, old_misinterpreted) < .75
    assert region_retention(expected, corrected) > .95
