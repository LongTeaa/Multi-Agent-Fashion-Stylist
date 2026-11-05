import pytest

from app.models.entities import InputKind
from app.services.crop_policy import review_crop_boxes
from app.services.providers import BoundingBoxDetection, DetectionResult
from app.services.vision_evaluation import region_retention
from app.services.classifier import classify_scene


def test_derby_sole_region_is_retained_with_a_bounded_margin() -> None:
    raw = (.092, .488, .906, .730)
    result = DetectionResult(InputKind.SINGLE_ITEM, [BoundingBoxDetection(raw, "shoes")])
    padded = review_crop_boxes(result)[0]
    assert padded.box == (.072, .468, .926, .75)
    reference = (.085, .49, .93, .76)
    assert region_retention(reference, raw) < .9
    assert region_retention(reference, padded.box) >= .95
    assert result.boxes[0].box == raw  # Provider result remains available for measurement.


@pytest.mark.parametrize("kind", [InputKind.WORN_OUTFIT, InputKind.MULTI_ITEM,
                                  InputKind.CLUTTERED, InputKind.UNKNOWN])
def test_context_with_adjacent_garments_or_face_is_not_expanded(kind: InputKind) -> None:
    # Even a single visible shoe in a worn/crowded photo keeps its tight region.
    box = BoundingBoxDetection((.1, .3, .6, .9), "footwear")
    assert review_crop_boxes(DetectionResult(kind, [box])) == [box]


def test_multiple_candidates_are_not_expanded_even_if_scene_is_mislabeled() -> None:
    boxes = [BoundingBoxDetection((.1, .1, .4, .8), "shoes"),
             BoundingBoxDetection((.41, .1, .7, .8), "pants")]
    assert review_crop_boxes(DetectionResult(InputKind.SINGLE_ITEM, boxes)) == boxes


@pytest.mark.parametrize("label,confidence", [("top", .95), ("clothing", .95),
                                              ("unknown", .95), ("shoes", .69)])
def test_uncertain_or_non_footwear_labels_are_unchanged(label: str, confidence: float) -> None:
    box = BoundingBoxDetection((.1, .2, .7, .8), label, confidence)
    assert review_crop_boxes(DetectionResult(InputKind.SINGLE_ITEM, [box])) == [box]


def test_margin_is_clipped_to_image_edges_and_does_not_duplicate_pairs() -> None:
    result = DetectionResult(InputKind.SINGLE_ITEM,
        [BoundingBoxDetection((.005, 0, .995, 1), "sneakers")])
    boxes = review_crop_boxes(result)
    assert len(boxes) == 1 and boxes[0].box == (0, 0, 1, 1)
    assert review_crop_boxes(DetectionResult(InputKind.SINGLE_ITEM, [])) == []


def test_scene_inferred_from_box_count_does_not_enable_margin() -> None:
    box = BoundingBoxDetection((.1, .2, .7, .8), "shoes")

    class Detector:
        def detect(self, image_bytes: bytes) -> DetectionResult:
            return DetectionResult(InputKind.UNKNOWN, [box])

    result = classify_scene(Detector(), b"test")
    assert result.input_kind == InputKind.SINGLE_ITEM and result.input_kind_inferred
    assert review_crop_boxes(result) == [box]
