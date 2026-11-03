from hashlib import sha256
from itertools import product
import json
from pathlib import Path

from app.services.vision_evaluation import region_coverage

FIXTURES = Path(__file__).resolve().parents[3] / "data/fixtures"


def test_annotation_version_changes_only_reviewed_source_and_preserves_thresholds() -> None:
    old_bytes = (FIXTURES / "vision_real_review_v1.json").read_bytes()
    old = json.loads(old_bytes)
    new = json.loads((FIXTURES / "vision_real_review_v2.json").read_text(encoding="utf-8"))
    assert new["supersedes_manifest_sha256"] == sha256(old_bytes).hexdigest()
    assert new["iou_threshold"] == old["iou_threshold"] == .5
    assert new["cases"][1:] == old["cases"][1:]
    assert new["cases"][0]["sha256"] == old["cases"][0]["sha256"]
    assert new["cases"][0]["regions"] != old["cases"][0]["regions"]


def test_frozen_prediction_reassessment_and_sensitivity_are_reproducible() -> None:
    old = json.loads((FIXTURES / "vision_real_review_v1.json").read_text(encoding="utf-8"))
    new = json.loads((FIXTURES / "vision_real_review_v2.json").read_text(encoding="utf-8"))
    evidence = json.loads((FIXTURES / "vision_real_review_v1_followup_20261102.json").read_text(encoding="utf-8"))
    report = json.loads((FIXTURES / "vision_annotation_review_20261103.json").read_text(encoding="utf-8"))
    boxes = [tuple(box["box"]) for box in evidence["cases"][0]["boxes"]]
    assert region_coverage([tuple(r["box"]) for r in old["cases"][0]["regions"]], boxes, .5, .9) == report["before"]
    assert region_coverage([tuple(r["box"]) for r in new["cases"][0]["regions"]], boxes, .5, .9) == report["after"]
    width, height = new["annotation_review"]["source_size"]
    for reference, sensitivity in zip(new["annotation_review"]["reviewed_pixel_boxes"], report["region_sensitivity"]):
        matches = 0
        for offsets in product((-3, 0, 3), repeat=4):
            x0, y0, x1, y1 = [n + d for n, d in zip(reference, offsets)]
            region = (max(0, x0) / width, max(0, y0) / height,
                      min(width, x1) / width, min(height, y1) / height)
            matches += region_coverage([region], boxes, .5, .9)["matched_regions"]
        assert matches == sensitivity["passing_variants"]
        assert sensitivity["variants"] == 81
