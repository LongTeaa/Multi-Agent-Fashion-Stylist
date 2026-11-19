"""Opt-in live evaluation of the wardrobe digitization pipeline.

Two experiments, both scored against frozen gold sets:

* Attributes: each gold photo goes through the real ingestion service
  (detector -> crop -> vision attributes) in an isolated temporary database and
  object store. The largest proposed detection is scored against the gold labels.
* Localization: each annotated photo goes through the detector and the crop
  policy; boxes are matched one-to-one with the annotated rectangles.

`--live` calls the configured providers and writes a raw-result file that holds
provider outputs only (no image bytes, no secrets). `--score` recomputes every
metric from one or more raw-result files without network access, so reported
numbers are reproducible from the frozen file.

Usage (from the repository root):
    python backend/scripts/evaluate_live_ingestion.py --live --detector yolo_world --out <raw.json>
    python backend/scripts/evaluate_live_ingestion.py --live --detector gemini --localization \
        --out <raw.json>
    python backend/scripts/evaluate_live_ingestion.py --score <raw-a.json> <raw-b.json>
"""
from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402
from app.models.entities import BoundingBox, IngestionDetection, MediaAsset, WardrobeCategory  # noqa: E402
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets  # noqa: E402
from app.services.classifier import classify_scene  # noqa: E402
from app.services.crop_policy import AUTO_CROP_POLICY_VERSION, review_crop_boxes  # noqa: E402
from app.services.ingestion_service import create_ingestion_batch, process_ingestion_batch  # noqa: E402
from app.services.providers import (  # noqa: E402
    DetectionResult, DetectorProtocol, VisionExtractionResult, VisionProviderProtocol,
)
from app.services.upload_validation import validate_image_bytes  # noqa: E402
from app.services.vision_evaluation import (  # noqa: E402
    AttributeGoldItem, judge_attributes, latency_summary, region_coverage, score_attribute_run,
)

RAW_SCHEMA = "live-ingestion-raw-v1"
DEFAULT_GOLD = ROOT / "data" / "fixtures" / "vision_attribute_gold_v1.json"
DEFAULT_IMAGES = ROOT / "data" / "demo-wardrobe"
DEFAULT_LOCALIZATION = ROOT / "data" / "fixtures" / "vision_real_review_v2.json"
DEFAULT_LOCALIZATION_DIR = ROOT / "data" / "private-vision-review"
PROVIDER_LOGGER = "app.services.gemini_provider"
MAX_ERROR_TEXT = 300


# --- Provider recording -----------------------------------------------------

def _error_record(error: BaseException, started: float) -> dict[str, Any]:
    # Keys travel in request headers, never in messages; truncation bounds payload echoes.
    return dict(status="error", error_type=type(error).__name__,
                error_message=str(error)[:MAX_ERROR_TEXT],
                elapsed_seconds=round(perf_counter() - started, 3))


class RecordingDetector:
    """Wraps a detector and records each call; exceptions are recorded and re-raised."""

    def __init__(self, inner: DetectorProtocol) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    def detect(self, image_bytes: bytes) -> DetectionResult:
        started = perf_counter()
        try:
            result = self.inner.detect(image_bytes)
        except BaseException as error:
            self.calls.append(_error_record(error, started))
            raise
        self.calls.append(dict(
            status="ok", elapsed_seconds=round(perf_counter() - started, 3),
            input_kind=result.input_kind.value, input_kind_inferred=result.input_kind_inferred,
            boxes=[dict(box=list(b.box), label=b.label, confidence=b.confidence) for b in result.boxes]))
        return result


class RecordingVision:
    """Wraps a vision provider and records each call; exceptions are recorded and re-raised."""

    def __init__(self, inner: VisionProviderProtocol) -> None:
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    def extract_attributes(
        self, crop_bytes: bytes, spatial_context: dict[str, Any] | None = None,
    ) -> VisionExtractionResult:
        started = perf_counter()
        crop_digest = sha256(crop_bytes).hexdigest()
        try:
            result = self.inner.extract_attributes(crop_bytes, spatial_context=spatial_context)
        except BaseException as error:
            self.calls.append({**_error_record(error, started), "crop_sha256": crop_digest})
            raise
        self.calls.append(dict(
            status="ok", elapsed_seconds=round(perf_counter() - started, 3),
            crop_sha256=crop_digest, attributes=result.attributes,
            field_confidence=result.field_confidence))
        return result


class _ProviderLogCounter(logging.Handler):
    """Counts provider log lines that reveal a model fallback or a rate limit."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.fallbacks = 0
        self.rate_limits = 0

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage().lower()
        self.fallbacks += "falling back" in message
        self.rate_limits += "rate limit" in message or "429" in message


@contextmanager
def count_provider_events() -> Iterator[_ProviderLogCounter]:
    handler = _ProviderLogCounter()
    logger = logging.getLogger(PROVIDER_LOGGER)
    logger.addHandler(handler)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


# --- Isolated environment ---------------------------------------------------

@contextmanager
def isolated_environment() -> Iterator[tuple[Session, LocalObjectStorage]]:
    """Migrated temporary SQLite database and local store; the configured ones are never used."""
    with TemporaryDirectory(prefix="live-ingestion-") as temporary:
        root = Path(temporary)
        url = f"sqlite:///{(root / 'evaluation.db').as_posix()}"
        previous_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = url  # migrations/env.py reads Settings, not alembic.ini
        get_settings.cache_clear()
        try:
            command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
        finally:
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
            get_settings.cache_clear()
        engine = create_database_engine(url)
        storage = LocalObjectStorage(root / "storage", StorageBuckets.from_settings(get_settings()))
        try:
            with Session(engine) as session:
                yield session, storage
        finally:
            engine.dispose()


# --- Experiments --------------------------------------------------------------

def _area(box: BoundingBox | list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def run_attribute_cases(
    cases: list[tuple[str, str, bytes]], detector: DetectorProtocol, vision: VisionProviderProtocol,
) -> list[dict[str, Any]]:
    """Run each (id, file name, bytes) photo through ingestion as its own batch."""
    results: list[dict[str, Any]] = []
    user_id = str(uuid4())
    with isolated_environment() as (session, storage):
        for case_id, file_name, raw in cases:
            recording_detector, recording_vision = RecordingDetector(detector), RecordingVision(vision)
            started = perf_counter()
            with count_provider_events() as events:
                try:
                    batch = create_ingestion_batch(session=session, storage=storage, user_id=user_id,
                                                   raw_files=[(file_name, raw)])
                    batch = process_ingestion_batch(
                        session=session, storage=storage, detector=recording_detector,
                        vision_provider=recording_vision, batch_id=batch.id, user_id=user_id)
                except Exception as error:  # an ingestion failure is a result, not a crash
                    results.append(dict(id=case_id, status="ingestion_error",
                                        **{k: v for k, v in _error_record(error, started).items()
                                           if k != "status"},
                                        detector_calls=recording_detector.calls,
                                        vision_calls=recording_vision.calls))
                    print(f"{case_id}: ingestion_error", flush=True)
                    continue
            detections = session.exec(select(IngestionDetection).where(
                IngestionDetection.ingestion_batch_id == batch.id)).all()
            rows = []
            for d in detections:
                crop = session.get(MediaAsset, d.crop_media_asset_id)
                rows.append(dict(box=list(d.bounding_box),
                                 raw_box=list(d.raw_bounding_box) if d.raw_bounding_box else None,
                                 crop_sha256=crop.sha256 if crop else None,
                                 proposed_attributes=d.proposed_attributes))
            primary = max(range(len(rows)), key=lambda i: _area(rows[i]["box"])) if rows else None
            results.append(dict(
                id=case_id, status="ok", elapsed_seconds=round(perf_counter() - started, 3),
                batch_status=str(batch.status.value if hasattr(batch.status, "value") else batch.status),
                batch_warnings=list(batch.quality_warnings or []),
                detector_calls=recording_detector.calls, vision_calls=recording_vision.calls,
                detections=rows, primary_detection_index=primary,
                provider_fallback_events=events.fallbacks, provider_rate_limit_events=events.rate_limits))
            print(f"{case_id}: ok ({len(rows)} detection(s))", flush=True)
    return results


class LocalizationRegion(BaseModel):
    category: WardrobeCategory
    box: BoundingBox


class LocalizationCase(BaseModel):
    id: str
    file: str
    sha256: str
    regions: list[LocalizationRegion]
    expected_box_count: int | None


class LocalizationDataset(BaseModel):
    dataset_version: str
    annotation_kind: str
    iou_threshold: float
    cases: list[LocalizationCase]


def run_localization_cases(
    cases: list[tuple[LocalizationCase, bytes]], detector: DetectorProtocol,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case, raw in cases:
        recording = RecordingDetector(detector)
        # Same bytes the upload path stores: EXIF orientation applied, metadata removed.
        # Annotations are drawn on the upright image, as browsers display it.
        upright = validate_image_bytes(raw).raw_bytes
        started = perf_counter()
        try:
            detected = classify_scene(detector=recording, image_bytes=upright)
            effective = review_crop_boxes(detected)
        except Exception as error:
            results.append(dict(id=case.id, **_error_record(error, started)))
            print(f"{case.id}: error", flush=True)
            continue
        results.append(dict(
            id=case.id, status="ok", elapsed_seconds=round(perf_counter() - started, 3),
            input_kind=detected.input_kind.value,
            raw_boxes=[dict(box=list(b.box), label=b.label, confidence=b.confidence) for b in detected.boxes],
            boxes=[dict(box=list(b.box), label=b.label, confidence=b.confidence) for b in effective]))
        print(f"{case.id}: ok ({len(effective)} box(es))", flush=True)
    return results


# --- Scoring -------------------------------------------------------------------

def _load_gold(path: Path) -> list[AttributeGoldItem]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [AttributeGoldItem.model_validate(item) for item in data["items"]]


def score_attributes(raw: dict[str, Any], gold: list[AttributeGoldItem]) -> dict[str, Any]:
    by_id = {row["id"]: row for row in raw.get("attribute_results", [])}
    verdicts: dict[str, dict[str, Any] | None] = {}
    single_detection = full_frame = detector_errors = vision_errors = missing = 0
    fallbacks = rate_limits = 0
    latencies: list[float] = []
    for item in gold:
        row = by_id.get(item.id)
        if row is None or row.get("status") != "ok":
            missing += row is None
            verdicts[item.id] = None
            continue
        latencies.append(row["elapsed_seconds"])
        fallbacks += row.get("provider_fallback_events", 0)
        rate_limits += row.get("provider_rate_limit_events", 0)
        detector_errors += any(c["status"] != "ok" for c in row["detector_calls"])
        vision_errors += any(c["status"] != "ok" for c in row["vision_calls"])
        detections = row["detections"]
        single_detection += len(detections) == 1
        full_frame += any(_area(d["box"]) >= 0.999 for d in detections)
        index = row.get("primary_detection_index")
        if index is None:
            verdicts[item.id] = None
            continue
        primary_digest = detections[index].get("crop_sha256")
        primary_crop_failed = not any(
            c["status"] == "ok" and c.get("crop_sha256") == primary_digest for c in row["vision_calls"])
        verdicts[item.id] = None if primary_crop_failed else judge_attributes(
            item, detections[index]["proposed_attributes"])
    total = len(gold)
    return dict(
        images=total, not_run=missing,
        completed=sum(1 for i in gold if by_id.get(i.id, {}).get("status") == "ok"),
        images_with_detector_error=detector_errors, images_with_vision_error=vision_errors,
        provider_model_fallback_events=fallbacks, provider_rate_limit_events=rate_limits,
        exactly_one_detection=dict(count=single_detection, total=total),
        full_frame_box=dict(count=full_frame, total=total),
        latency_seconds=latency_summary(latencies),
        owner_reviewed_gold_items=sum(1 for i in gold if i.owner_reviewed),
        metrics=score_attribute_run(gold, verdicts),
        per_item={k: (None if v is None else {**{f: v.get(f) for f in (
            "category", "item_group", "garment_type", "primary_color", "pattern", "material",
            "formality_error")}, "normalized": v["normalized"]}) for k, v in verdicts.items()},
    )


def score_localization(raw: dict[str, Any], dataset: LocalizationDataset) -> dict[str, Any]:
    by_id = {row["id"]: row for row in raw.get("localization_results", [])}
    expected = matched = count_cases = count_pass = errors = 0
    latencies: list[float] = []
    per_case: dict[str, Any] = {}
    for case in dataset.cases:
        row = by_id.get(case.id)
        expected += len(case.regions)
        if case.expected_box_count is not None:
            count_cases += 1
        if row is None or row.get("status") != "ok":
            errors += row is not None
            per_case[case.id] = dict(status=row.get("status") if row else "not_run")
            continue
        latencies.append(row["elapsed_seconds"])
        boxes = [tuple(b["box"]) for b in row["boxes"]]
        coverage = region_coverage([r.box for r in case.regions], boxes,  # type: ignore[misc]
                                   dataset.iou_threshold, min_retention=0.9)
        matched += int(coverage["matched_regions"])
        passed = case.expected_box_count is not None and len(boxes) == case.expected_box_count
        count_pass += passed
        per_case[case.id] = dict(status="ok", **coverage,
                                 count_pass=passed if case.expected_box_count is not None else None)
    return dict(
        dataset_version=dataset.dataset_version, cases=len(dataset.cases), provider_errors=errors,
        matched_regions=matched, expected_regions=expected,
        region_recall=round(matched / expected, 4) if expected else None,
        count_pass=dict(count=count_pass, total=count_cases),
        latency_seconds=latency_summary(latencies), per_case=per_case,
        match_rule=f"one-to-one, IoU >= {dataset.iou_threshold}, retention >= 0.9")


def _percent(rate: dict[str, Any]) -> str:
    value = rate.get("accuracy")
    return "n/a" if value is None else f"{value * 100:.1f}% ({rate['correct']}/{rate['total']})"


def render_markdown(scores: list[dict[str, Any]]) -> str:
    lines = ["| Metric | " + " | ".join(s["label"] for s in scores) + " |",
             "| :--- |" + " :--- |" * len(scores)]
    rows = [("Category", "category"), ("Category (strict)", "category_strict"),
            ("Garment group", "item_group"), ("Garment type", "garment_type"),
            ("Primary color", "primary_color"), ("Pattern", "pattern"),
            ("Solid vs patterned", "pattern_solid_vs_patterned"), ("Material (plausible)", "material"),
            ("Formality exact", "formality_exact"), ("Formality within 1", "formality_within_one")]
    for title, key in rows:
        cells = [_percent(s["attributes"]["metrics"][key]) if s.get("attributes") else "-" for s in scores]
        lines.append(f"| {title} | " + " | ".join(cells) + " |")
    extra = [("Images not run", lambda a: f"{a['not_run']}/{a['images']}"),
             ("Formality MAE", lambda a: str(a["metrics"]["formality_mae"])),
             ("Exactly one detection", lambda a: f"{a['exactly_one_detection']['count']}/{a['images']}"),
             ("Full-frame box", lambda a: f"{a['full_frame_box']['count']}/{a['images']}"),
             ("Images with vision error", lambda a: str(a["images_with_vision_error"])),
             ("Model fallback events", lambda a: str(a["provider_model_fallback_events"])),
             ("Median latency (s)", lambda a: str(a["latency_seconds"]["median"]))]
    for title, fn in extra:
        cells = [fn(s["attributes"]) if s.get("attributes") else "-" for s in scores]
        lines.append(f"| {title} | " + " | ".join(cells) + " |")
    for s in scores:
        loc = s.get("localization")
        if loc:
            lines.append(f"\nLocalization {s['label']}: {loc['matched_regions']}/{loc['expected_regions']} regions "
                         f"({loc['match_rule']}), count pass {loc['count_pass']['count']}/"
                         f"{loc['count_pass']['total']}, provider errors {loc['provider_errors']}.")
    return "\n".join(lines)


# --- Entry point -------------------------------------------------------------------

def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _read_verified(directory: Path, file_name: str, expected_sha256: str) -> bytes:
    path = (directory / file_name).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise SystemExit(f"Manifest file escapes its directory: {file_name}")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise SystemExit(f"Digest mismatch: {file_name}")
    return raw


def build_detector(name: str) -> tuple[DetectorProtocol, str]:
    settings = get_settings()
    if name == "yolo_world":
        from app.core.dependencies import get_yolo_world_detector
        return get_yolo_world_detector(settings), Path(settings.yolo_world_model_path).name
    from app.core.dependencies import get_gemini_key_pool
    from app.services.gemini_provider import GeminiDetector
    if not settings.get_gemini_api_keys():
        raise SystemExit("The Gemini detector needs a configured Gemini API key.")
    pool = get_gemini_key_pool(settings)
    model = settings.get_detector_model()
    return GeminiDetector(api_key=pool.keys[0], model=model,
                          timeout_seconds=float(settings.vision_timeout_seconds), key_pool=pool), model


def run_live(args: argparse.Namespace) -> int:
    from app.core.dependencies import get_vision_provider
    settings = get_settings()
    if settings.vision_provider != "gemini":
        raise SystemExit("Live evaluation requires VISION_PROVIDER=gemini.")
    detector, detector_model = build_detector(args.detector)
    raw: dict[str, Any] = dict(
        schema=RAW_SCHEMA, run_at=datetime.now(timezone.utc).isoformat(), detector=args.detector,
        detector_model=detector_model, vision_model=settings.get_vision_model(),
        vision_fallback_model=settings.vision_fallback_model or None, crop_policy=AUTO_CROP_POLICY_VERSION)
    if not args.skip_attributes:
        gold_data = json.loads(args.gold.read_text(encoding="utf-8"))
        gold = [AttributeGoldItem.model_validate(item) for item in gold_data["items"]]
        if args.limit:
            gold = gold[: args.limit]
        cases = [(i.id, i.file, _read_verified(args.image_dir, i.file, i.sha256)) for i in gold]
        raw.update(gold_dataset_version=gold_data["dataset_version"], gold_sha256=_digest(args.gold),
                   gold_review_status=gold_data.get("review_status"),
                   attribute_results=run_attribute_cases(cases, detector, get_vision_provider()))
    if args.localization:
        dataset = LocalizationDataset.model_validate_json(args.localization_manifest.read_text(encoding="utf-8"))
        loc_cases = [(c, _read_verified(args.localization_dir, c.file, c.sha256)) for c in dataset.cases]
        raw.update(localization_dataset_version=dataset.dataset_version,
                   localization_sha256=_digest(args.localization_manifest),
                   localization_results=run_localization_cases(loc_cases, detector))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Raw results: {args.out}", flush=True)
    return 0


def run_score(args: argparse.Namespace) -> int:
    scores: list[dict[str, Any]] = []
    for path in args.score:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema") != RAW_SCHEMA:
            raise SystemExit(f"Unsupported raw-result schema in {path}")
        label = (f"{raw['detector']} + {raw['vision_model']}" if "attribute_results" in raw
                 else f"{raw['detector']} ({raw['detector_model']})")
        entry: dict[str, Any] = dict(label=label, file=str(path), run_at=raw["run_at"])
        if "attribute_results" in raw:
            if raw.get("gold_sha256") != _digest(args.gold):
                print(f"Note: {path.name} was run against a different gold file digest; "
                      "scoring uses the current gold labels.", flush=True)
            entry["attributes"] = score_attributes(raw, _load_gold(args.gold))
        if "localization_results" in raw:
            dataset = LocalizationDataset.model_validate_json(
                args.localization_manifest.read_text(encoding="utf-8"))
            entry["localization"] = score_localization(raw, dataset)
        scores.append(entry)
    print(render_markdown(scores))
    if args.metrics_out:
        args.metrics_out.write_text(json.dumps(scores, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="Call the configured providers (sends photos to Gemini)")
    mode.add_argument("--score", nargs="+", type=Path, help="Score saved raw-result files offline")
    parser.add_argument("--detector", choices=("yolo_world", "gemini"))
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--skip-attributes", action="store_true")
    parser.add_argument("--localization", action="store_true", help="Also run the localization set")
    parser.add_argument("--localization-manifest", type=Path, default=DEFAULT_LOCALIZATION)
    parser.add_argument("--localization-dir", type=Path, default=DEFAULT_LOCALIZATION_DIR)
    parser.add_argument("--limit", type=int, default=0, help="Only the first N gold items (smoke runs)")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--metrics-out", type=Path)
    args = parser.parse_args(argv)
    if args.live and (args.detector is None or args.out is None):
        parser.error("--live requires --detector and --out")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run_live(args) if args.live else run_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
