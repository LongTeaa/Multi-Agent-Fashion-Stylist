from collections.abc import Iterator
from uuid import uuid4

from fastapi.testclient import TestClient
from alembic.config import Config
from sqlalchemy import Engine
from sqlmodel import Session

from app.core.dependencies import get_db_session
from app.main import app
from app.models.entities import User
from tests.unit.test_garment_taxonomy import item


def test_search_filters_before_paging_and_respects_ownership(
    migrated_database: tuple[Config, Engine],
) -> None:
    _, engine = migrated_database
    owner, other = str(uuid4()), str(uuid4())
    with Session(engine) as session:
        session.add_all([User(id=owner), User(id=other)])
        session.flush()
        for category, subtype, user, active, confirmed in [
            ("footwear", "derby", owner, True, True),
            ("footwear", "sneakers", owner, True, True),
            ("footwear", "derby", other, True, True),
            ("footwear", "derby", owner, False, True),
            ("footwear", "derby", owner, True, False),
            ("bottom", "trousers", owner, True, True),
            ("bottom", "skirt", owner, True, True),
        ]:
            record = item(category, subtype)
            record.user_id, record.is_active, record.is_user_confirmed = user, active, confirmed
            session.add(record)
        session.commit()

    def db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db_session] = db
    with TestClient(app) as client:
        headers = {"X-User-Id": owner}
        first = client.get("/api/v1/wardrobe/items", headers=headers,
                           params={"text": "giay den", "page_size": 1}).json()["data"]
        second = client.get("/api/v1/wardrobe/items", headers=headers,
                            params={"text": "giày đen", "page_size": 1, "page": 2}).json()["data"]
        assert first["total"] == second["total"] == 2
        assert first["items"][0]["id"] != second["items"][0]["id"]
        assert first["items"][0]["item_group"] == "shoes"
        pants = client.get("/api/v1/wardrobe/items", headers=headers,
                           params={"category": "bottom", "item_group": "pants"}).json()["data"]
        assert pants["total"] == 1
        assert pants["items"][0]["sub_category"] == "trousers"
        assert client.get("/api/v1/wardrobe/items", headers=headers,
                          params={"item_group": "invalid"}).status_code == 422
        catalog = client.get("/api/v1/wardrobe/items/taxonomy", headers=headers)
        assert catalog.status_code == 200
        assert {g["value"] for g in catalog.json()["data"]["groups"]} >= {"pants", "skirt", "shoes", "sandals"}
        assert client.get("/api/v1/wardrobe/items/taxonomy").status_code == 422
