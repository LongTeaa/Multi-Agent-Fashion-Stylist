from pathlib import Path

from PIL import Image
import pytest

from scripts.evaluate_crop_boundaries import BoundaryDataset, evaluate_case, source_bytes

ROOT = Path(__file__).resolve().parents[3]
DATASET = BoundaryDataset.model_validate_json(
    (ROOT / "data/fixtures/crop_boundary_v1.json").read_text(encoding="utf-8"))
SYNTHETIC_CASES = [case for case in DATASET.cases if case.source_kind == "synthetic_markers"]


@pytest.mark.parametrize("case_id", [case.id for case in SYNTHETIC_CASES])
def test_protected_source_pixels_and_explicit_negative_control(case_id: str, tmp_path: Path) -> None:
    case = next(case for case in SYNTHETIC_CASES if case.id == case_id)
    raw = source_bytes(case, tmp_path, DATASET.synthetic_size)
    result = evaluate_case(case, raw, tmp_path, 1)
    assert result["policy_conforms_to_fixture"]
    red_counts = []
    for suffix in ("raw", "effective"):
        with Image.open(tmp_path / f"case-01-{suffix}.png") as crop:
            red_counts.append(sum(pixel == (255, 0, 0) for pixel in crop.convert("RGB").getdata()))
    assert max(0, red_counts[1] - red_counts[0]) == result["added_protected_pixels"]
    if case.evidence_kind == "negative_control":
        assert not result["protected_region_guard_passed"]
        assert result["added_protected_pixels"] == 1680
    else:
        assert result["protected_region_guard_passed"]
        assert result["added_protected_pixels"] == 0
    if case.scene.value == "unknown":
        assert result["input_kind_inferred"]
    if case.id == "image-edge-clipping":
        assert result["effective_box"] == (0, 0, 1, 1)
        with Image.open(tmp_path / "case-01-effective.png") as crop:
            assert crop.size == DATASET.synthetic_size
