"""A failing Gemini detector falls back to YOLO-World boxes, not the full-frame box (Phase 5)."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session

from app.core.dependencies import get_db_session, get_detector, get_object_storage, get_vision_provider
from app.main import app
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider
from app.services.fallback_detector import FallbackDetector

FULL_FRAME = [0.0, 0.0, 1.0, 1.0]


def _image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (300, 300), color=(200, 100, 50)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def storage(tmp_path: Path) -> LocalObjectStorage:
    buckets = StorageBuckets(wardrobe="wardrobe-private", thumbnails="wardrobe-thumbnails", tryon="tryon-private")
    return LocalObjectStorage(root=tmp_path / "storage", buckets=buckets)


def _review_boxes(engine: object, storage: LocalObjectStorage, detector: object) -> list[list[float]]:
    app.dependency_overrides[get_db_session] = lambda: Session(engine)
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_detector] = lambda: detector
    app.dependency_overrides[get_vision_provider] = lambda: FakeVisionProvider(scenario="golden_polo")
    try:
        client = TestClient(app)
        user = {"X-User-Id": str(uuid4())}
        upload = client.post(
            "/api/v1/ingestions", headers=user,
            files=[("images[]", ("flat_lay.jpg", _image_bytes(), "image/jpeg"))],
        )
        assert upload.status_code == 202
        review = client.get(f"/api/v1/ingestions/{upload.json()['data']['batch_id']}", headers=user)
        assert review.status_code == 200
        return [det["bounding_box"] for det in review.json()["data"]["detections"]]
    finally:
        app.dependency_overrides.clear()


def test_gemini_failure_uses_yolo_world_boxes(
    migrated_database: tuple[object, object], storage: LocalObjectStorage
) -> None:
    _, engine = migrated_database
    secondary = FakeDetector(mode="multi_item")
    built: list[int] = []

    def factory() -> FakeDetector:
        built.append(1)
        return secondary

    detector = FallbackDetector(
        FakeDetector(mode="provider_error"), factory, primary_name="gemini", secondary_name="yolo_world"
    )

    boxes = _review_boxes(engine, storage, detector)

    assert len(boxes) == 2
    assert FULL_FRAME not in boxes
    assert built == [1]


def test_without_fallback_a_detector_failure_gives_the_full_frame_box(
    migrated_database: tuple[object, object], storage: LocalObjectStorage
) -> None:
    """Control: the behavior that Phase 5 replaces when the fallback is configured."""
    _, engine = migrated_database

    boxes = _review_boxes(engine, storage, FakeDetector(mode="provider_error"))

    assert boxes == [FULL_FRAME]
