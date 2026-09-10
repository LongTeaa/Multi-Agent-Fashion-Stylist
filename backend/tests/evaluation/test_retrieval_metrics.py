from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import quantiles
from time import perf_counter
from uuid import uuid4

from sqlmodel import Session

from app.models.entities import User, WardrobeCategory, WardrobeItem
from app.schemas.retrieval import WardrobeRetrievalQuery
from app.services.retrieval_document_service import refresh_retrieval_document
from app.services.retrieval_service import RetrievalMatch, retrieve_wardrobe_items

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATASET_PATH = REPOSITORY_ROOT / "data" / "fixtures" / "retrieval_evaluation_v1.json"
REPORT_PATH = REPOSITORY_ROOT / "data" / "fixtures" / "retrieval_evaluation_v1_report.json"


@dataclass(frozen=True)
class RetrievalMetrics:
    recall_at_10: float
    precision_at_5: float
    fixed_denominator_precision_at_5: float


def _load_dataset() -> dict[str, object]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _seed_wardrobes(session: Session, dataset: dict[str, object]) -> None:
    templates = dataset["item_templates"]
    wardrobes = dataset["wardrobes"]
    assert isinstance(templates, dict) and isinstance(wardrobes, list)
    for wardrobe in wardrobes:
        assert isinstance(wardrobe, dict) and isinstance(wardrobe["items"], list)
        wardrobe_id = str(wardrobe["id"])
        session.add(User(id=wardrobe_id))
        session.flush()
        for item_value in wardrobe["items"]:
            item_name = str(item_value)
            attributes = templates[item_name]
            assert isinstance(attributes, dict)
            item = WardrobeItem(
                id=f"{wardrobe_id}/{item_name}",
                user_id=wardrobe_id,
                **attributes,
                is_active=True,
                is_user_confirmed=True,
            )
            session.add(item)
            session.flush()
            refresh_retrieval_document(session, item)
    session.commit()


def _ranked_ids(results: dict[WardrobeCategory, list[RetrievalMatch]]) -> list[str]:
    matches = [match for group in results.values() for match in group]
    matches.sort(
        key=lambda match: (
            -match.composite_score,
            -match.metadata_score,
            match.item.id,
        )
    )
    return [match.item.id for match in matches]


def _evaluate(
    session: Session, dataset: dict[str, object], *, enable_full_text: bool
) -> RetrievalMetrics:
    cases = dataset["queries"]
    assert isinstance(cases, list)
    recalls: list[float] = []
    precisions: list[float] = []
    fixed_denominator_precisions: list[float] = []
    for case in cases:
        assert isinstance(case, dict) and isinstance(case["intent"], dict)
        wardrobe_id = str(case["wardrobe"])
        query = WardrobeRetrievalQuery.model_validate(
            {**case["intent"], "enable_full_text": enable_full_text}
        )
        ranked = _ranked_ids(
            retrieve_wardrobe_items(session=session, user_id=wardrobe_id, query=query)
        )
        relevant_values = case["relevant"]
        assert isinstance(relevant_values, list)
        relevant = {f"{wardrobe_id}/{value}" for value in relevant_values}
        if not relevant:
            recalls.append(1.0 if not ranked else 0.0)
            precisions.append(1.0 if not ranked else 0.0)
            continue
        recalls.append(len(relevant & set(ranked[:10])) / len(relevant))
        relevant_hits = len(relevant & set(ranked[:5]))
        available_at_five = min(5, len(ranked))
        precisions.append(
            relevant_hits / available_at_five if available_at_five else 0.0
        )
        fixed_denominator_precisions.append(relevant_hits / 5)
    return RetrievalMetrics(
        recall_at_10=sum(recalls) / len(recalls),
        precision_at_5=sum(precisions) / len(precisions),
        fixed_denominator_precision_at_5=(
            sum(fixed_denominator_precisions) / len(fixed_denominator_precisions)
        ),
    )


def test_fixed_dataset_contains_thirty_vietnamese_queries_and_five_wardrobes() -> None:
    dataset = _load_dataset()
    wardrobes = dataset["wardrobes"]
    queries = dataset["queries"]
    assert dataset["dataset_version"] == "retrieval-v1"
    assert dataset["rule_version"] == "metadata-v1"
    assert isinstance(wardrobes, list) and len(wardrobes) == 5
    assert isinstance(queries, list) and len(queries) == 30
    assert len({str(case["id"]) for case in queries}) == 30
    assert all(
        any(ord(character) > 127 for character in str(case["query_vi"]))
        for case in queries
    )
    dress = next(value for value in wardrobes if value["id"] == "dress")
    small = next(value for value in wardrobes if value["id"] == "small")
    assert any("dress" in str(item) for item in dress["items"])
    assert len(small["items"]) <= 5


def test_retrieval_meets_quality_targets_without_semantic_index(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    dataset = _load_dataset()
    with Session(engine) as session:
        _seed_wardrobes(session, dataset)
        metadata_metrics = _evaluate(
            session, dataset, enable_full_text=False
        )
        full_text_metrics = _evaluate(
            session, dataset, enable_full_text=True
        )

    assert metadata_metrics.recall_at_10 >= 0.90
    assert metadata_metrics.precision_at_5 >= 0.75
    assert full_text_metrics.recall_at_10 >= 0.90
    assert full_text_metrics.precision_at_5 >= 0.75
    semantic_index_recommended = (
        full_text_metrics.recall_at_10 < 0.90
        or full_text_metrics.precision_at_5 < 0.75
    )
    report = {
        "dataset_version": dataset["dataset_version"],
        "rule_version": dataset["rule_version"],
        "metric_definition_version": "sparse-wardrobe-v1",
        "provider_model_version": None,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "metadata_only": {
            "recall_at_10": round(metadata_metrics.recall_at_10, 4),
            "precision_at_5": round(metadata_metrics.precision_at_5, 4),
            "fixed_denominator_precision_at_5": round(
                metadata_metrics.fixed_denominator_precision_at_5, 4
            ),
        },
        "metadata_plus_full_text": {
            "recall_at_10": round(full_text_metrics.recall_at_10, 4),
            "precision_at_5": round(full_text_metrics.precision_at_5, 4),
            "fixed_denominator_precision_at_5": round(
                full_text_metrics.fixed_denominator_precision_at_5, 4
            ),
        },
        "semantic_index_recommended": semantic_index_recommended,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    saved_report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert (
        saved_report["metric_definition_version"]
        == report["metric_definition_version"]
    )
    assert saved_report["metadata_only"] == report["metadata_only"]
    assert saved_report["metadata_plus_full_text"] == report["metadata_plus_full_text"]
    assert saved_report["semantic_index_recommended"] is semantic_index_recommended
    assert semantic_index_recommended is False


def test_metadata_search_p95_is_below_budget_with_five_hundred_items(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        for index in range(500):
            item = WardrobeItem(
                id=f"perf-{index:04d}",
                user_id=user_id,
                category=WardrobeCategory.TOP,
                sub_category="tee" if index % 2 else "polo",
                primary_color="white" if index % 3 else "navy",
                pattern="solid",
                material="cotton",
                style="smart_casual" if index % 2 else "casual",
                fit="regular",
                formality_level=2 + index % 2,
                weather_suitability=["warm", "cool"],
                free_text_tags=["cafe"],
                is_active=True,
                is_user_confirmed=True,
            )
            session.add(item)
            session.flush()
            refresh_retrieval_document(session, item)
        session.commit()
        query = WardrobeRetrievalQuery(
            categories=[WardrobeCategory.TOP],
            style_hints=["smart_casual"],
            weather_condition="cool",
            formality_min=2,
            formality_max=3,
        )
        retrieve_wardrobe_items(session=session, user_id=user_id, query=query)
        durations_ms: list[float] = []
        for _ in range(20):
            started = perf_counter()
            retrieve_wardrobe_items(session=session, user_id=user_id, query=query)
            durations_ms.append((perf_counter() - started) * 1000)

    p95_ms = quantiles(durations_ms, n=20)[18]
    print(json.dumps({"search_p95_ms_500_items": round(p95_ms, 3)}))
    assert p95_ms < 300
