from app.services.vision_evaluation import box_iou, region_coverage


def test_iou_identical_disjoint_and_partial() -> None:
    assert box_iou((0, 0, 1, 1), (0, 0, 1, 1)) == 1
    assert box_iou((0, 0, .2, .2), (.8, .8, 1, 1)) == 0
    assert box_iou((0, 0, 1, 1), (0, 0, .5, 1)) == .5


def test_a_fallback_box_cannot_count_as_multiple_detected_items() -> None:
    result = region_coverage([(0, 0, .6, 1), (.4, 0, 1, 1)], [(0, 0, 1, 1)])
    assert result["matched_regions"] == 1
    assert result["coverage"] == .5


def test_matching_is_one_to_one_and_maximizes_coverage() -> None:
    assert region_coverage([(0, 0, 1, 1), (0, 0, .5, 1)],
                           [(0, 0, .5, 1), (.5, 0, 1, 1)])["matched_regions"] == 2
    assert region_coverage([(0, 0, 1, 1)], [])["coverage"] == 0
