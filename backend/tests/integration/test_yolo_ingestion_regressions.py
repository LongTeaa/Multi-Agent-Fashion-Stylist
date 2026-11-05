from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.dependencies import get_db_session, get_object_storage, get_vision_provider
from app.main import app
from app.models.entities import WardrobeItem
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.fakes.vision_fakes import FakeVisionProvider
from app.services.providers import VisionExtractionResult
from app.services.yolo_world_detector import YoloWorldDetector


class CapturingVisionProvider(FakeVisionProvider):
    def __init__(self) -> None:
        super().__init__()
        self.contexts: list[dict[str, Any]] = []

    def extract_attributes(
        self, crop_bytes: bytes, spatial_context: dict[str, Any] | None = None,
    ) -> VisionExtractionResult:
        assert spatial_context is not None
        self.contexts.append(spatial_context)
        return super().extract_attributes(crop_bytes, spatial_context=spatial_context)


def image_bytes(size: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, (180, 150, 100)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_selected_yolo_multi_photo_review_and_confirmation(
    migrated_database: tuple[object, Engine], tmp_path: Path,
) -> None:
    """Preserve overlapping layers/raw boxes and warn on a person-only second photo."""
    _, engine = migrated_database
    storage = LocalObjectStorage(
        root=tmp_path / "storage",
        buckets=StorageBuckets(
            wardrobe="wardrobe-private", thumbnails="wardrobe-thumbnails", tryon="tryon-private",
        ),
    )
    session = MagicMock()
    model_input = MagicMock()
    model_input.name = "images"
    session.get_inputs.return_value = [model_input]
    session.run.side_effect = [
        [np.array([[[230, 120, 410, 420, .95, 5], [240, 130, 400, 410, .90, 3]]], dtype=np.float32)],
        [np.array([[[100, 180, 540, 460, .99, 0]]], dtype=np.float32)],
    ]
    detector = YoloWorldDetector(session=session)
    vision = CapturingVisionProvider()
    model_file = tmp_path / "injected-model.onnx"
    model_file.write_bytes(b"injected session")
    settings = Settings(
        _env_file=None, detector_backend="yolo_world", vision_provider="fake",
        yolo_world_model_path=str(model_file),
    )
    app.dependency_overrides[get_db_session] = lambda: Session(engine)
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_vision_provider] = lambda: vision
    headers = {"X-User-Id": str(uuid4())}
    client = TestClient(app)

    with patch("app.core.dependencies.get_settings", return_value=settings), patch(
        "app.core.dependencies.get_yolo_world_detector", return_value=detector,
    ):
        upload = client.post("/api/v1/ingestions", headers=headers, files=[
            ("images[]", ("layers.png", image_bytes((400, 800)), "image/png")),
            ("images[]", ("person.png", image_bytes((800, 400)), "image/png")),
        ])
    assert upload.status_code == 202, upload.text
    batch_url = f"/api/v1/ingestions/{upload.json()['data']['batch_id']}"
    review = client.get(batch_url, headers=headers).json()["data"]
    assert review["status"] == "needs_review"
    assert len(review["source_images"]) == 2
    assert len(review["detections"]) == 3
    sources = {s["media_asset_id"]: s for s in review["source_images"]}
    layers = [d for d in review["detections"] if sources[d["source_media_asset_id"]]["width"] == 400]
    fallback = [d for d in review["detections"] if sources[d["source_media_asset_id"]]["width"] == 800]
    assert len(layers) == 2
    assert len(fallback) == 1
    assert fallback[0]["raw_bounding_box"] is None
    assert fallback[0]["bounding_box"] == [0, 0, 1, 1]
    assert any("phân tách" in warning for warning in review["quality_warnings"])
    jacket_raw = [.2188, .1875, .7812, .6562]
    jacket = next(d for d in layers if d["raw_bounding_box"] == pytest.approx(jacket_raw, abs=.0001))
    assert jacket["bounding_box"] == jacket["raw_bounding_box"]
    jacket_context = next(c for c in vision.contexts if c["detected_label"] == "jacket")
    assert jacket_context["aspect_ratio"] == pytest.approx(.6)
    assert jacket_context["shape_type"] == "tall_vertical"
    with Session(engine) as db:
        assert db.exec(select(WardrobeItem)).all() == []

    crop_url = f"{batch_url}/detections/{jacket['detection_id']}/crop"
    edited = client.patch(crop_url, headers=headers, json={"bounding_box": [.3, .2, .7, .6]})
    assert edited.status_code == 200, edited.text
    edited_jacket = next(d for d in edited.json()["data"]["detections"] if d["detection_id"] == jacket["detection_id"])
    assert edited_jacket["raw_bounding_box"] == jacket["raw_bounding_box"]
    restored = client.patch(crop_url, headers=headers, json={"bounding_box": jacket["raw_bounding_box"]})
    assert restored.status_code == 200, restored.text
    restored_jacket = next(d for d in restored.json()["data"]["detections"] if d["detection_id"] == jacket["detection_id"])
    assert restored_jacket["bounding_box"] == jacket["raw_bounding_box"]
    assert client.get(restored_jacket["crop_url"], headers=headers).status_code == 200
    assert client.get(restored_jacket["crop_url"], headers={"X-User-Id": str(uuid4())}).status_code in (403, 404)

    payload = {"confirmations": [
        {"detection_id": d["detection_id"], "accepted": True} for d in review["detections"]
    ]}
    confirmed = client.post(f"{batch_url}/confirm", headers=headers, json=payload)
    assert confirmed.status_code == 200, confirmed.text
    confirmed_ids = confirmed.json()["data"]["wardrobe_item_ids"]
    assert len(set(confirmed_ids)) == 3
    retried = client.post(f"{batch_url}/confirm", headers=headers, json=payload)
    assert retried.status_code == 200, retried.text
    assert set(retried.json()["data"]["wardrobe_item_ids"]) == set(confirmed_ids)
    with Session(engine) as db:
        assert len(db.exec(select(WardrobeItem)).all()) == 3
