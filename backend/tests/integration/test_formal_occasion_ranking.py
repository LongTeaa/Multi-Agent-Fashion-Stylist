"""Regression: formal occasions rank the in-range outfit first on the golden wardrobe.

Before the fix, the golden button-down shirt was seeded at formality 3 (equal to the
polo) and FormalityFit only averaged major items, so a bank interview and a wedding
returned "white polo + black trousers + Oxford" first, tied with the shirt outfit.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.dependencies import get_db_session, get_utc_clock
from app.core.seed import GOLDEN_USER_ID, golden_item_id, seed_golden_wardrobe
from app.main import app

SHIRT = golden_item_id("item-top-02")
POLO = golden_item_id("item-top-01")
TROUSERS = golden_item_id("item-bottom-02")
OXFORD = golden_item_id("item-shoes-02")
CAFE_GOLDEN = {POLO, golden_item_id("item-bottom-01"), golden_item_id("item-shoes-01")}


def _clock() -> datetime:
    return datetime(2026, 11, 18, 2, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def client(migrated_database: tuple[object, object]):
    _, engine = migrated_database
    seed_golden_wardrobe(engine)

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _clock
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _recommendations(client: TestClient, query: str) -> list[dict]:
    response = client.post(
        "/api/v1/stylist/chat",
        headers={"X-User-Id": GOLDEN_USER_ID},
        json={"query": query, "location": None},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["recommendations"]


def _item_ids(recommendation: dict) -> set[str]:
    return {item["item_id"] for item in recommendation["items"]}


@pytest.mark.parametrize(
    "query",
    [
        "Sáng mai phỏng vấn xin việc ở ngân hàng",
        "Cuối tuần đi đám cưới bạn thân ở nhà hàng",
    ],
)
def test_formal_occasion_ranks_shirt_trousers_oxford_first(client: TestClient, query: str) -> None:
    recs = _recommendations(client, query)

    assert recs, "a formal request on the golden wardrobe must return an outfit"
    assert _item_ids(recs[0]) == {SHIRT, TROUSERS, OXFORD}
    polo_ranks = [index for index, rec in enumerate(recs) if POLO in _item_ids(rec)]
    assert all(index > 0 for index in polo_ranks)
    assert all(
        recs[0]["composite_score"] > recs[index]["composite_score"] for index in polo_ranks
    )


def test_cafe_keeps_golden_outfit_first_and_offers_alternatives(client: TestClient) -> None:
    recs = _recommendations(client, "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?")

    assert len(recs) >= 2
    assert _item_ids(recs[0]) == CAFE_GOLDEN
