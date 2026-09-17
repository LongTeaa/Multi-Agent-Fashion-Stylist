from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from statistics import quantiles
from time import perf_counter

from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session

from app.agents.context_agent import extract_context
from app.core.dependencies import get_db_session
from app.core.seed import GOLDEN_USER_ID, seed_golden_wardrobe
from app.main import app
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPOSITORY_ROOT / "data" / "fixtures"
CONTEXT_DATASET = FIXTURE_ROOT / "context_evaluation_v1.json"
VISION_DATASET = FIXTURE_ROOT / "vision_evaluation_v1.json"
ACCEPTANCE_REPORT = FIXTURE_ROOT / "acceptance_report_v1.json"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixed_phase7_dataset_shape_and_versions() -> None:
    context = _load(CONTEXT_DATASET)
    vision = _load(VISION_DATASET)
    report = _load(ACCEPTANCE_REPORT)

    assert context["dataset_version"] == "context-v1"
    assert context["rule_version"] == "context-rules-v1"
    assert context["provider_model_version"] == "deterministic-fallback-v1"
    assert isinstance(context["cases"], list) and len(context["cases"]) == 30
    assert isinstance(context["profiles"], list) and len(context["profiles"]) == 3

    assert vision["dataset_version"] == "vision-v1"
    assert vision["rule_version"] == "vision-normalization-v1"
    assert vision["provider_model_version"] == "fake-vision-v1"
    assert isinstance(vision["cases"], list) and len(vision["cases"]) == 30
    acceptable = [case for case in vision["cases"] if case["quality"] == "acceptable"]
    edge_cases = [case for case in vision["cases"] if case["quality"] != "acceptable"]
    assert len(acceptable) == 20
    assert len(edge_cases) == 10
    assert {case["quality"] for case in edge_cases} == {
        "multi_item",
        "worn_outfit",
        "cluttered",
        "low_quality",
    }

    for case in vision["cases"]:
        image_path = FIXTURE_ROOT / str(case["image"])
        assert image_path.is_file()
        with Image.open(image_path) as image:
            assert image.size == (256, 256)
            assert image.format == "JPEG"

    assert report["report_version"] == "acceptance-v1"
    assert report["execution_mode"] == "offline_deterministic"
    assert report["datasets"] == {
        "vision": vision["dataset_version"],
        "context": context["dataset_version"],
        "retrieval": "retrieval-v1",
    }
    assert report["provider_models"]["live_provider_run"] is False


def test_required_context_field_f1_meets_target() -> None:
    dataset = _load(CONTEXT_DATASET)
    cases = dataset["cases"]
    assert isinstance(cases, list)
    fields = (
        "occasion",
        "time_of_day",
        "weather_condition",
        "target_formality_range",
        "needs_clarification",
    )
    true_positives = 0
    false_positives = 0
    false_negatives = 0

    for case in cases:
        expected = case["expected"]
        predicted = extract_context(str(case["query"]), current_date=date(2026, 9, 17))
        prediction = predicted.model_dump()
        for field in fields:
            if prediction[field] == expected[field]:
                true_positives += 1
            else:
                false_positives += 1
                false_negatives += 1

    precision = true_positives / (true_positives + false_positives)
    recall = true_positives / (true_positives + false_negatives)
    f1 = 2 * precision * recall / (precision + recall)
    print(json.dumps({"context_required_field_f1": round(f1, 4)}))
    assert f1 >= 0.85


def test_vision_tagging_accuracy_meets_target_on_acceptable_images() -> None:
    dataset = _load(VISION_DATASET)
    cases = dataset["cases"]
    assert isinstance(cases, list)
    tag_hits = 0
    tag_total = 0
    kind_hits = 0

    for case in cases:
        image_bytes = (FIXTURE_ROOT / str(case["image"])).read_bytes()
        detector = FakeDetector(mode=str(case["detector_mode"]))
        detection = detector.detect(image_bytes)
        expected = case["expected"]
        kind_hits += int(detection.input_kind.value == expected["input_kind"])

        if case["quality"] != "acceptable":
            continue
        provider = FakeVisionProvider(scenario=str(case["vision_scenario"]))
        attributes = provider.extract_attributes(image_bytes).attributes
        for field in ("category", "primary_color", "formality_level"):
            tag_hits += int(attributes[field] == expected[field])
            tag_total += 1

    tagging_accuracy = tag_hits / tag_total
    input_kind_accuracy = kind_hits / len(cases)
    print(
        json.dumps(
            {
                "vision_tagging_accuracy": round(tagging_accuracy, 4),
                "input_kind_accuracy": round(input_kind_accuracy, 4),
            }
        )
    )
    assert tagging_accuracy >= 0.85
    assert input_kind_accuracy >= 0.85


def test_styling_response_p95_meets_budget(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    seed_golden_wardrobe(engine)
    app.dependency_overrides[get_db_session] = lambda: Session(engine)
    durations: list[float] = []
    try:
        client = TestClient(app)
        for _ in range(20):
            started = perf_counter()
            response = client.post(
                "/api/v1/stylist/chat",
                headers={"X-User-Id": GOLDEN_USER_ID},
                json={"query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?"},
            )
            durations.append(perf_counter() - started)
            assert response.status_code == 200
        p95_seconds = quantiles(durations, n=20)[18]
        print(json.dumps({"styling_response_p95_seconds": round(p95_seconds, 4)}))
        assert p95_seconds <= 5.0
    finally:
        app.dependency_overrides.clear()
