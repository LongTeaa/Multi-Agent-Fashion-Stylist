from __future__ import annotations

import logging
from sqlmodel import Session

from app.models.entities import IngestionBatch, InputKind
from app.services.providers import DetectionResult, DetectorProtocol

logger = logging.getLogger(__name__)


PERSON_LABELS: frozenset[str] = frozenset(
    {"person", "human", "model", "man", "woman", "boy", "girl"}
)


def _box_contained_or_overlaps(
    inner_box: tuple[float, float, float, float],
    outer_box: tuple[float, float, float, float],
    min_overlap_ratio: float = 0.35,
) -> bool:
    """Calculate if inner_box has significant overlap area with outer_box."""
    ix1, iy1, ix2, iy2 = inner_box
    ox1, oy1, ox2, oy2 = outer_box

    inter_x1 = max(ix1, ox1)
    inter_y1 = max(iy1, oy1)
    inter_x2 = min(ix2, ox2)
    inter_y2 = min(iy2, oy2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    inner_area = max(0.0001, (ix2 - ix1) * (iy2 - iy1))
    return (inter_area / inner_area) >= min_overlap_ratio


def find_primary_wearer(
    person_boxes: list[BoundingBoxDetection],
    garment_boxes: list[BoundingBoxDetection],
) -> tuple[float, float, float, float] | None:
    """Identify the primary wearer from candidate person boxes based on garment containment.
    
    In multi-person or street scenes, bystander boxes may appear larger than the actual wearer.
    The primary wearer is the person containing the highest count of detected garments with
    significant overlap, breaking ties by total overlap ratio and box area.
    """
    if not person_boxes:
        return None
    if not garment_boxes:
        # Fallback to largest person box if no separate garments are detected
        largest = max(
            person_boxes,
            key=lambda p: (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]),
        )
        return largest.box

    best_box: tuple[float, float, float, float] | None = None
    best_score: tuple[int, float, float] = (-1, -1.0, -1.0)

    for p in person_boxes:
        p_box = p.box
        p_area = (p_box[2] - p_box[0]) * (p_box[3] - p_box[1])
        contained_count = 0
        total_overlap_ratio = 0.0

        for g in garment_boxes:
            ix1, iy1, ix2, iy2 = g.box
            px1, py1, px2, py2 = p_box

            inter_x1 = max(ix1, px1)
            inter_y1 = max(iy1, py1)
            inter_x2 = min(ix2, px2)
            inter_y2 = min(iy2, py2)

            inter_w = max(0.0, inter_x2 - inter_x1)
            inter_h = max(0.0, inter_y2 - inter_y1)
            inter_area = inter_w * inter_h
            g_area = max(0.0001, (ix2 - ix1) * (iy2 - iy1))
            ratio = inter_area / g_area

            if ratio >= 0.35:
                contained_count += 1
                total_overlap_ratio += ratio

        score = (contained_count, total_overlap_ratio, p_area)
        if contained_count > 0 and score > best_score:
            best_score = score
            best_box = p_box

    # Fallback to largest person if no person overlaps with garments >= 0.35
    if best_box is None:
        largest = max(
            person_boxes,
            key=lambda p: (p.box[2] - p.box[0]) * (p.box[3] - p.box[1]),
        )
        best_box = largest.box

    return best_box


def classify_scene(
    detector: DetectorProtocol,
    image_bytes: bytes,
    declared_input_kind: InputKind | None = None,
) -> DetectionResult:
    """Classify the clothing scene using the injected DetectorProtocol and optional declared hint."""
    result = detector.detect(image_bytes)

    # 1. Separate person reference boxes from individual garment boxes
    person_boxes: list[BoundingBoxDetection] = []
    garment_boxes: list[BoundingBoxDetection] = []

    for b in result.boxes:
        if b.label.strip().lower() in PERSON_LABELS:
            person_boxes.append(b)
        else:
            garment_boxes.append(b)

    # 2. Determine reference person_box (primary wearer)
    detected_person_box: tuple[float, float, float, float] | None = result.person_box
    if detected_person_box is None and person_boxes:
        detected_person_box = find_primary_wearer(person_boxes, garment_boxes)

    # 3. Check if garments are worn on the detected person
    has_overlapping_garment = False
    if detected_person_box is not None and garment_boxes:
        has_overlapping_garment = any(
            _box_contained_or_overlaps(g.box, detected_person_box) for g in garment_boxes
        )

    # 4. Resolve scene kind
    resolved_kind = result.input_kind
    if resolved_kind == InputKind.UNKNOWN and declared_input_kind not in (None, InputKind.UNKNOWN):
        resolved_kind = declared_input_kind
    elif resolved_kind == InputKind.UNKNOWN:
        if detected_person_box is not None and (has_overlapping_garment or not garment_boxes):
            resolved_kind = InputKind.WORN_OUTFIT
        else:
            box_count = len(garment_boxes)
            if box_count == 1:
                resolved_kind = InputKind.SINGLE_ITEM
            elif box_count > 1:
                resolved_kind = InputKind.MULTI_ITEM
            else:
                resolved_kind = InputKind.CLUTTERED

    # 5. Exclude person box from clothing items to crop into wardrobe
    # (If no garment boxes exist at all, preserve person_boxes as provisional fallback)
    final_boxes = garment_boxes if garment_boxes else person_boxes

    return DetectionResult(
        input_kind=resolved_kind,
        boxes=final_boxes,
        quality_warnings=result.quality_warnings,
        person_box=detected_person_box,
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
