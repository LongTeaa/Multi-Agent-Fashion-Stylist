from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.core.dependencies import get_db_session, get_detector, get_vision_provider, get_object_storage
from app.main import app
from app.models.entities import WardrobeItem
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider
from app.services.providers import DetectionResult


@pytest.mark.parametrize("count", [1, 2, 10])
def test_each_uploaded_photo_survives_review_reload_and_partial_provider_failure(
    migrated_database: tuple[Config, Engine], tmp_path: Path, count: int,
) -> None:
    _, engine = migrated_database
    storage = LocalObjectStorage(tmp_path / "s", StorageBuckets(
        wardrobe="wardrobe-private", thumbnails="wardrobe-thumbnails", tryon="tryon-private"))
    user = str(uuid4())
    files = []
    colors = [(20 + index * 17, 60, 120) for index in range(count)]
    for index, color in enumerate(colors):
        buffer = BytesIO()
        Image.new("RGB", (160, 200), color).save(buffer, format="PNG")
        files.append(("images[]", (f"photo-{index}.png", buffer.getvalue(), "image/png")))

    class Detector(FakeDetector):
        calls = 0
        def detect(self, image_bytes: bytes) -> DetectionResult:
            self.calls += 1
            if count > 1 and self.calls == 2:
                raise TimeoutError("controlled second-photo failure")
            return super().detect(image_bytes)

    def db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_detector] = lambda: Detector(mode="single_item")
    app.dependency_overrides[get_vision_provider] = lambda: FakeVisionProvider()
    app.dependency_overrides[get_object_storage] = lambda: storage
    with TestClient(app) as client:
        headers = {"X-User-Id": user}
        uploaded = client.post("/api/v1/ingestions", headers=headers, files=files)
        assert uploaded.status_code == 202, uploaded.text
        url = f"/api/v1/ingestions/{uploaded.json()['data']['batch_id']}"
        review = client.get(url, headers=headers).json()["data"]
        assert review["status"] == "needs_review"
        assert len(review["source_images"]) == len(review["detections"]) == count
        assert {d["source_media_asset_id"] for d in review["detections"]} == {s["media_asset_id"] for s in review["source_images"]}
        seen = set()
        for source in review["source_images"]:
            with Image.open(BytesIO(client.get(source["media_url"], headers=headers).content)) as image:
                seen.add(image.convert("RGB").getpixel((0, 0)))
        assert seen == set(colors)
        assert client.get(url, headers=headers).json()["data"] == review
        if count > 1:
            assert review["quality_warnings"]
            assert any(d["raw_bounding_box"] is None for d in review["detections"])
        with Session(engine) as session:
            assert session.exec(select(WardrobeItem)).all() == []
        confirmed = client.post(url + "/confirm", headers=headers, json={"confirmations": [
            {"detection_id": d["detection_id"], "accepted": True} for d in review["detections"]]})
        assert confirmed.status_code == 200, confirmed.text
        assert len(confirmed.json()["data"]["wardrobe_item_ids"]) == count
