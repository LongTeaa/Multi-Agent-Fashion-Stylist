from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
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
    assert ctx_shirt["person_relative_y_min"] == pytest.approx(0.0333, abs=0.01)
    assert ctx_shirt["person_relative_y_max"] == pytest.approx(0.3333, abs=0.01)
    assert ctx_shirt["person_relative_height_percent"] == pytest.approx(30.0, abs=0.1)

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
    assert ctx_pants["person_relative_height_percent"] == pytest.approx(60.0, abs=0.1)


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


def test_gemini_vision_provider_incorporates_person_relative_quantitative_guidance() -> None:
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
                                            "length": "cropped",
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
    provider = GeminiVisionProvider(key_pool=pool, client=client)

    dummy_crop = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    spatial_ctx = {
        "box": [0.25, 0.32, 0.75, 0.50],
        "relative_height_percent": 18.0,
        "relative_width_percent": 50.0,
        "aspect_ratio": 2.78,
        "shape_type": "wide_horizontal",
        "estimated_body_zone": "upper_torso_head",
        "scene_kind": "worn_outfit",
        "detected_label": "top",
        "person_relative": True,
        "person_relative_y_min": 0.0333,
        "person_relative_y_max": 0.3333,
        "person_relative_height_percent": 30.0,
    }

    res = provider.extract_attributes(dummy_crop, spatial_context=spatial_ctx)
    assert res.attributes["category"] == "top"

    assert captured_payload is not None
    prompt_text = captured_payload["contents"][0]["parts"][0]["text"]
    assert "Garment proportion: aspect ratio 2.78 (wide_horizontal)" in prompt_text
    assert "Wearer-relative vertical span: from 3.3% to 33.3% of person height (spans 30.0% of wearer body)" in prompt_text
    assert "Anatomical/body position: upper_torso_head" in prompt_text
    assert "Upper body with span < 25% or ending above waist -> 'cropped'" in prompt_text
    assert "VISUAL PRIORITY PRINCIPLE" in prompt_text


def test_gemini_vision_provider_incorporates_flat_lay_layout_guidance() -> None:
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
    provider = GeminiVisionProvider(key_pool=pool, client=client)

    dummy_crop = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    spatial_ctx = {
        "box": [0.20, 0.10, 0.80, 0.30],
        "relative_height_percent": 20.0,
        "relative_width_percent": 60.0,
        "aspect_ratio": 3.0,
        "shape_type": "wide_horizontal",
        "estimated_body_zone": None,
        "scene_kind": "multi_item",
        "detected_label": "top",
        "person_relative": False,
        "flat_lay_rank": "top_layer",
    }

    res = provider.extract_attributes(dummy_crop, spatial_context=spatial_ctx)
    assert res.attributes["category"] == "top"

    assert captured_payload is not None
    prompt_text = captured_payload["contents"][0]["parts"][0]["text"]
    assert "Garment proportion: aspect ratio 3.0 (wide_horizontal)" in prompt_text
    assert "Flat-lay arrangement layer: top_layer (items laid flat on surface)" in prompt_text
    assert "Garment is laid flat: determine category and length from intrinsic garment proportion" in prompt_text
    assert "Wearer-relative vertical span" not in prompt_text
    assert "Anatomical/body position" not in prompt_text


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


def test_classify_scene_detects_worn_outfit_and_filters_person_box() -> None:
    from app.services.classifier import classify_scene
    from app.services.providers import BoundingBoxDetection, DetectionResult

    detector = MagicMock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.UNKNOWN,
        boxes=[
            BoundingBoxDetection(box=(0.15, 0.05, 0.85, 0.95), label="person", confidence=0.98),
            BoundingBoxDetection(box=(0.20, 0.15, 0.80, 0.45), label="top", confidence=0.92),
            BoundingBoxDetection(box=(0.25, 0.46, 0.75, 0.85), label="bottom", confidence=0.91),
        ],
        quality_warnings=[],
    )

    res = classify_scene(detector=detector, image_bytes=b"fake")
    assert res.input_kind == InputKind.WORN_OUTFIT
    assert res.person_box == (0.15, 0.05, 0.85, 0.95)
    # Crucial: "person" is filtered out from boxes to prevent cropping the whole human into wardrobe
    assert len(res.boxes) == 2
    assert [b.label for b in res.boxes] == ["top", "bottom"]


def test_classify_scene_detects_flat_lay_multi_item_without_person() -> None:
    from app.services.classifier import classify_scene
    from app.services.providers import BoundingBoxDetection, DetectionResult

    detector = MagicMock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.UNKNOWN,
        boxes=[
            BoundingBoxDetection(box=(0.1, 0.1, 0.9, 0.4), label="top", confidence=0.9),
            BoundingBoxDetection(box=(0.1, 0.5, 0.9, 0.9), label="bottom", confidence=0.9),
        ],
        quality_warnings=[],
    )

    res = classify_scene(detector=detector, image_bytes=b"fake")
    assert res.input_kind == InputKind.MULTI_ITEM
    assert res.person_box is None
    assert len(res.boxes) == 2


def test_classify_scene_detects_single_item_without_person() -> None:
    from app.services.classifier import classify_scene
    from app.services.providers import BoundingBoxDetection, DetectionResult

    detector = MagicMock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.UNKNOWN,
        boxes=[
            BoundingBoxDetection(box=(0.1, 0.1, 0.9, 0.9), label="t-shirt", confidence=0.95),
        ],
        quality_warnings=[],
    )

    res = classify_scene(detector=detector, image_bytes=b"fake")
    assert res.input_kind == InputKind.SINGLE_ITEM
    assert res.person_box is None
    assert len(res.boxes) == 1


def test_process_ingestion_batch_passes_person_box_and_all_boxes_to_spatial_context() -> None:
    from io import BytesIO
    from unittest.mock import MagicMock, patch
    from PIL import Image
    from app.models.entities import IngestionStatus, MediaKind
    from app.services.ingestion_service import process_ingestion_batch
    from app.services.providers import BoundingBoxDetection, DetectionResult

    batch = MagicMock()
    batch.id = "batch-pbox"
    batch.user_id = "user-pbox"
    batch.status = IngestionStatus.PROCESSING
    batch.input_kind = InputKind.UNKNOWN
    batch.quality_warnings = []

    asset = MagicMock()
    asset.id = "asset-pbox"
    asset.user_id = "user-pbox"
    asset.ingestion_batch_id = "batch-pbox"
    asset.kind = MediaKind.ORIGINAL
    asset.bucket = "uploads"
    asset.object_key = "photo.jpg"

    session = MagicMock()
    session.get.return_value = batch
    session.exec.return_value.all.return_value = [asset]
    session.execute.return_value.rowcount = 1

    buf = BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    storage = MagicMock()
    storage.get_object.return_value = img_bytes

    # Detector returns person + shirt
    person_box = (0.1, 0.2, 0.9, 0.9)  # height = 0.70
    shirt_box = (0.2, 0.25, 0.8, 0.45) # center_y = 0.35 -> relative to person: (0.35 - 0.2) / 0.7 = 0.214 (< 0.35)
    detector = MagicMock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.UNKNOWN,
        boxes=[
            BoundingBoxDetection(box=person_box, label="person", confidence=0.99),
            BoundingBoxDetection(box=shirt_box, label="top", confidence=0.95),
        ],
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
            batch_id="batch-pbox",
            user_id="user-pbox",
        )

    # 1. Person box was passed and used for coordinate normalization
    assert fake_vision.last_spatial_context is not None
    assert fake_vision.last_spatial_context["scene_kind"] == "worn_outfit"
    assert fake_vision.last_spatial_context["person_relative"] is True
    assert fake_vision.last_spatial_context["person_box"] == list(person_box)
    assert fake_vision.last_spatial_context["estimated_body_zone"] == "upper_torso_head"
    # 2. Only 1 crop was made (the shirt), the person box was NOT cropped into user's wardrobe!
    assert session.add_all.call_count >= 2
    detections_added = session.add_all.call_args_list[1][0][0]
    assert detections_added[0].bounding_box == shirt_box


def test_classify_scene_primary_wearer_resolves_multi_person_bystander() -> None:
    from app.services.classifier import classify_scene, find_primary_wearer
    from app.services.providers import BoundingBoxDetection, DetectionResult

    # Bystander box: large box in foreground (area = 0.5 * 0.9 = 0.45), but contains NO garments
    bystander_person = BoundingBoxDetection(
        box=(0.0, 0.1, 0.5, 1.0),
        label="person",
        confidence=0.99,
    )
    # Primary wearer box: smaller box in background (area = 0.3 * 0.8 = 0.24), contains jacket and pants
    wearer_person = BoundingBoxDetection(
        box=(0.55, 0.1, 0.85, 0.9),
        label="person",
        confidence=0.95,
    )

    jacket = BoundingBoxDetection(
        box=(0.58, 0.2, 0.82, 0.5),
        label="jacket",
        confidence=0.93,
    )
    pants = BoundingBoxDetection(
        box=(0.60, 0.5, 0.80, 0.85),
        label="trousers",
        confidence=0.91,
    )

    # Unit test find_primary_wearer directly
    selected = find_primary_wearer(
        person_boxes=[bystander_person, wearer_person],
        garment_boxes=[jacket, pants],
    )
    # Must pick wearer_person, NOT the larger bystander!
    assert selected == wearer_person.box

    # Integration test with classify_scene
    detector = MagicMock()
    detector.detect.return_value = DetectionResult(
        input_kind=InputKind.UNKNOWN,
        boxes=[bystander_person, wearer_person, jacket, pants],
        quality_warnings=[],
    )

    res = classify_scene(detector=detector, image_bytes=b"fake-bytes")
    assert res.input_kind == InputKind.WORN_OUTFIT
    assert res.person_box == wearer_person.box
    # The two person boxes must be filtered out, leaving only the two garments
    assert len(res.boxes) == 2
    assert [b.label for b in res.boxes] == ["jacket", "trousers"]


def test_gemini_providers_dynamically_resolve_models_from_settings() -> None:
    from app.core.config import Settings
    from app.services.gemini_provider import GeminiDetector, GeminiVisionProvider

    custom_settings = Settings(
        gemini_api_key=SecretStr("custom-key"),
        vision_model="gemini-2.5-flash",
        detector_model="gemini-2.0-flash",
    )

    with patch("app.core.config.get_settings", return_value=custom_settings):
        # When model is None, GeminiDetector resolves from settings.get_detector_model()
        detector = GeminiDetector(api_key=SecretStr("test-k"), model=None)
        assert detector.model == "gemini-2.0-flash"

        # When model is None, GeminiVisionProvider resolves from settings.get_vision_model()
        vision = GeminiVisionProvider(api_key=SecretStr("test-k"), model=None)
        assert vision.model == "gemini-2.5-flash"
