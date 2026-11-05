"""Conservative automatic footwear margin; manual crop coordinates stay exact."""
from dataclasses import replace

from app.models.entities import InputKind, WardrobeCategory
from app.services.garment_taxonomy import classify, normalize
from app.services.providers import BoundingBoxDetection, DetectionResult

AUTO_CROP_POLICY_VERSION = "isolated-footwear-margin-v1"
AUTO_FOOTWEAR_MARGIN = 0.02


def review_crop_boxes(result: DetectionResult) -> list[BoundingBoxDetection]:
    """Pad only one confidently detected footwear unit in a single-item scene.

    Two shoes of a matching pair are one unit. Unknown labels, worn outfits,
    multiple candidates, and provider fallback images are deliberately excluded.
    Coordinates remain normalized relative to the original image.
    """
    if result.input_kind_inferred or result.input_kind != InputKind.SINGLE_ITEM or len(result.boxes) != 1:
        return list(result.boxes)
    detection = result.boxes[0]
    group, _ = classify(WardrobeCategory.FOOTWEAR, detection.label)
    if detection.confidence < 0.7 or (group is None and normalize(detection.label) != "footwear"):
        return list(result.boxes)
    xmin, ymin, xmax, ymax = detection.box
    if not (0 <= xmin < xmax <= 1 and 0 <= ymin < ymax <= 1):
        raise ValueError("Invalid automatic crop coordinates")
    margin = AUTO_FOOTWEAR_MARGIN
    box = (round(max(0.0, xmin - margin), 6), round(max(0.0, ymin - margin), 6),
           round(min(1.0, xmax + margin), 6), round(min(1.0, ymax + margin), 6))
    return [replace(detection, box=box)]
