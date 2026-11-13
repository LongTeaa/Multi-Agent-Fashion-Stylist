from __future__ import annotations

import json
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.models.entities import IngestionDetection, IngestionStatus, InputKind
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.gemini_key_pool import GeminiKeyPool
from app.services.gemini_provider import GeminiVisionProvider
from app.services.ingestion_service import create_ingestion_batch, process_ingestion_batch
from app.services.providers import (
    BoundingBoxDetection,
    DetectionResult,
    VisionExtractionResult,
)
from app.services.yolo_world_detector import resolve_yolo_model_path


def _create_test_image(width: int = 400, height: int = 400) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (width, height), (200, 180, 160)).save(buf, format="JPEG")
    return buf.getvalue()


class _FourBoxDetector:
    """Deterministic fake detector returning 4 non-overlapping fashion boxes."""

    def __init__(self, count: int = 4) -> None:
        self._boxes = [
            BoundingBoxDetection(box=(0.05, 0.05, 0.45, 0.45), label="top", confidence=0.96),
            BoundingBoxDetection(box=(0.55, 0.05, 0.95, 0.45), label="bottom", confidence=0.95),
            BoundingBoxDetection(box=(0.05, 0.55, 0.45, 0.95), label="footwear", confidence=0.94),
            BoundingBoxDetection(box=(0.55, 0.55, 0.95, 0.95), label="outerwear", confidence=0.93),
        ][:count]

    def detect(self, image_bytes: bytes) -> DetectionResult:
        return DetectionResult(
            input_kind=InputKind.MULTI_ITEM,
            boxes=list(self._boxes),
            quality_warnings=[],
        )


class _SlowFakeVisionProvider:
    """Fake vision provider simulating network latency and distinct attributes per crop."""

    _ATTRS_BY_LABEL: dict[str, tuple[str, str]] = {
        "top": ("top", "white"),
        "bottom": ("bottom", "blue"),
        "footwear": ("footwear", "black"),
        "outerwear": ("outerwear", "beige"),
    }

    def __init__(self, delay_seconds: float = 0.25) -> None:
        self.delay_seconds = delay_seconds

    def extract_attributes(
        self,
        crop_bytes: bytes,
        spatial_context: dict[str, Any] | None = None,
    ) -> VisionExtractionResult:
        assert spatial_context is not None
        time.sleep(self.delay_seconds)
        label = str(spatial_context.get("detected_label", "top"))
        category, color = self._ATTRS_BY_LABEL.get(label, ("top", "gray"))
        return VisionExtractionResult(
            attributes={
                "category": category,
                "primary_color": color,
                "style": "casual",
                "comfort_level": 4,
                "silhouette_level": 3,
                "length": "hip",
                "functional_flags": ["movement"],
            },
            field_confidence={
                "category": 0.95,
                "primary_color": 0.92,
                "comfort_level": 0.90,
                "silhouette_level": 0.88,
                "length": 0.90,
            },
            quality_warnings=[],
        )


def test_parallel_vision_extraction_speedup_and_deterministic_order(
    migrated_database: tuple[object, Engine],
    tmp_path: Path,
) -> None:
    """Extract 4 crops concurrently in < 0.75s while keeping deterministic order and isolation."""
    _, engine = migrated_database
    storage = LocalObjectStorage(
        root=tmp_path / "storage",
        buckets=StorageBuckets(
            wardrobe="wardrobe-private",
            thumbnails="wardrobe-thumbnails",
            tryon="tryon-private",
        ),
    )
    user_id = str(uuid4())

    with Session(engine) as session:
        batch = create_ingestion_batch(
            session=session,
            storage=storage,
            user_id=user_id,
            raw_files=[("multi.jpg", _create_test_image())],
        )
        batch_id = batch.id

    detector = _FourBoxDetector(count=4)
    vision_provider = _SlowFakeVisionProvider(delay_seconds=0.25)

    start = time.perf_counter()
    with Session(engine) as session:
        result_batch = process_ingestion_batch(
            session=session,
            storage=storage,
            detector=detector,
            vision_provider=vision_provider,
            batch_id=batch_id,
            user_id=user_id,
        )
    elapsed = time.perf_counter() - start

    assert result_batch.status == IngestionStatus.NEEDS_REVIEW
    # 4 calls x 0.25s sequentially >= 1.0s; parallel must finish well under 0.75s
    assert elapsed < 0.75, f"Expected parallel execution < 0.75s, got {elapsed:.3f}s"

    with Session(engine) as session:
        detections = session.exec(
            select(IngestionDetection).where(IngestionDetection.ingestion_batch_id == batch_id)
        ).all()

    assert len(detections) == 4
    expected = [
        ((0.05, 0.05, 0.45, 0.45), "top", "white"),
        ((0.55, 0.05, 0.95, 0.45), "bottom", "blue"),
        ((0.05, 0.55, 0.45, 0.95), "footwear", "black"),
        ((0.55, 0.55, 0.95, 0.95), "outerwear", "beige"),
    ]
    for det, (exp_box, exp_cat, exp_color) in zip(detections, expected, strict=True):
        assert tuple(det.bounding_box) == pytest.approx(exp_box, abs=1e-4)
        assert det.proposed_attributes["category"] == exp_cat
        assert det.proposed_attributes["primary_color"] == exp_color


def test_parallel_vision_extraction_rotates_gemini_key_pool(
    migrated_database: tuple[object, Engine],
    tmp_path: Path,
) -> None:
    """Concurrent vision extraction safely rotates across all keys in GeminiKeyPool."""
    _, engine = migrated_database
    storage = LocalObjectStorage(
        root=tmp_path / "storage",
        buckets=StorageBuckets(
            wardrobe="wardrobe-private",
            thumbnails="wardrobe-thumbnails",
            tryon="tryon-private",
        ),
    )
    user_id = str(uuid4())

    with Session(engine) as session:
        batch = create_ingestion_batch(
            session=session,
            storage=storage,
            user_id=user_id,
            raw_files=[("rot.jpg", _create_test_image())],
        )
        batch_id = batch.id

    observed_keys: list[str] = []
    lock = threading.Lock()

    def mock_transport(request: httpx.Request) -> httpx.Response:
        key_val = request.headers.get("x-goog-api-key", "")
        with lock:
            observed_keys.append(key_val)
        return httpx.Response(
            status_code=200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "attributes": {
                                                "category": "top",
                                                "primary_color": "navy",
                                                "style": "casual",
                                                "comfort_level": 4,
                                                "silhouette_level": 3,
                                                "length": "hip",
                                                "functional_flags": [],
                                            },
                                            "field_confidence": {
                                                "category": 0.95,
                                                "primary_color": 0.9,
                                            },
                                            "quality_warnings": [],
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    pool = GeminiKeyPool(
        [SecretStr("key-1"), SecretStr("key-2"), SecretStr("key-3")],
        cooldown_seconds=60.0,
    )
    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    vision_provider = GeminiVisionProvider(
        key_pool=pool,
        model="gemini-1.5-flash",
        client=client,
    )

    with Session(engine) as session:
        result_batch = process_ingestion_batch(
            session=session,
            storage=storage,
            detector=_FourBoxDetector(count=3),
            vision_provider=vision_provider,
            batch_id=batch_id,
            user_id=user_id,
        )

    assert result_batch.status == IngestionStatus.NEEDS_REVIEW
    assert len(observed_keys) == 3
    assert set(observed_keys) == {"key-1", "key-2", "key-3"}


def test_resolve_yolo_model_path_from_repo_root_and_backend_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Resolve relative YOLO model path whether cwd is repo root or backend directory."""
    fake_repo = tmp_path / "repo"
    fake_backend = fake_repo / "backend"
    fake_model = fake_backend / "models" / "yolov8s-worldv2.onnx"
    fake_model.parent.mkdir(parents=True)
    fake_model.write_bytes(b"onnx-weights")

    monkeypatch.setattr("app.services.yolo_world_detector.BACKEND_DIR", fake_backend)

    monkeypatch.chdir(fake_repo)
    resolved_from_root = resolve_yolo_model_path("models/yolov8s-worldv2.onnx")
    assert resolved_from_root.is_file()
    assert resolved_from_root.resolve() == fake_model.resolve()

    monkeypatch.chdir(fake_backend)
    resolved_from_backend = resolve_yolo_model_path("models/yolov8s-worldv2.onnx")
    assert resolved_from_backend.is_file()
    assert resolved_from_backend.resolve() == fake_model.resolve()
