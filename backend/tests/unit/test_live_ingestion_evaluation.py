"""Offline tests for the live ingestion evaluation: normalization, scoring and the runner wiring."""
from __future__ import annotations

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

from PIL import Image
import pytest

from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider
from app.services.vision_evaluation import (
    AttributeGoldItem, judge_attributes, latency_summary, normalize_color, normalize_material,
    normalize_pattern, score_attribute_run,
)

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend" / "scripts" / "evaluate_live_ingestion.py"
GOLD = ROOT / "data" / "fixtures" / "vision_attribute_gold_v1.json"
GOLD_V2 = ROOT / "data" / "fixtures" / "vision_attribute_gold_v2.json"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("evaluate_live_ingestion", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # pydantic resolves postponed annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def _gold(**overrides: Any) -> AttributeGoldItem:
    base: dict[str, Any] = dict(
        id="g1", file="g1.jpg", sha256="0" * 64, source_label="Polo",
        category=dict(accepted=["top"], provenance="source_dataset"),
        item_group=dict(accepted=["top"], provenance="ai_draft"),
        garment_type=dict(accepted=["polo"], provenance="ai_draft"),
        primary_color=dict(accepted=["white"], provenance="ai_draft"),
        pattern=dict(accepted=["solid"], provenance="ai_draft"),
        material=dict(accepted=["cotton"], provenance="ai_draft"),
        formality_level=dict(value=3, provenance="ai_draft"))
    base.update(overrides)
    return AttributeGoldItem.model_validate(base)


def _jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (64, 80), (240, 240, 240)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.mark.parametrize(("raw", "expected"), [
    ("Navy Blue", {"navy blue"}), ("navy", {"navy blue"}), ("light_blue", {"blue"}),
    ("Xanh navy", {"navy blue"}), ("teal", {"blue", "green"}), ("cream", {"beige", "white"}),
    ("charcoal grey", {"grey"}), ("", set()), (None, set()), ("iridescent", set()),
])
def test_color_normalization_maps_free_text_onto_taxonomy(raw: Any, expected: set[str]) -> None:
    assert normalize_color(raw) == expected


@pytest.mark.parametrize(("raw", "expected"), [
    ("Solid", "solid"), ("quilted", "solid"), ("pin-striped", "striped"), ("tartan", "plaid"),
    ("leopard print", "animal"), ("graphic_print", "graphic"), ("abstract", "print"),
    ("sequined", "embellished"), ("swirly", None),
])
def test_pattern_normalization(raw: str, expected: str | None) -> None:
    assert normalize_pattern(raw) == expected


def test_material_normalization_returns_fiber_families() -> None:
    assert normalize_material("100% cotton") == {"cotton"}
    assert normalize_material("satin") == {"silk", "synthetic"}
    assert normalize_material("suede") == {"leather"}
    assert normalize_material("fabric") == set()


def test_judge_accepts_any_listed_value_and_strict_uses_the_first() -> None:
    gold = _gold(category=dict(accepted=["top", "outerwear"], provenance="source_dataset+ai_draft"))
    verdict = judge_attributes(gold, dict(category="outerwear", sub_category="jacket",
                                          primary_color="off-white", pattern="plain",
                                          material="polyester", formality_level=5))
    assert verdict["category"] is True
    assert verdict["category_strict"] is False
    assert verdict["item_group"] is False
    assert verdict["primary_color"] is True
    assert verdict["pattern"] is True
    assert verdict["material"] is False
    assert (verdict["formality_exact"], verdict["formality_within_one"], verdict["formality_error"]) == (
        False, False, 2)


def test_unknown_or_unparseable_values_are_unanswered_not_correct() -> None:
    verdict = judge_attributes(_gold(), dict(category="unknown", primary_color="?", formality_level="high"))
    assert verdict["category"] is None
    assert verdict["primary_color"] is None
    assert verdict["formality_exact"] is None


def test_scoring_counts_provider_failures_as_wrong_and_reports_both_rates() -> None:
    gold = [_gold(id="a"), _gold(id="b"), _gold(id="c", category=dict(accepted=["bottom"], provenance="x"))]
    good = judge_attributes(gold[0], dict(category="top", sub_category="polo", primary_color="white",
                                          pattern="solid", material="cotton", formality_level=2))
    wrong = judge_attributes(gold[2], dict(category="top", sub_category="polo", formality_level=3))
    metrics = score_attribute_run(gold, {"a": good, "b": None, "c": wrong})
    assert metrics["category"] == dict(correct=1, answered=2, total=3, accuracy=0.3333,
                                       accuracy_when_answered=0.5)
    assert metrics["formality_within_one"]["correct"] == 2
    assert metrics["formality_exact"]["correct"] == 1
    assert metrics["formality_mae"] == 0.5
    assert {"expected": "top", "predicted": "no_answer", "count": 1} in metrics["category_confusion"]
    assert metrics["category_per_class"]["bottom"] == dict(total=1, correct=0, recall=0.0)


def test_latency_summary() -> None:
    assert latency_summary([]) == {"count": 0, "median": None, "p90": None, "max": None}
    summary = latency_summary([float(n) for n in range(1, 11)])
    assert (summary["median"], summary["p90"], summary["max"]) == (5.5, 9.0, 10.0)


@pytest.mark.parametrize("gold_path", [GOLD, GOLD_V2], ids=["v1", "v2"])
def test_gold_file_is_valid_and_independent_of_app_confirmations(gold_path: Path) -> None:
    data = json.loads(gold_path.read_text(encoding="utf-8"))
    items = [AttributeGoldItem.model_validate(item) for item in data["items"]]
    manifest = json.loads((ROOT / "data/fixtures/demo_wardrobe_v1.json").read_text(encoding="utf-8"))
    assert len(items) == len(manifest["items"]) == 58
    for item, source in zip(items, manifest["items"]):
        assert item.sha256 == source["sha256"]
        # The source label is the gold unless the owner explicitly relabelled it.
        if item.category.provenance != "owner_labelled":
            assert item.category.accepted[0] == source["expected_category"]
    assert all(i.owner_reviewed for i in items)
    assert {i.primary_color.provenance for i in items} <= {"owner_reviewed", "owner_labelled"}


def test_gold_v2_changes_only_formality_and_marks_every_change() -> None:
    v1 = {i["id"]: i for i in json.loads(GOLD.read_text(encoding="utf-8"))["items"]}
    v2 = {i["id"]: i for i in json.loads(GOLD_V2.read_text(encoding="utf-8"))["items"]}
    assert v1.keys() == v2.keys()
    unchanged_fields = lambda item: {k: v for k, v in item.items() if k not in ("formality_level", "note")}  # noqa: E731
    changed = []
    for item_id, old in v1.items():
        new = v2[item_id]
        assert unchanged_fields(old) == unchanged_fields(new)
        if old["formality_level"] != new["formality_level"]:
            assert new["formality_level"]["provenance"] == "kb_scale_proposed"
            changed.append(item_id)
        else:
            assert new["formality_level"]["provenance"] != "kb_scale_proposed"
    assert len(changed) == 11


class _BrokenVision:
    def extract_attributes(self, crop_bytes: bytes, spatial_context: dict[str, Any] | None = None) -> Any:
        raise RuntimeError("provider unavailable")


def test_runner_records_real_pipeline_outputs_and_scores_offline(tmp_path: Path) -> None:
    runner = _load_runner()
    image = _jpeg()
    ok = runner.run_attribute_cases([("g1", "g1.jpg", image)], FakeDetector("single_item"),
                                    FakeVisionProvider("golden_polo"))
    failed = runner.run_attribute_cases([("g1", "g1.jpg", image)], FakeDetector("single_item"), _BrokenVision())
    assert ok[0]["status"] == "ok" and len(ok[0]["detections"]) == 1
    assert ok[0]["vision_calls"][0]["crop_sha256"] == ok[0]["detections"][0]["crop_sha256"]
    assert failed[0]["vision_calls"][0]["status"] == "error"
    assert failed[0]["vision_calls"][0]["error_type"] == "RuntimeError"

    gold = [_gold()]
    scored_ok = runner.score_attributes(dict(attribute_results=ok), gold)
    scored_failed = runner.score_attributes(dict(attribute_results=failed), gold)
    assert scored_ok["metrics"]["category"]["correct"] == 1
    assert scored_ok["exactly_one_detection"] == dict(count=1, total=1)
    assert scored_failed["images_with_vision_error"] == 1
    assert scored_failed["metrics"]["category"]["correct"] == 0
    assert scored_failed["metrics"]["category"]["total"] == 1


def test_runner_records_detector_failure_as_full_frame_fallback() -> None:
    runner = _load_runner()
    rows = runner.run_attribute_cases([("g1", "g1.jpg", _jpeg())], FakeDetector("provider_error"),
                                      FakeVisionProvider("golden_polo"))
    assert rows[0]["detector_calls"][0]["status"] == "error"
    scored = runner.score_attributes(dict(attribute_results=rows), [_gold()])
    assert scored["images_with_detector_error"] == 1
    assert scored["full_frame_box"] == dict(count=1, total=1)


def test_localization_scoring_uses_one_to_one_matching() -> None:
    runner = _load_runner()
    dataset = runner.LocalizationDataset.model_validate(dict(
        dataset_version="t", annotation_kind="t", iou_threshold=0.5, cases=[
            dict(id="a", file="a.jpg", sha256="0" * 64, expected_box_count=2, regions=[
                dict(category="top", box=(0, 0, .5, 1)), dict(category="bottom", box=(.5, 0, 1, 1))]),
            dict(id="b", file="b.jpg", sha256="0" * 64, expected_box_count=1, regions=[
                dict(category="footwear", box=(0, 0, 1, 1))])]))
    raw = dict(localization_results=[
        dict(id="a", status="ok", elapsed_seconds=1.0, boxes=[dict(box=[0, 0, 1, 1])]),
        dict(id="b", status="error", error_type="TimeoutError")])
    scored = runner.score_localization(raw, dataset)
    assert (scored["matched_regions"], scored["expected_regions"]) == (1, 3)
    assert scored["provider_errors"] == 1
    assert scored["count_pass"] == dict(count=0, total=2)


def test_score_mode_rejects_unknown_schema(tmp_path: Path) -> None:
    runner = _load_runner()
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"schema": "other"}), encoding="utf-8")
    with pytest.raises(SystemExit):
        runner.main(["--score", str(raw)])
