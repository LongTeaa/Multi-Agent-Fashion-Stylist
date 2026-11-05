from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from alembic.config import Config
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.core.dependencies import get_db_session, get_context_llm_provider, get_weather_provider
from app.core.seed import GOLDEN_USER_ID, GOLDEN_WARDROBE, seed_golden_wardrobe, _new_item
from app.main import app
from app.models.entities import FeedbackDeliveredOutfit, FeedbackPromptState, UserPreference, WardrobeItem, WardrobeCategory, Rating, RatingSource, RecommendationRequest, OutfitRecommendation
from app.services.retrieval_document_service import refresh_retrieval_document
from app.schemas.common import AppException
from app.schemas.stylist import StylistChatRequest
from app.services.recommendation_replay import bind_request


@pytest.fixture
def review_client(migrated_database: tuple[Config, Engine]) -> Iterator[tuple[TestClient, Engine]]:
    _, engine = migrated_database
    seed_golden_wardrobe(engine)
    def db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_context_llm_provider] = lambda: None
    app.dependency_overrides[get_weather_provider] = lambda: None
    with TestClient(app) as client:
        yield client, engine


def test_retry_preserves_complete_response_and_binds_content(review_client: tuple[TestClient, Engine]) -> None:
    client, engine = review_client
    with Session(engine) as session:
        session.add(FeedbackPromptState(user_id=GOLDEN_USER_ID, eligible_count_since_prompt=4, next_threshold=5))
        session.add(UserPreference(user_id=GOLDEN_USER_ID, styles=["smart_casual"], color_palettes=["neutral"]))
        session.commit()
    headers = {"X-User-Id": GOLDEN_USER_ID}
    payload = {"query": "Đi cafe buổi tối trời mát", "location": "Hà Nội", "idempotency_key": str(uuid4())}
    first = client.post("/api/v1/stylist/chat", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    data = first.json()["data"]
    assert data["feedback_prompt_eligible"]
    assert any(rec["applied_preferences"] for rec in data["recommendations"])
    retry = client.post("/api/v1/stylist/chat", headers=headers, json=payload)
    assert retry.status_code == 200 and retry.json()["data"] == data
    with Session(engine) as session:
        assert len(session.exec(select(FeedbackDeliveredOutfit)).all()) == len(data["recommendations"])
        session.add(Rating(user_id=GOLDEN_USER_ID, outfit_id=data["feedback_target_outfit_id"],
                           stars=4, source=RatingSource.MANUAL))
        session.commit()
    rated_retry = client.post("/api/v1/stylist/chat", headers=headers, json=payload)
    assert rated_retry.status_code == 200
    assert not rated_retry.json()["data"]["feedback_prompt_eligible"]
    assert rated_retry.json()["data"]["feedback_target_outfit_id"] is None
    for change in ({"query": "Đi dự tiệc trang trọng"}, {"location": "Đà Lạt"}):
        changed = client.post("/api/v1/stylist/chat", headers=headers, json={**payload, **change})
        assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    item_id = data["recommendations"][0]["items"][0]["item_id"]
    assert client.delete(f"/api/v1/wardrobe/items/{item_id}", headers=headers).status_code == 200
    assert client.post("/api/v1/stylist/chat", headers=headers, json=payload).status_code == 409


def test_legacy_wrong_query_cannot_claim_existing_key(review_client: tuple[TestClient, Engine]) -> None:
    client, engine = review_client
    headers = {"X-User-Id": GOLDEN_USER_ID}
    payload = {"query": "Đi cafe buổi tối trời mát", "idempotency_key": str(uuid4())}
    first = client.post("/api/v1/stylist/chat", headers=headers, json=payload)
    assert first.status_code == 200
    with Session(engine) as session:
        record = session.get(RecommendationRequest, (GOLDEN_USER_ID, payload["idempotency_key"]))
        assert record is not None
        session.delete(record)
        for recommendation in session.exec(select(OutfitRecommendation)).all():
            snapshot = dict(recommendation.context_snapshot)
            snapshot.pop("_request_location", None)
            recommendation.context_snapshot = snapshot
            session.add(recommendation)
        session.commit()
    assert client.post("/api/v1/stylist/chat", headers=headers,
                       json={**payload, "query": "Đi dự tiệc"}).status_code == 409
    assert client.post("/api/v1/stylist/chat", headers=headers, json=payload).status_code == 200


def test_key_binding_is_atomic_across_competing_queries(review_client: tuple[TestClient, Engine]) -> None:
    _, engine = review_client
    key = str(uuid4())
    def bind(query: str) -> str:
        with Session(engine) as session:
            try:
                bind_request(session, GOLDEN_USER_ID, key, StylistChatRequest(query=query))
                return "bound"
            except AppException as error:
                assert error.status_code == 409
                return "conflict"
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(bind, ["Đi làm", "Đi cafe"])) == ["bound", "conflict"]


def test_seed_uuid_crud_and_null_validation(review_client: tuple[TestClient, Engine]) -> None:
    client, _ = review_client
    headers = {"X-User-Id": GOLDEN_USER_ID}
    for item in GOLDEN_WARDROBE:
        assert str(UUID(item.id)) == item.id
        assert client.get(f"/api/v1/wardrobe/items/{item.id}", headers=headers).status_code == 200
    url = f"/api/v1/wardrobe/items/{GOLDEN_WARDROBE[0].id}"
    for field in ("category", "sub_category", "comfort_level", "weather_suitability", "primary_color", "free_text_tags"):
        assert client.patch(url, headers=headers, json={field: None}).status_code == 422
    assert client.patch(url, headers=headers, json={"secondary_color": None}).status_code == 200
    assert client.patch(url, headers=headers, json={"comfort_level": 5}).json()["data"]["comfort_level"] == 5
    assert client.delete(url, headers=headers).status_code == 200


def test_avoid_colors_applies_before_large_wardrobe_combination_budget(review_client: tuple[TestClient, Engine]) -> None:
    client, engine = review_client
    with Session(engine) as session:
        tops = list(GOLDEN_WARDROBE[:3])
        for index, spec in enumerate(tops):
            item = session.get(WardrobeItem, spec.id)
            item.primary_color = "white" if index == 2 else "black"
            item.style = "casual"
            item.formality_level = 3
            item.weather_suitability = ["warm", "cool"]
            refresh_retrieval_document(session, item)
        for spec in (GOLDEN_WARDROBE[3], GOLDEN_WARDROBE[6]):
            for _ in range(14):
                item = _new_item(spec)
                item.id = str(uuid4())
                session.add(item)
                session.flush()
                refresh_retrieval_document(session, item)
        outer = _new_item(GOLDEN_WARDROBE[0])
        outer.id, outer.category, outer.sub_category = str(uuid4()), WardrobeCategory.OUTERWEAR, "jacket"
        session.add(outer)
        session.flush()
        refresh_retrieval_document(session, outer)
        session.add(UserPreference(user_id=GOLDEN_USER_ID, avoid_colors=["black"]))
        session.commit()
    result = client.post("/api/v1/stylist/chat", headers={"X-User-Id": GOLDEN_USER_ID},
                         json={"query": "Đi cafe trời mát"})
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    with Session(engine) as session:
        for outfit in data["recommendations"]:
            for item in outfit["items"]:
                record = session.get(WardrobeItem, item["item_id"])
                assert record.primary_color != "black"
                if item["slot"] == "top":
                    assert item["item_id"] == tops[2].id
    from app.agents.personalization_agent import AVOID_RELAXATION_WARNING
    assert AVOID_RELAXATION_WARNING not in data["warnings"]
