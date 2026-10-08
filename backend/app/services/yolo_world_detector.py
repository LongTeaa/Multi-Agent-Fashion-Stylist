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


class YoloWorldDetector:
    """Production local detector using YOLO-World ONNX model with CPUExecutionProvider."""

    def __init__(
        self,
        model_path: str = "models/yolov8s-worldv2.onnx",
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        padding: float = 0.05,
        classes: list[str] | None = None,
        session: ort.InferenceSession | None = None,
        intra_op_num_threads: int = 4,
    ) -> None:
        self.model_path = model_path
        self.confidence_threshold = float(confidence_threshold)
        self.iou_threshold = float(iou_threshold)
        self.padding = float(padding)
        self.classes = list(classes) if classes is not None else list(DEFAULT_FASHION_CLASSES)

        if session is not None:
            self._session = session
        else:
            p = Path(model_path)
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
                Path(model_path).parent / "fashion_clip_features.npy",
                Path("models/fashion_clip_features.npy"),
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

            # Filter by confidence threshold first for speed
            conf_mask = confidences >= self.confidence_threshold
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
            x1 = cx - w / 2.0
            y1 = cy - h / 2.0
            x2 = cx + w / 2.0
            y2 = cy + h / 2.0
            boxes_xyxy = np.column_stack([x1, y1, x2, y2])
        else:
            logger.warning("Unrecognized YOLO-World ONNX output tensor shape: %s", preds.shape)
            return []

        # Filter by confidence threshold (if not done already)
        conf_mask = confidences >= self.confidence_threshold
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

        results: list[BoundingBoxDetection] = []
        for i in range(len(kept_boxes)):
            box = kept_boxes[i]
            score = float(kept_scores[i])
            cls_id = int(kept_classes[i])

            label = active_vocab[cls_id] if 0 <= cls_id < len(active_vocab) else f"item_{cls_id}"

            # Rescale from letterbox coordinates to original pixel coordinates
            orig_x1 = (box[0] - pad_x) / scale
            orig_y1 = (box[1] - pad_y) / scale
            orig_x2 = (box[2] - pad_x) / scale
            orig_y2 = (box[3] - pad_y) / scale

            # Bounding Box Padding (+5% default)
            bw = orig_x2 - orig_x1
            bh = orig_y2 - orig_y1
            pad_w = bw * self.padding
            pad_h = bh * self.padding

            px1 = max(0.0, orig_x1 - pad_w)
            py1 = max(0.0, orig_y1 - pad_h)
            px2 = min(float(orig_w), orig_x2 + pad_w)
            py2 = min(float(orig_h), orig_y2 + pad_h)

            if px2 <= px1 or py2 <= py1:
                continue

            # Normalize to canonical [0.0, 1.0]
            norm_x1 = max(0.0, min(1.0, round(px1 / orig_w, 4)))
            norm_y1 = max(0.0, min(1.0, round(py1 / orig_h, 4)))
            norm_x2 = max(norm_x1, min(1.0, round(px2 / orig_w, 4)))
            norm_y2 = max(norm_y1, min(1.0, round(py2 / orig_h, 4)))

            canonical_box: BoundingBox = (
                ConfidenceValue(norm_x1),
                ConfidenceValue(norm_y1),
                ConfidenceValue(norm_x2),
                ConfidenceValue(norm_y2),
            )

            results.append(
                BoundingBoxDetection(
                    box=canonical_box,
                    label=label,
                    confidence=ConfidenceValue(max(0.0, min(1.0, round(score, 4)))),
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
