from collections.abc import Iterator
from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import Engine
from sqlmodel import Session

from app.core.dependencies import get_db_session, get_object_storage
from app.main import app
from app.models.entities import InputKind
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.fakes.vision_fakes import FakeVisionProvider
from app.services.ingestion_service import create_ingestion_batch, process_ingestion_batch
from app.services.providers import BoundingBoxDetection, DetectionResult, VisionExtractionResult


def test_auto_margin_matches_review_pixels_and_manual_edit_is_exact(
    migrated_database: tuple[Config, Engine], tmp_path: Path,
) -> None:
    _, engine = migrated_database
    storage = LocalObjectStorage(tmp_path / "storage", StorageBuckets(
        wardrobe="wardrobe-private", thumbnails="wardrobe-thumbnails", tryon="tryon-private"))
    image = Image.new("RGB", (399, 501), "white")
    ImageDraw.Draw(image).rectangle((37, 366, 360, 373), fill="black")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    user = str(uuid4())

    class Detector:
        def detect(self, image_bytes: bytes) -> DetectionResult:
            return DetectionResult(InputKind.SINGLE_ITEM,
                [BoundingBoxDetection((.092, .488, .906, .73), "shoes")])

    class Vision(FakeVisionProvider):
        def extract_attributes(self, crop_bytes: bytes) -> VisionExtractionResult:
            result = super().extract_attributes(crop_bytes)
            return replace(result, attributes={**result.attributes, "category": "footwear", "sub_category": "derby"})

    with Session(engine) as session:
        batch = create_ingestion_batch(session=session, storage=storage, user_id=user,
                                       raw_files=[("shoe.png", buffer.getvalue())])
        process_ingestion_batch(session=session, storage=storage, user_id=user, batch_id=batch.id,
                                detector=Detector(), vision_provider=Vision())
        batch_id = batch.id

    def db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_object_storage] = lambda: storage
    with TestClient(app) as client:
        headers = {"X-User-Id": user}
        url = f"/api/v1/ingestions/{batch_id}"
        detection = client.get(url, headers=headers).json()["data"]["detections"][0]
        assert detection["bounding_box"] == [.072, .468, .926, .75]
        with Image.open(BytesIO(client.get(detection["crop_url"], headers=headers).content)) as crop:
            assert crop.size == (341, 141)
            assert crop.convert("RGB").getpixel((50, 135)) == (0, 0, 0)  # Sole survives.
        edited = client.patch(f"{url}/detections/{detection['detection_id']}/crop", headers=headers,
                              json={"bounding_box": [.092, .488, .906, .73]})
        assert edited.status_code == 200
        selected = edited.json()["data"]["detections"][0]
        assert selected["bounding_box"] == [.092, .488, .906, .73]
        with Image.open(BytesIO(client.get(selected["crop_url"], headers=headers).content)) as crop:
            assert crop.size == (325, 121)  # Explicit user crop gets no hidden margin.
