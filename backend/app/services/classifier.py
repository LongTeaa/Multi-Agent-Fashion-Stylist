from __future__ import annotations

import logging
from sqlmodel import Session

from app.models.entities import IngestionBatch, InputKind
from app.services.providers import DetectionResult, DetectorProtocol

logger = logging.getLogger(__name__)


def classify_scene(
    detector: DetectorProtocol,
    image_bytes: bytes,
    declared_input_kind: InputKind | None = None,
) -> DetectionResult:
    """Classify the clothing scene using the injected DetectorProtocol and optional declared hint."""
    result = detector.detect(image_bytes)

    # If client explicitly declared kind and detector returned unknown, respect user declaration
    resolved_kind = result.input_kind
    if resolved_kind == InputKind.UNKNOWN and declared_input_kind not in (None, InputKind.UNKNOWN):
        resolved_kind = declared_input_kind
    elif resolved_kind == InputKind.UNKNOWN:
        box_count = len(result.boxes)
        if box_count == 1:
            resolved_kind = InputKind.SINGLE_ITEM
        elif box_count > 1:
            resolved_kind = InputKind.MULTI_ITEM
        else:
            resolved_kind = InputKind.CLUTTERED

    return DetectionResult(
        input_kind=resolved_kind,
        boxes=result.boxes,
        quality_warnings=result.quality_warnings,
    )


def update_batch_classification(
    session: Session,
    batch_id: str,
    detection_result: DetectionResult,
) -> IngestionBatch:
    """Update an IngestionBatch with classified input_kind and quality_warnings."""
    batch = session.get(IngestionBatch, batch_id)
    if batch is None:
        raise ValueError(f"Batch with ID '{batch_id}' not found.")

    batch.input_kind = detection_result.input_kind
    if detection_result.quality_warnings:
        # Merge quality warnings without duplicates
        existing = set(batch.quality_warnings)
        for warning in detection_result.quality_warnings:
            if warning not in existing:
                batch.quality_warnings.append(warning)
                existing.add(warning)

    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch
