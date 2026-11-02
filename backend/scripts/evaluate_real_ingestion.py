"""Replay annotated real pixels in isolation; optionally measure live localization.

Private source files and run artifacts are deliberately excluded from Git. This
does not modify the configured database or upload anything unless --live is set.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from alembic import command
from alembic.config import Config
from PIL import Image
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import create_database_engine
from app.models.entities import BoundingBox, InputKind, MediaAsset, WardrobeCategory, WardrobeItem
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.schemas.ingestion import DetectionConfirmationItem
from app.services.crop_engine import crop_item_and_generate_thumbnail
from app.services.gemini_provider import GeminiDetector
from app.services.ingestion_service import (
    confirm_ingestion_batch, create_ingestion_batch, get_batch_review,
    process_ingestion_batch, update_detection_crop,
)
from app.services.providers import BoundingBoxDetection, DetectionResult, VisionExtractionResult
from app.services.vision_evaluation import region_coverage


class Region(BaseModel):
    category: WardrobeCategory
    box: BoundingBox


class Case(BaseModel):
    id: str
    file: str
    sha256: str
    regions: list[Region]
    expected_box_count: int | None


class Dataset(BaseModel):
    dataset_version: str
    annotation_kind: str
    iou_threshold: float
    cases: list[Case]


class AnnotatedReplay:
    """Human annotations, not AI; exercises actual pipeline with real source pixels."""

    def __init__(self, cases: list[tuple[Case, bytes]]) -> None:
        self.sources = {sha256(raw).hexdigest(): case for case, raw in cases}
        self.crops: dict[str, WardrobeCategory] = {}
        for case, raw in cases:
            for region in case.regions:
                crop = crop_item_and_generate_thumbnail(raw, region.box)
                self.crops[crop.crop_sha256] = region.category

    def detect(self, image_bytes: bytes) -> DetectionResult:
        case = self.sources[sha256(image_bytes).hexdigest()]
        return DetectionResult(
            input_kind=InputKind.SINGLE_ITEM if len(case.regions) == 1 else InputKind.MULTI_ITEM,
            boxes=[BoundingBoxDetection(box=r.box, label=r.category.value) for r in case.regions],
        )

    def extract_attributes(self, crop_bytes: bytes) -> VisionExtractionResult:
        category = self.crops[sha256(crop_bytes).hexdigest()]
        attrs = dict(category=category.value, sub_category=category.value, primary_color="unknown",
                     pattern="unknown", material="unknown", style="casual", fit="regular",
                     formality_level=3, season=[], weather_suitability=[], functional_flags=[])
        return VisionExtractionResult(attributes=attrs, field_confidence={})


def replay_pipeline(cases: list[tuple[Case, bytes]], output: Path) -> dict[str, object]:
    with TemporaryDirectory(prefix="real-ingestion-") as temporary:
        root = Path(temporary)
        config = Config(str(BACKEND / "alembic.ini"))
        url = f"sqlite:///{(root / 'review.db').as_posix()}"
        # migrations/env.py deliberately reads Settings instead of alembic.ini.
        # Override its environment explicitly so the configured DB is never used.
        previous_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()
        try:
            command.upgrade(config, "head")
        finally:
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
            get_settings.cache_clear()
        engine = create_database_engine(url)
        storage = LocalObjectStorage(root / "storage", StorageBuckets(
            wardrobe="wardrobe-private", thumbnails="wardrobe-thumbnails", tryon="tryon-private"))
        provider = AnnotatedReplay(cases)
        user = str(uuid4())
        try:
            with Session(engine) as session:
                batch = create_ingestion_batch(session=session, storage=storage, user_id=user,
                    raw_files=[(case.file, raw) for case, raw in cases])
                process_ingestion_batch(session=session, storage=storage, user_id=user, batch_id=batch.id,
                                        detector=provider, vision_provider=provider)
                review = get_batch_review(session=session, user_id=user, batch_id=batch.id)
                assert len(review.source_images) == len(cases)
                assert len(review.detections) == sum(len(c.regions) for c, _ in cases)
                assert session.exec(select(WardrobeItem)).all() == []
                original_bytes = {}
                for source in review.source_images:
                    asset = session.get(MediaAsset, source.media_asset_id)
                    assert asset is not None
                    original_bytes[asset.id] = storage.get_object(
                        user_id=user, bucket=asset.bucket, object_key=asset.object_key)
                expected_hashes = {sha256(raw).hexdigest() for _, raw in cases}
                assert {sha256(raw).hexdigest() for raw in original_bytes.values()} == expected_hashes
                for index, detection in enumerate(review.detections):
                    raw = original_bytes[detection.source_media_asset_id]
                    expected = crop_item_and_generate_thumbnail(raw, detection.bounding_box)
                    asset = session.get(MediaAsset, detection.crop_url.rsplit("/", 1)[-1])
                    assert asset is not None
                    actual = storage.get_object(user_id=user, bucket=asset.bucket, object_key=asset.object_key)
                    assert sha256(actual).hexdigest() == expected.crop_sha256
                    (output / f"replay-crop-{index + 1:02}.png").write_bytes(actual)
                # Correct a crop from a later photo, then reload and explicitly confirm.
                later_source = review.source_images[-1].media_asset_id
                target = next(d for d in review.detections if d.source_media_asset_id == later_source)
                update_detection_crop(session=session, storage=storage, user_id=user, batch_id=batch.id,
                    detection_id=target.detection_id, bounding_box=(0, 0, 1, 1))
                reloaded = get_batch_review(session=session, user_id=user, batch_id=batch.id)
                changed = next(d for d in reloaded.detections if d.detection_id == target.detection_id)
                assert tuple(changed.bounding_box) == (0, 0, 1, 1)
                crop_asset = session.get(MediaAsset, changed.crop_url.rsplit("/", 1)[-1])
                assert crop_asset is not None
                with Image.open(BytesIO(original_bytes[later_source])) as original:
                    assert (crop_asset.width, crop_asset.height) == original.size
                confirmations = [DetectionConfirmationItem(detection_id=d.detection_id) for d in reloaded.detections]
                ids = confirm_ingestion_batch(session=session, user_id=user, batch_id=batch.id,
                                               confirmations=confirmations)
                assert len(ids) == len(reloaded.detections)
                assert set(confirm_ingestion_batch(session=session, user_id=user, batch_id=batch.id,
                                                    confirmations=confirmations)) == set(ids)
                return dict(mode="annotated_real_pixel_replay_not_ai", status="passed",
                            sources=len(cases), crops=len(ids), later_photo_edit_reload_confirm=True,
                            no_item_before_confirmation=True, idempotent_confirmation=True)
        finally:
            engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ROOT / "data/private-vision-review")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/fixtures/vision_real_review_v1.json")
    parser.add_argument("--live", action="store_true", help="Send private images to the configured Gemini detector")
    parser.add_argument("--case", dest="case_ids", action="append",
                        help="Evaluate only this case live (repeatable); offline replay still covers all sources")
    args = parser.parse_args()
    dataset = Dataset.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    if args.case_ids and (not args.live or set(args.case_ids) - {case.id for case in dataset.cases}):
        parser.error("--case requires --live and case IDs present in the manifest")
    cases = []
    for case in dataset.cases:
        path = (args.input_dir / case.file).resolve()
        if not path.is_relative_to(args.input_dir.resolve()):
            parser.error("Manifest source must stay inside input directory")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != case.sha256:
            parser.error(f"Source digest mismatch: {case.id}")
        cases.append((case, raw))
    output = args.input_dir / datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%S%fZ")
    output.mkdir()
    report: dict[str, object] = dict(dataset_version=dataset.dataset_version,
        annotation_kind=dataset.annotation_kind, run_at=datetime.now(timezone.utc).isoformat(),
        replay=replay_pipeline(cases, output), live_provider_run=args.live)
    failures = 0
    if args.live:
        settings = get_settings()
        if not settings.gemini_api_key or not settings.vision_model or settings.vision_provider != "gemini":
            parser.error("Live evaluation requires configured Gemini vision provider, key and model")
        detector = GeminiDetector(settings.gemini_api_key, settings.vision_model,
                                  timeout_seconds=30, max_retries=0)
        rows: list[dict[str, object]] = []
        selected_cases = [(case, raw) for case, raw in cases if not args.case_ids or case.id in args.case_ids]
        for case_index, (case, raw) in enumerate(selected_cases, 1):
            if failures >= 2:
                rows.append(dict(id=case.id, status="skipped_after_provider_failures"))
                continue
            start = perf_counter()
            try:
                detected = detector.detect(raw)
                metrics = region_coverage([r.box for r in case.regions], [b.box for b in detected.boxes],
                                          dataset.iou_threshold, min_retention=0.9)
                crops = []
                for index, box in enumerate(detected.boxes, 1):
                    crop = crop_item_and_generate_thumbnail(raw, box.box)
                    file = f"live-{case_index:02}-{index:02}.png"
                    (output / file).write_bytes(crop.crop_bytes)
                    crops.append(dict(file=file, sha256=crop.crop_sha256,
                                      width=crop.crop_width, height=crop.crop_height))
                rows.append(dict(id=case.id, status="available", elapsed_seconds=round(perf_counter()-start, 3),
                    crops=crops,
                    metrics=metrics, count_pass=(len(detected.boxes) == case.expected_box_count)
                    if case.expected_box_count is not None else None,
                    boxes=[dict(box=b.box, label=b.label) for b in detected.boxes]))
                failures = 0
            except Exception as error:
                failures += 1
                rows.append(dict(id=case.id, status="unavailable", error_type=type(error).__name__,
                                 error_message=str(error),
                                 elapsed_seconds=round(perf_counter()-start, 3)))
            print(f"{case.id}: {rows[-1]['status']}", flush=True)
        available = [r for r in rows if r["status"] == "available"]
        report["live"] = dict(model=settings.vision_model, results=rows,
            adapter_contract="gemini-native-yxyx1000-v1", manifest_sha256=sha256(args.manifest.read_bytes()).hexdigest(),
            selected_case_ids=[case.id for case, _ in selected_cases],
            available_cases=len(available), total_cases=len(selected_cases),
            status="complete" if len(available) == len(selected_cases) else "incomplete_provider_failures",
            semantic_attribute_accuracy="not_measured")
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report: {output / 'report.json'}", flush=True)
    return 2 if args.live and report["live"]["status"] != "complete" else 0


if __name__ == "__main__":
    raise SystemExit(main())
