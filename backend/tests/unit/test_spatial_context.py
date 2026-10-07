from __future__ import annotations

import json
import httpx
import pytest
from pydantic import SecretStr

from app.models.entities import InputKind
from app.services.gemini_key_pool import GeminiKeyPool
from app.services.gemini_provider import GeminiVisionProvider
from app.services.fakes.vision_fakes import FakeVisionProvider
from app.services.ingestion_service import compute_spatial_context


def test_compute_spatial_context_zones_and_metrics() -> None:
    # 1. Upper body (shirt / hat) in worn_outfit
    upper_box = (0.15, 0.05, 0.85, 0.35)
    ctx_upper = compute_spatial_context(
        box=upper_box,
        scene_kind=InputKind.WORN_OUTFIT,
        detected_label="top",
    )
    assert ctx_upper["estimated_body_zone"] == "upper_torso_head"
    assert ctx_upper["relative_height_percent"] == 30.0
    assert ctx_upper["relative_width_percent"] == 70.0
    assert ctx_upper["scene_kind"] == "worn_outfit"
    assert ctx_upper["detected_label"] == "top"

    # 2. Non-worn outfit (single_item / flat lay) -> estimated_body_zone must be None
    mid_box = (0.20, 0.40, 0.80, 0.60)
    ctx_mid = compute_spatial_context(box=mid_box, scene_kind="single_item", detected_label="shorts")
    assert ctx_mid["estimated_body_zone"] is None
    assert ctx_mid["relative_height_percent"] == 20.0
    assert ctx_mid["scene_kind"] == "single_item"

    # 3. Mid body in worn_outfit -> mid_torso_waist
    ctx_mid_worn = compute_spatial_context(box=mid_box, scene_kind="worn_outfit", detected_label="shorts")
    assert ctx_mid_worn["estimated_body_zone"] == "mid_torso_waist"

    # 4. Lower body (trousers / skirt) in worn_outfit
    lower_box = (0.25, 0.50, 0.75, 0.84)
    ctx_lower = compute_spatial_context(box=lower_box, scene_kind="worn_outfit", detected_label="bottom")
    assert ctx_lower["estimated_body_zone"] == "lower_body_legs"

    # 5. Footwear (shoes / boots) in worn_outfit
    foot_box = (0.30, 0.86, 0.70, 0.98)
    ctx_foot = compute_spatial_context(box=foot_box, scene_kind="worn_outfit", detected_label="shoes")
    assert ctx_foot["estimated_body_zone"] == "feet_footwear"


def test_compute_spatial_context_with_person_box_normalization() -> None:
    # A person standing further back, occupying y: 0.30 to 0.90 (height = 0.60)
    person_box = (0.20, 0.30, 0.80, 0.90)

    # Shirt worn on upper body: y from 0.32 to 0.50 (center_y = 0.41)
    # Under old frame coordinates (center_y=0.41), this would be wrongly classified as mid_torso_waist.
    # Under person normalization: (0.41 - 0.30) / 0.60 = 0.183 (< 0.35) -> correctly upper_torso_head!
    shirt_box = (0.25, 0.32, 0.75, 0.50)
    ctx_shirt = compute_spatial_context(
        box=shirt_box,
        scene_kind=InputKind.WORN_OUTFIT,
        detected_label="top",
        person_box=person_box,
    )
    assert ctx_shirt["person_relative"] is True
    assert ctx_shirt["estimated_body_zone"] == "upper_torso_head"
    assert ctx_shirt["person_box"] == list(person_box)
    assert ctx_shirt["person_relative_center_y"] == pytest.approx(0.1833, abs=0.01)

    # Pants worn on lower body: y from 0.52 to 0.88 (height=0.36, width=0.22, aspect_ratio=0.61 -> tall_vertical)
    # Center y = 0.70. Relative to person: (0.70 - 0.30) / 0.60 = 0.667 -> lower_body_legs
    pants_box = (0.35, 0.52, 0.57, 0.88)
    ctx_pants = compute_spatial_context(
        box=pants_box,
        scene_kind=InputKind.WORN_OUTFIT,
        detected_label="bottom",
        person_box=person_box,
    )
    assert ctx_pants["estimated_body_zone"] == "lower_body_legs"
    assert ctx_pants["shape_type"] == "tall_vertical"


def test_compute_spatial_context_flat_lay_ranking_and_shape_types() -> None:
    top_box = (0.20, 0.10, 0.80, 0.30)     # aspect_ratio: 0.6 / 0.2 = 3.0 -> wide_horizontal
    pants_box = (0.25, 0.35, 0.75, 0.75)   # aspect_ratio: 0.5 / 0.4 = 1.25
    shoes_box = (0.30, 0.80, 0.70, 0.95)   # aspect_ratio: 0.4 / 0.15 = 2.67
    all_boxes = [top_box, pants_box, shoes_box]

    ctx_top = compute_spatial_context(
        box=top_box,
        scene_kind=InputKind.MULTI_ITEM,
        detected_label="top",
        all_boxes=all_boxes,
    )
    assert ctx_top["estimated_body_zone"] is None
    assert ctx_top["flat_lay_rank"] == "top_layer"
    assert ctx_top["shape_type"] == "wide_horizontal"

    ctx_pants = compute_spatial_context(
        box=pants_box,
        scene_kind=InputKind.MULTI_ITEM,
        detected_label="bottom",
        all_boxes=all_boxes,
    )
    assert ctx_pants["estimated_body_zone"] is None
    assert ctx_pants["flat_lay_rank"] == "middle_layer"

    ctx_shoes = compute_spatial_context(
        box=shoes_box,
        scene_kind=InputKind.MULTI_ITEM,
        detected_label="shoes",
        all_boxes=all_boxes,
    )
    assert ctx_shoes["estimated_body_zone"] is None
    assert ctx_shoes["flat_lay_rank"] == "bottom_layer"



def test_gemini_vision_provider_incorporates_spatial_context_in_prompt() -> None:
    captured_payload: dict | None = None

    def mock_transport(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps({
                                        "attributes": {
                                            "category": "top",
                                            "sub_category": "crop-top",
                                            "primary_color": "black",
                                            "length": "cropped",
                                            "silhouette_level": 2,
                                            "comfort_level": 4,
                                        },
                                        "field_confidence": {
                                            "category": 0.95,
                                            "length": 0.92,
                                        },
                                        "quality_warnings": [],
                                    })
                                }
                            ]
                        }
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    pool = GeminiKeyPool([SecretStr("test-key")])
    provider = GeminiVisionProvider(
        key_pool=pool,
        client=client,
    )

    dummy_crop = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    spatial_ctx = {
        "box": [0.1, 0.15, 0.9, 0.35],
        "relative_height_percent": 20.0,
        "relative_width_percent": 80.0,
        "estimated_body_zone": "upper_torso_head",
        "scene_kind": "worn_outfit",
        "detected_label": "top",
    }

    res = provider.extract_attributes(dummy_crop, spatial_context=spatial_ctx)
    assert res.attributes["category"] == "top"
    assert res.attributes["length"] == "cropped"

    # Verify that captured payload contains spatial reasoning directives
    assert captured_payload is not None
    prompt_text = captured_payload["contents"][0]["parts"][0]["text"]
    assert "SPATIAL CONTEXT FROM ORIGINAL FULL-FRAME IMAGE" in prompt_text
    assert "spans 20.0% of total frame height" in prompt_text
    assert "upper_torso_head" in prompt_text
    assert "SPATIAL REASONING GUIDANCE FOR ATTRIBUTES" in prompt_text


def test_gemini_vision_provider_works_without_spatial_context() -> None:
    captured_payload: dict | None = None

    def mock_transport(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps({
                                        "attributes": {
                                            "category": "top",
                                            "comfort_level": 3,
                                            "silhouette_level": 3,
                                            "length": "hip",
                                        },
                                        "field_confidence": {},
                                        "quality_warnings": [],
                                    })
                                }
                            ]
                        }
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    pool = GeminiKeyPool([SecretStr("test-key")])
    provider = GeminiVisionProvider(
        key_pool=pool,
        client=client,
    )

    dummy_crop = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    res = provider.extract_attributes(dummy_crop, spatial_context=None)
    assert res.attributes["category"] == "top"

    assert captured_payload is not None
    prompt_text = captured_payload["contents"][0]["parts"][0]["text"]
    assert "SPATIAL CONTEXT FROM ORIGINAL FULL-FRAME IMAGE" not in prompt_text


def test_gemini_vision_provider_omits_body_zone_for_non_worn_outfit() -> None:
    captured_payload: dict | None = None

    def mock_transport(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps({
                                        "attributes": {
                                            "category": "top",
                                            "comfort_level": 3,
                                            "silhouette_level": 3,
                                            "length": "hip",
                                        },
                                        "field_confidence": {},
                                        "quality_warnings": [],
                                    })
                                }
                            ]
                        }
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    pool = GeminiKeyPool([SecretStr("test-key")])
    provider = GeminiVisionProvider(
        key_pool=pool,
        client=client,
    )

    dummy_crop = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    spatial_ctx = {
        "box": [0.1, 0.2, 0.9, 0.8],
        "relative_height_percent": 60.0,
        "relative_width_percent": 80.0,
        "estimated_body_zone": None,
        "scene_kind": "single_item",
        "detected_label": "clothing",
    }
    res = provider.extract_attributes(dummy_crop, spatial_context=spatial_ctx)
    assert res.attributes["category"] == "top"

    assert captured_payload is not None
    prompt_text = captured_payload["contents"][0]["parts"][0]["text"]
    # Spatial section present
    assert "SPATIAL CONTEXT FROM ORIGINAL FULL-FRAME IMAGE" in prompt_text
    assert "spans 60.0% of total frame height" in prompt_text
    assert "Original frame scene kind: single_item" in prompt_text
    # But anatomical guidance & body position omitted
    assert "Anatomical/body position" not in prompt_text
    assert "SPATIAL REASONING GUIDANCE FOR ATTRIBUTES" not in prompt_text



def test_fake_vision_provider_accepts_spatial_context() -> None:
    fake = FakeVisionProvider(scenario="golden_polo")
    res = fake.extract_attributes(
        crop_bytes=b"any",
        spatial_context={"box": [0.1, 0.1, 0.9, 0.9]},
    )
    assert res.attributes["category"] == "top"
    assert fake.last_spatial_context == {"box": [0.1, 0.1, 0.9, 0.9]}


def test_process_ingestion_batch_passes_detected_kind_to_vision_provider() -> None:
    from io import BytesIO
    from unittest.mock import MagicMock, patch
    from PIL import Image
    from app.models.entities import IngestionStatus, MediaKind
    from app.services.ingestion_service import process_ingestion_batch
    from app.services.providers import BoundingBoxDetection, DetectionResult

    batch = MagicMock()
    batch.id = "batch-123"
    batch.user_id = "user-123"
    batch.status = IngestionStatus.PROCESSING
    batch.input_kind = InputKind.UNKNOWN
    batch.quality_warnings = []

    asset = MagicMock()
    asset.id = "asset-123"
    asset.user_id = "user-123"
    asset.ingestion_batch_id = "batch-123"
    asset.kind = MediaKind.ORIGINAL
    asset.bucket = "uploads"
    asset.object_key = "photo.jpg"

    session = MagicMock()
    session.get.return_value = batch
    session.exec.return_value.all.return_value = [asset]

    buf = BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    storage = MagicMock()
    storage.get_object.return_value = img_bytes

    detector = MagicMock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.WORN_OUTFIT,
        boxes=[BoundingBoxDetection(box=(0.1, 0.1, 0.9, 0.35), label="top", confidence=0.95)],
        quality_warnings=[],
    )

    fake_vision = FakeVisionProvider(scenario="golden_polo")

    with patch("app.services.ingestion_service.stage_object_upload"), \
         patch("app.services.ingestion_service.get_settings"):
        process_ingestion_batch(
            session=session,
            storage=storage,
            detector=detector,
            vision_provider=fake_vision,
            batch_id="batch-123",
            user_id="user-123",
        )

    # Verify that the detected scene_kind (worn_outfit) was passed, NOT initial unknown!
    assert fake_vision.last_spatial_context is not None
    assert fake_vision.last_spatial_context["scene_kind"] == "worn_outfit"
    assert fake_vision.last_spatial_context["estimated_body_zone"] == "upper_torso_head"


