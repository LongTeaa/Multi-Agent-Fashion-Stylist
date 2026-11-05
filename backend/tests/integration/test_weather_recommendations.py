"""Real graph + HTTP weather adapter + persisted, owned wardrobe recommendations."""
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine
from sqlmodel import Session, select

from app.core.dependencies import get_context_llm_provider, get_db_session, get_utc_clock, get_weather_provider
from app.core.seed import GOLDEN_WARDROBE, _new_item
from app.main import app
from app.models.entities import OutfitRecommendation, User, WardrobeCategory, WardrobeItem
from app.services.retrieval_document_service import refresh_retrieval_document
from app.services.weather_providers import OpenMeteoProvider
from tests.unit.test_weather_integration import meteo_client


@pytest.mark.parametrize("temperature,code,expected", [(35, 0, "hot"), (10, 0, "cold"), (24, 61, "rainy")])
def test_weather_changes_actual_owned_outfit_through_full_graph(
    migrated_database: tuple[object, Engine], temperature: int, code: int, expected: str,
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    groups: dict[str, set[str]] = {weather: set() for weather in ("hot", "cold", "rainy")}
    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        for weather in groups:
            for spec in (GOLDEN_WARDROBE[0], GOLDEN_WARDROBE[3], GOLDEN_WARDROBE[6]):
                item = _new_item(spec)
                item.id, item.user_id = str(uuid4()), user_id
                item.weather_suitability = [weather]
                item.style, item.formality_level, item.comfort_level = "casual", 3, 5 if weather == "hot" else 3
                item.primary_color, item.material = "white", "cotton"
                item.functional_flags = ["rain", "water_resistant"] if weather == "rainy" else []
                session.add(item)
                session.flush()
                refresh_retrieval_document(session, item)
                groups[weather].add(item.id)
            if weather == "cold":
                outer = _new_item(GOLDEN_WARDROBE[0])
                outer.id, outer.user_id = str(uuid4()), user_id
                outer.category, outer.sub_category = WardrobeCategory.OUTERWEAR, "jacket"
                outer.style, outer.formality_level = "casual", 3
                outer.weather_suitability, outer.functional_flags = ["cold"], ["heavy", "outdoor"]
                session.add(outer)
                session.flush()
                refresh_retrieval_document(session, outer)
                groups[weather].add(outer.id)
        session.commit()

    def db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_context_llm_provider] = lambda: None
    app.dependency_overrides[get_utc_clock] = lambda: lambda: datetime(2026, 11, 3, 1, tzinfo=timezone.utc)
    with meteo_client(temperature=temperature, code=code) as weather_http:
        app.dependency_overrides[get_weather_provider] = lambda: OpenMeteoProvider(client=weather_http)
        with TestClient(app) as client:
            payload = {"query": "Tối nay đi cafe ngoài trời ở Hà Nội", "idempotency_key": str(uuid4())}
            headers = {"X-User-Id": user_id}
            response = client.post("/api/v1/stylist/chat", headers=headers, json=payload)
            assert response.status_code == 200, response.text
            data = response.json()["data"]
            assert (data["context"]["weather_condition"], data["context"]["weather_source"]) == (expected, "api")
            assert data["context"]["time_of_day"] == "evening"
            top = data["recommendations"][0]
            assert {item["item_id"] for item in top["items"]} <= groups[expected]
            if expected == "cold":
                assert any(item["slot"] == "outerwear" for item in top["items"])
            with Session(engine) as session:
                ids = {row.id for row in session.exec(select(OutfitRecommendation)).all()}
                assert all(outfit["outfit_id"] in ids for outfit in data["recommendations"])
                for outfit in data["recommendations"]:
                    for item in outfit["items"]:
                        row = session.get(WardrobeItem, item["item_id"])
                        assert row.user_id == user_id and row.is_active and row.is_user_confirmed
            retry = client.post("/api/v1/stylist/chat", headers=headers, json=payload)
            assert retry.status_code == 200 and retry.json()["data"] == data
