"""Geometry metrics for opt-in real-image evaluation, independent of providers."""
from __future__ import annotations

from app.models.entities import BoundingBox


def box_iou(left: BoundingBox, right: BoundingBox) -> float:
    intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    union = (left[2] - left[0]) * (left[3] - left[1]) + (
        right[2] - right[0]
    ) * (right[3] - right[1]) - intersection
    return intersection / union if union > 0 else 0.0


def region_retention(expected: BoundingBox, predicted: BoundingBox) -> float:
    """Fraction of the annotated garment rectangle retained by a crop."""
    area = (expected[2] - expected[0]) * (expected[3] - expected[1])
    intersection = max(0.0, min(expected[2], predicted[2]) - max(expected[0], predicted[0])) * max(
        0.0, min(expected[3], predicted[3]) - max(expected[1], predicted[1])
    )
    return intersection / area if area > 0 else 0.0


def region_coverage(
    expected: list[BoundingBox], predicted: list[BoundingBox], threshold: float = 0.5,
    min_retention: float = 0.0,
) -> dict[str, int | float]:
    """Maximum one-to-one match count, so one full-frame box cannot cover all items.

    This is localization coverage only, not semantic category/attribute accuracy.
    """
    choices = [[i for i, box in enumerate(predicted) if box_iou(region, box) >= threshold
                and region_retention(region, box) >= min_retention]
               for region in expected]
    assigned: dict[int, int] = {}

    def match(region: int, visited: set[int]) -> bool:
        for prediction in choices[region]:
            if prediction in visited:
                continue
            visited.add(prediction)
            if prediction not in assigned or match(assigned[prediction], visited):
                assigned[prediction] = region
                return True
        return False

    count = sum(match(index, set()) for index in range(len(expected)))
    return {"expected_regions": len(expected), "predicted_regions": len(predicted),
            "matched_regions": count, "coverage": count / len(expected) if expected else 0.0}
