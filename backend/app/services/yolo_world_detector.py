"""YOLO-World Open-Vocabulary Detector implementation using ONNX Runtime on CPU."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps

from app.models.entities import BoundingBox, ConfidenceValue, InputKind
from app.services.providers import BoundingBoxDetection, DetectionResult, DetectorProtocol

logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]


def resolve_yolo_model_path(model_path: str | Path) -> Path:
    """Resolve relative YOLO-World ONNX paths from either cwd or the backend/ directory."""
    candidate = Path(model_path)
    if candidate.is_file():
        return candidate
    if not candidate.is_absolute():
        backend_candidate = BACKEND_DIR / candidate
        if backend_candidate.is_file():
            return backend_candidate
    return candidate

DEFAULT_FASHION_CLASSES: list[str] = [
    "person",
    "clothing",
    "top",
    "shirt",
    "t-shirt",
    "jacket",
    "coat",
    "hoodie",
    "pants",
    "trousers",
    "shorts",
    "skirt",
    "dress",
    "shoes",
    "sneakers",
    "boots",
    "bag",
    "hat",
]

PERSON_LABELS: frozenset[str] = frozenset(
    {"person", "human", "model", "man", "woman", "boy", "girl"}
)
UPPER_GARMENT_LABELS: frozenset[str] = frozenset(
    {"top", "shirt", "t-shirt", "jacket", "coat", "hoodie"}
)
UPPER_TORSO_ALIAS_LABELS: frozenset[str] = frozenset({"top", "shirt", "t-shirt"})
LOWER_CONTOUR_LABELS: frozenset[str] = frozenset(
    {"pants", "trousers", "shorts", "skirt", "dress"}
)
FOOTWEAR_LABELS: frozenset[str] = frozenset({"shoes", "sneakers", "boots"})
HAT_LABELS: frozenset[str] = frozenset({"hat"})

# Only apply person-anchored low-confidence rescue when base threshold is in default range
ADAPTIVE_RESCUE_MAX_BASE_THRESHOLD = 0.35
DEFAULT_WEARER_GARMENT_MIN_CONFIDENCE = 0.13
MIN_PERSON_CONTAINMENT = 0.78
LOWER_CONTOUR_NMS_IOU = 0.70
SUBBOX_CONTAINMENT_THRESHOLD = 0.75
WEAK_RESCUE_OVERLAP_IOU = 0.70

COCO_80_CLASSES: list[str] = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]


def _nms(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float,
) -> list[int]:
    """Pure NumPy vectorised Non-Maximum Suppression (NMS).

    Args:
        boxes: Array of shape (N, 4) with coordinates [x1, y1, x2, y2].
        scores: Array of shape (N,) with confidence scores.
        iou_threshold: IoU threshold for suppression.

    Returns:
        Indices of preserved bounding boxes.
    """
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)

    order = scores.argsort()[::-1]
    keep: list[int] = []

    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h

        union = areas[i] + areas[order[1:]] - inter
        iou = np.where(union > 0.0, inter / union, 0.0)

        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]

    return keep


def _box_iou_and_containment(
    box_a: tuple[float, float, float, float],
    box_b: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    """Return (iou, fraction_of_a_inside_b, fraction_of_b_inside_a) for xyxy boxes."""
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    area_a = max(1e-9, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1e-9, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - inter_area
    iou = inter_area / union if union > 0.0 else 0.0
    return iou, inter_area / area_a, inter_area / area_b


def _passes_wearer_anatomical_gate(
    label_lower: str,
    garment_box: tuple[float, float, float, float],
    person_box: tuple[float, float, float, float],
    person_has_lower_garments: bool,
) -> bool:
    """Validate that a low-confidence garment candidate sits in its expected anatomical zone."""
    gx1, gy1, gx2, gy2 = garment_box
    px1, py1, px2, py2 = person_box
    p_width = max(1e-6, px2 - px1)
    p_height = max(1e-6, py2 - py1)
    p_area = p_width * p_height
    g_area = max(0.0, (gx2 - gx1) * (gy2 - gy1))
    if g_area <= 0.0 or p_area <= 0.0:
        return False

    _, in_person_ratio, _ = _box_iou_and_containment(garment_box, person_box)
    if in_person_ratio < MIN_PERSON_CONTAINMENT:
        return False

    area_ratio = g_area / p_area
    rel_ymin = (gy1 - py1) / p_height
    rel_ymax = (gy2 - py1) / p_height
    rel_cy = (rel_ymin + rel_ymax) / 2.0
    rel_width = (gx2 - gx1) / p_width

    if label_lower in UPPER_GARMENT_LABELS:
        if rel_ymin < 0.06 or rel_cy < 0.12 or not (0.035 <= area_ratio <= 0.65):
            return False
        if person_has_lower_garments:
            return rel_ymax <= 0.72 and rel_cy <= 0.58
        return rel_ymax <= 0.98 and rel_cy <= 0.72 and rel_width >= 0.30

    if label_lower == "dress":
        return 0.10 <= rel_ymin <= 0.65 and rel_ymax >= 0.45 and area_ratio >= 0.08

    if label_lower in LOWER_CONTOUR_LABELS:
        return 0.28 <= rel_ymin <= 0.75 and rel_ymax >= 0.48 and area_ratio >= 0.06

    if label_lower in FOOTWEAR_LABELS:
        return rel_ymin >= 0.65 and rel_ymax >= 0.78 and 0.004 <= area_ratio <= 0.25

    if label_lower in HAT_LABELS:
        return rel_ymax <= 0.30 and 0.005 <= area_ratio <= 0.18

    return False


def _suppress_group_by_nms(
    boxes_arr: np.ndarray,
    scores_arr: np.ndarray,
    labels: list[str],
    group_labels: frozenset[str],
    iou_threshold: float,
) -> set[int]:
    """Return indices to suppress within group_labels using IoU NMS."""
    indices = [i for i, lbl in enumerate(labels) if lbl in group_labels]
    if len(indices) < 2:
        return set()
    keep_relative = _nms(boxes_arr[indices], scores_arr[indices], iou_threshold)
    keep_group = {indices[i] for i in keep_relative}
    return set(indices) - keep_group


def _suppress_contained_subboxes(
    boxes: list[tuple[float, float, float, float]],
    scores: list[float],
    labels: list[str],
    group_labels: frozenset[str],
    min_containment: float = SUBBOX_CONTAINMENT_THRESHOLD,
) -> set[int]:
    """Suppress smaller lower-confidence sub-boxes enclosed within a larger box in the same group."""
    indices = [i for i, lbl in enumerate(labels) if lbl in group_labels]
    if len(indices) < 2:
        return set()
    suppressed: set[int] = set()
    ordered = sorted(indices, key=lambda idx: scores[idx], reverse=True)
    for pos, i in enumerate(ordered):
        if i in suppressed:
            continue
        area_i = (boxes[i][2] - boxes[i][0]) * (boxes[i][3] - boxes[i][1])
        for j in ordered[pos + 1:]:
            if j in suppressed:
                continue
            area_j = (boxes[j][2] - boxes[j][0]) * (boxes[j][3] - boxes[j][1])
            if area_j >= area_i:
                continue
            _, _, frac_j_in_i = _box_iou_and_containment(boxes[i], boxes[j])
            if frac_j_in_i >= min_containment:
                suppressed.add(j)
    return suppressed


def _suppress_weak_rescue_duplicates(
    boxes: list[tuple[float, float, float, float]],
    scores: list[float],
    labels: list[str],
    group_labels: frozenset[str],
    base_threshold: float,
) -> set[int]:
    """Drop low-confidence rescued boxes heavily overlapping a high-confidence sibling in the same group."""
    strong = [i for i, lbl in enumerate(labels) if lbl in group_labels and scores[i] >= base_threshold]
    weak = [i for i, lbl in enumerate(labels) if lbl in group_labels and scores[i] < base_threshold]
    if not strong or not weak:
        return set()
    suppressed: set[int] = set()
    for w_idx in weak:
        for s_idx in strong:
            iou, frac_w_in_s, _ = _box_iou_and_containment(boxes[w_idx], boxes[s_idx])
            if iou >= WEAK_RESCUE_OVERLAP_IOU or frac_w_in_s >= 0.85:
                suppressed.add(w_idx)
                break
    return suppressed


def _suppress_lower_scored_generic_clothing(
    boxes: list[tuple[float, float, float, float]],
    scores: list[float],
    labels: list[str],
    iou_threshold: float = LOWER_CONTOUR_NMS_IOU,
) -> set[int]:
    """Suppress generic 'clothing' boxes when a higher-scoring specific garment shares the contour."""
    generic_indices = [i for i, lbl in enumerate(labels) if lbl == "clothing"]
    if not generic_indices:
        return set()
    specific_indices = [
        i for i, lbl in enumerate(labels)
        if lbl not in PERSON_LABELS and lbl != "clothing"
    ]
    suppressed: set[int] = set()
    for g_idx in generic_indices:
        for s_idx in specific_indices:
            if scores[s_idx] >= scores[g_idx]:
                iou, _, _ = _box_iou_and_containment(boxes[g_idx], boxes[s_idx])
                if iou >= iou_threshold:
                    suppressed.add(g_idx)
                    break
    return suppressed


class YoloWorldDetector:
    """Production local detector using YOLO-World ONNX model with CPUExecutionProvider."""

    def __init__(
        self,
        model_path: str = "models/yolov8s-worldv2.onnx",
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        classes: list[str] | None = None,
        session: ort.InferenceSession | None = None,
        intra_op_num_threads: int = 4,
        wearer_garment_confidence_threshold: float = DEFAULT_WEARER_GARMENT_MIN_CONFIDENCE,
    ) -> None:
        self.model_path = model_path
        self.confidence_threshold = float(confidence_threshold)
        self.iou_threshold = float(iou_threshold)
        self.wearer_garment_confidence_threshold = float(wearer_garment_confidence_threshold)
        self.classes = list(classes) if classes is not None else list(DEFAULT_FASHION_CLASSES)

        if session is not None:
            self._session = session
            resolved_model_path = Path(model_path)
        else:
            p = resolve_yolo_model_path(model_path)
            resolved_model_path = p
            if not p.is_file():
                raise FileNotFoundError(
                    f"YOLO-World ONNX model not found at '{model_path}'. "
                    f"Please ensure the checkpoint exists or download it before using 'yolo_world' backend."
                )
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = max(1, intra_op_num_threads)
            sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

            self._session = ort.InferenceSession(
                str(p),
                sess_options=sess_options,
                providers=["CPUExecutionProvider"],
            )

        inputs = self._session.get_inputs()
        self._input_name = inputs[0].name
        input_names = [inp.name for inp in inputs]
        self._needs_txt_feats = "txt_feats" in input_names

        self._txt_feats: np.ndarray | None = None
        if self._needs_txt_feats:
            possible_paths = [
                resolved_model_path.parent / "fashion_clip_features.npy",
                Path("models/fashion_clip_features.npy"),
                BACKEND_DIR / "models/fashion_clip_features.npy",
                Path("backend/models/fashion_clip_features.npy"),
            ]
            for feat_p in possible_paths:
                if feat_p.is_file():
                    self._txt_feats = np.load(str(feat_p)).astype(np.float32)
                    break

    def _preprocess(
        self,
        image_bytes: bytes,
        target_size: tuple[int, int] = (640, 640),
    ) -> tuple[np.ndarray, float, float, float, int, int]:
        """Decode image, apply EXIF orientation, letterbox resize to target_size, and normalize to NCHW."""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGB":
                img = img.convert("RGB")
        except Exception as exc:
            raise ValueError(f"Failed to decode image bytes: {exc}") from exc

        orig_w, orig_h = img.size
        target_w, target_h = target_size
        scale = min(target_w / orig_w, target_h / orig_h)
        new_w = max(1, int(round(orig_w * scale)))
        new_h = max(1, int(round(orig_h * scale)))

        resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        canvas = Image.new("RGB", (target_w, target_h), (114, 114, 114))
        pad_x = (target_w - new_w) / 2.0
        pad_y = (target_h - new_h) / 2.0
        canvas.paste(resized, (int(round(pad_x)), int(round(pad_y))))

        arr = np.asarray(canvas, dtype=np.float32) / 255.0
        arr = np.transpose(arr, (2, 0, 1))  # (3, H, W)
        input_tensor = np.expand_dims(arr, axis=0)  # (1, 3, H, W)

        return input_tensor, scale, pad_x, pad_y, orig_w, orig_h

    def _get_prefilter_threshold(self) -> float:
        """Allow lower candidate threshold only for person-anchored rescue under standard thresholds."""
        if (
            self.confidence_threshold <= ADAPTIVE_RESCUE_MAX_BASE_THRESHOLD
            and self.wearer_garment_confidence_threshold < self.confidence_threshold
        ):
            return self.wearer_garment_confidence_threshold
        return self.confidence_threshold

    def _rescale_to_canonical_box(
        self,
        box: np.ndarray,
        scale: float,
        pad_x: float,
        pad_y: float,
        orig_w: int,
        orig_h: int,
    ) -> tuple[float, float, float, float] | None:
        """Convert letterbox [x1, y1, x2, y2] coordinates to canonical clamped [0.0, 1.0] bounds."""
        orig_x1 = (float(box[0]) - pad_x) / scale
        orig_y1 = (float(box[1]) - pad_y) / scale
        orig_x2 = (float(box[2]) - pad_x) / scale
        orig_y2 = (float(box[3]) - pad_y) / scale

        px1 = max(0.0, orig_x1)
        py1 = max(0.0, orig_y1)
        px2 = min(float(orig_w), orig_x2)
        py2 = min(float(orig_h), orig_y2)
        if px2 <= px1 or py2 <= py1:
            return None

        norm_x1 = max(0.0, min(1.0, round(px1 / orig_w, 4)))
        norm_y1 = max(0.0, min(1.0, round(py1 / orig_h, 4)))
        norm_x2 = max(norm_x1, min(1.0, round(px2 / orig_w, 4)))
        norm_y2 = max(norm_y1, min(1.0, round(py2 / orig_h, 4)))
        if norm_x2 <= norm_x1 or norm_y2 <= norm_y1:
            return None
        return (norm_x1, norm_y1, norm_x2, norm_y2)

    def _filter_person_anchored(
        self,
        boxes: list[tuple[float, float, float, float]],
        scores: list[float],
        labels_lower: list[str],
    ) -> list[int]:
        """Keep all high-confidence detections plus anatomically valid worn garments on strong persons."""
        if not boxes:
            return []
        strong_persons = [
            boxes[i] for i, lbl in enumerate(labels_lower)
            if lbl in PERSON_LABELS and scores[i] >= self.confidence_threshold
        ]
        person_contexts: list[tuple[tuple[float, float, float, float], bool]] = []
        for p_box in strong_persons:
            p_height = max(1e-6, p_box[3] - p_box[1])
            has_lower = any(
                labels_lower[j] in (LOWER_CONTOUR_LABELS | FOOTWEAR_LABELS)
                and _box_iou_and_containment(boxes[j], p_box)[1] >= MIN_PERSON_CONTAINMENT
                and (boxes[j][3] - p_box[1]) / p_height >= 0.72
                for j in range(len(boxes))
            )
            person_contexts.append((p_box, has_lower))

        keep_indices: list[int] = []
        for i, score in enumerate(scores):
            if score >= self.confidence_threshold:
                keep_indices.append(i)
                continue
            if not person_contexts or labels_lower[i] in PERSON_LABELS:
                continue
            if any(
                _passes_wearer_anatomical_gate(labels_lower[i], boxes[i], p_box, has_lower)
                for p_box, has_lower in person_contexts
            ):
                keep_indices.append(i)
        return keep_indices

    def _deduplicate_candidates(
        self,
        boxes: list[tuple[float, float, float, float]],
        scores: list[float],
        labels_lower: list[str],
    ) -> list[int]:
        """Apply alias NMS, lower-body contour merging, footwear sub-box suppression, and near-duplicate NMS."""
        if len(boxes) < 2:
            return list(range(len(boxes)))

        boxes_arr = np.asarray(boxes, dtype=np.float32)
        scores_arr = np.asarray(scores, dtype=np.float32)
        suppressed: set[int] = set()

        # Genuine alias groups share strict IoU threshold; upper layers stay preserved.
        for synonyms in (
            frozenset({"pants", "trousers"}),
            frozenset({"shoes", "sneakers", "boots"}),
            frozenset({"coat", "jacket"}),
        ):
            suppressed.update(_suppress_group_by_nms(boxes_arr, scores_arr, labels_lower, synonyms, self.iou_threshold))

        # Merge duplicate lower-body/one-piece silhouettes (e.g., wide-leg jeans tagged as both pants and dress).
        suppressed.update(
            _suppress_group_by_nms(boxes_arr, scores_arr, labels_lower, LOWER_CONTOUR_LABELS, LOWER_CONTOUR_NMS_IOU)
        )

        # Suppress enclosed single-shoe sub-boxes inside a full-pair footwear box.
        suppressed.update(_suppress_contained_subboxes(boxes, scores, labels_lower, FOOTWEAR_LABELS))

        # Suppress generic 'clothing' fallback detections when a higher-scoring specific garment shares the contour.
        suppressed.update(_suppress_lower_scored_generic_clothing(boxes, scores, labels_lower))

        # Suppress weak-rescued alternative labels when a high-confidence sibling already owns that region.
        for group in (UPPER_TORSO_ALIAS_LABELS, LOWER_CONTOUR_LABELS, FOOTWEAR_LABELS):
            suppressed.update(
                _suppress_weak_rescue_duplicates(
                    boxes, scores, labels_lower, group, self.confidence_threshold
                )
            )

        survivors = [i for i in range(len(boxes)) if i not in suppressed]
        if len(survivors) < 2:
            return survivors

        # Near-identical anchor duplicate suppression (IoU >= 0.92) across non-person garments.
        surv_garments = [i for i in survivors if labels_lower[i] not in PERSON_LABELS]
        if len(surv_garments) >= 2:
            keep_rel = _nms(boxes_arr[surv_garments], scores_arr[surv_garments], 0.92)
            keep_set = {surv_garments[i] for i in keep_rel}
            suppressed.update(set(surv_garments) - keep_set)

        return [i for i in survivors if i not in suppressed]

    def _postprocess(
        self,
        raw_outputs: list[np.ndarray],
        scale: float,
        pad_x: float,
        pad_y: float,
        orig_w: int,
        orig_h: int,
    ) -> list[BoundingBoxDetection]:
        """Convert ONNX model outputs to canonical BoundingBoxDetection items."""
        if not raw_outputs:
            return []

        preds = raw_outputs[0]
        prefilter_threshold = self._get_prefilter_threshold()

        # Handle different output formats:
        # 1. Standard YOLOv8: shape (1, 4 + C, 8400) or (1, 8400, 4 + C)
        # 2. End-to-end NMS output: shape (1, N, 6) or (N, 6)
        if preds.ndim == 3 and preds.shape[2] != 6:
            # Transpose if channels dimension (4 + C) is at axis 1
            if preds.shape[1] < preds.shape[2] or preds.shape[1] in (4 + len(self.classes), 84, 22):
                preds = np.transpose(preds, (0, 2, 1))

        if preds.ndim == 3 and preds.shape[2] == 6:
            # Output is already [x1, y1, x2, y2, score, class_id]
            flat_preds = preds[0]
            boxes_xyxy = flat_preds[:, :4]
            confidences = flat_preds[:, 4]
            class_ids = flat_preds[:, 5].astype(int)
        elif preds.ndim == 2 and preds.shape[1] == 6:
            boxes_xyxy = preds[:, :4]
            confidences = preds[:, 4]
            class_ids = preds[:, 5].astype(int)
        elif preds.ndim == 3:
            # Shape (1, num_anchors, 4 + C)
            flat_preds = preds[0]
            boxes_cxcywh = flat_preds[:, :4]
            scores_matrix = flat_preds[:, 4:]

            if np.any(scores_matrix < 0.0) or np.any(scores_matrix > 1.0):
                scores_matrix = 1.0 / (1.0 + np.exp(-np.clip(scores_matrix, -25.0, 25.0)))

            class_ids = np.argmax(scores_matrix, axis=1)
            confidences = np.max(scores_matrix, axis=1)

            # Filter by adaptive prefilter threshold first for speed
            conf_mask = confidences >= prefilter_threshold
            if not np.any(conf_mask):
                return []

            boxes_cxcywh = boxes_cxcywh[conf_mask]
            confidences = confidences[conf_mask]
            class_ids = class_ids[conf_mask]

            # Convert (cx, cy, w, h) to (x1, y1, x2, y2) in 640x640 space
            cx = boxes_cxcywh[:, 0]
            cy = boxes_cxcywh[:, 1]
            w = boxes_cxcywh[:, 2]
            h = boxes_cxcywh[:, 3]
            boxes_xyxy = np.column_stack([cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0])
        else:
            logger.warning("Unrecognized YOLO-World ONNX output tensor shape: %s", preds.shape)
            return []

        # Filter by adaptive prefilter threshold (if not done already)
        conf_mask = confidences >= prefilter_threshold
        if not np.any(conf_mask):
            return []

        boxes_xyxy = boxes_xyxy[conf_mask]
        confidences = confidences[conf_mask]
        class_ids = class_ids[conf_mask]

        # Multi-class NMS via class offset trick
        boxes_for_nms = boxes_xyxy + class_ids[:, None] * 4096.0
        keep_indices = _nms(boxes_for_nms, confidences, self.iou_threshold)

        if not keep_indices:
            return []

        kept_boxes = boxes_xyxy[keep_indices]
        kept_scores = confidences[keep_indices]
        kept_classes = class_ids[keep_indices]

        # Resolve labels vocabulary
        total_classes = int(np.max(kept_classes) + 1) if len(kept_classes) > 0 else len(self.classes)
        active_vocab = self.classes
        if total_classes > len(self.classes) and total_classes <= len(COCO_80_CLASSES):
            active_vocab = COCO_80_CLASSES

        norm_boxes: list[tuple[float, float, float, float]] = []
        cand_scores: list[float] = []
        cand_labels: list[str] = []
        cand_labels_lower: list[str] = []

        for i in range(len(kept_boxes)):
            norm_box = self._rescale_to_canonical_box(
                kept_boxes[i], scale, pad_x, pad_y, orig_w, orig_h
            )
            if norm_box is None:
                continue
            cls_id = int(kept_classes[i])
            label = active_vocab[cls_id] if 0 <= cls_id < len(active_vocab) else f"item_{cls_id}"
            norm_boxes.append(norm_box)
            cand_scores.append(float(kept_scores[i]))
            cand_labels.append(label)
            cand_labels_lower.append(label.lower())

        kept_adaptive = self._filter_person_anchored(norm_boxes, cand_scores, cand_labels_lower)
        if not kept_adaptive:
            return []

        norm_boxes = [norm_boxes[i] for i in kept_adaptive]
        cand_scores = [cand_scores[i] for i in kept_adaptive]
        cand_labels = [cand_labels[i] for i in kept_adaptive]
        cand_labels_lower = [cand_labels_lower[i] for i in kept_adaptive]

        final_indices = self._deduplicate_candidates(norm_boxes, cand_scores, cand_labels_lower)

        results: list[BoundingBoxDetection] = []
        for idx in final_indices:
            nx1, ny1, nx2, ny2 = norm_boxes[idx]
            canonical_box: BoundingBox = (
                ConfidenceValue(nx1),
                ConfidenceValue(ny1),
                ConfidenceValue(nx2),
                ConfidenceValue(ny2),
            )
            results.append(
                BoundingBoxDetection(
                    box=canonical_box,
                    label=cand_labels[idx],
                    confidence=ConfidenceValue(max(0.0, min(1.0, round(cand_scores[idx], 4)))),
                )
            )

        return results

    def detect(self, image_bytes: bytes) -> DetectionResult:
        """Execute detection pipeline on image bytes and return DetectionResult."""
        input_tensor, scale, pad_x, pad_y, orig_w, orig_h = self._preprocess(image_bytes)

        feed_dict = {self._input_name: input_tensor}
        if self._needs_txt_feats:
            if self._txt_feats is not None:
                feed_dict["txt_feats"] = self._txt_feats
            else:
                feed_dict["txt_feats"] = np.zeros((1, len(self.classes), 512), dtype=np.float32)

        outputs = self._session.run(None, feed_dict)

        boxes = self._postprocess(
            raw_outputs=outputs,
            scale=scale,
            pad_x=pad_x,
            pad_y=pad_y,
            orig_w=orig_w,
            orig_h=orig_h,
        )

        quality_warnings: list[str] = []
        if not boxes:
            quality_warnings.append("No garments or fashion items detected in image.")

        return DetectionResult(
            input_kind=InputKind.UNKNOWN,
            boxes=boxes,
            quality_warnings=quality_warnings,
            person_box=None,
        )
