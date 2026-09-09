from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.dependencies import get_db_session, get_object_storage
from app.main import app
from app.models.entities import (
    MediaAsset,
    MediaKind,
    User,
    WardrobeCategory,
    WardrobeItem,
    WardrobeRetrievalDocument,
)
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets


@pytest.fixture
def wardrobe_storage(tmp_path: Path) -> LocalObjectStorage:
    return LocalObjectStorage(
        root=tmp_path / "storage",
        buckets=StorageBuckets(
            wardrobe="wardrobe-private",
            thumbnails="wardrobe-thumbnails",
            tryon="tryon-private",
        ),
    )


def _item_payload(media_asset_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "media_asset_id": media_asset_id,
        "category": "top",
        "sub_category": "polo",
        "primary_color": "white",
        "secondary_color": None,
        "pattern": "solid",
        "material": "cotton",
        "style": "smart_casual",
        "fit": "regular",
        "formality_level": 3,
        "season": ["spring"],
        "weather_suitability": ["warm", "cool"],
        "functional_flags": [],
        "free_text_tags": ["cafe"],
    }
    payload.update(overrides)
    return payload


def test_wardrobe_crud_filters_media_and_cross_user_isolation(
    migrated_database: tuple[object, object],
    wardrobe_storage: LocalObjectStorage,
) -> None:
    _, engine = migrated_database
    user_a, user_b = str(uuid4()), str(uuid4())
    content = b"private-image"
    asset_id = str(uuid4())
    object_key = f"users/{user_a}/items/uploaded-item/crop/item.jpg"

    with Session(engine) as session:
        session.add(User(id=user_a))
        session.add(User(id=user_b))
        session.flush()
        session.add(
            MediaAsset(
                id=asset_id,
                user_id=user_a,
                kind=MediaKind.CROP,
                bucket="wardrobe-private",
                object_key=object_key,
                mime_type="image/jpeg",
                size_bytes=len(content),
                width=10,
                height=10,
                sha256=sha256(content).hexdigest(),
            )
        )
        session.add(
            WardrobeItem(
                user_id=user_a,
                category=WardrobeCategory.BOTTOM,
                sub_category="hidden",
                primary_color="black",
                pattern="solid",
                material="cotton",
                style="casual",
                fit="regular",
                formality_level=1,
                is_user_confirmed=False,
            )
        )
        session.add(
            WardrobeItem(
                user_id=user_b,
                category=WardrobeCategory.TOP,
                sub_category="other-user-shirt",
                primary_color="white",
                pattern="solid",
                material="cotton",
                style="smart_casual",
                fit="regular",
                formality_level=3,
                is_user_confirmed=True,
            )
        )
        session.commit()

    wardrobe_storage.put_object(
        user_id=user_a,
        bucket="wardrobe-private",
        object_key=object_key,
        data=content,
        content_type="image/jpeg",
    )

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_object_storage] = lambda: wardrobe_storage
    try:
        client = TestClient(app)
        created = client.post(
            "/api/v1/wardrobe/items",
            headers={"X-User-Id": user_a},
            json=_item_payload(asset_id),
        )
        assert created.status_code == 201
        item = created.json()["data"]
        item_id = item["id"]
        assert item["is_user_confirmed"] is True
        assert item["field_confidence"] == {}
        assert item["times_worn"] == 0
        assert item["last_worn_at"] is None
        assert item["media_url"] == f"/api/v1/media/{asset_id}"
        with Session(engine) as session:
            document = session.get(WardrobeRetrievalDocument, item_id)
            assert document is not None
            assert document.user_id == user_a
            assert "white" in document.searchable_text
            assert document.metadata_snapshot["free_text_tags"] == ["cafe"]

        listing = client.get(
            "/api/v1/wardrobe/items?category=top&style=smart_casual&color=white&text=cafe",
            headers={"X-User-Id": user_a},
        )
        assert listing.status_code == 200
        assert listing.json()["data"]["total"] == 1
        assert [row["id"] for row in listing.json()["data"]["items"]] == [item_id]

        assert client.get(
            f"/api/v1/wardrobe/items/{item_id}", headers={"X-User-Id": user_b}
        ).status_code == 404
        assert client.patch(
            f"/api/v1/wardrobe/items/{item_id}",
            headers={"X-User-Id": user_b},
            json={"primary_color": "black"},
        ).status_code == 404
        assert client.delete(
            f"/api/v1/wardrobe/items/{item_id}", headers={"X-User-Id": user_b}
        ).status_code == 404

        media = client.get(item["media_url"], headers={"X-User-Id": user_a})
        assert media.status_code == 200
        assert media.content == content
        assert client.get(
            item["media_url"], headers={"X-User-Id": user_b}
        ).status_code == 403

        updated = client.patch(
            f"/api/v1/wardrobe/items/{item_id}",
            headers={"X-User-Id": user_a},
            json={"primary_color": "navy", "free_text_tags": ["office"]},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["primary_color"] == "navy"
        with Session(engine) as session:
            document = session.get(WardrobeRetrievalDocument, item_id)
            assert document is not None
            assert "navy" in document.searchable_text
            assert "office" in document.searchable_text
            assert "white" not in document.searchable_text

        deleted = client.delete(
            f"/api/v1/wardrobe/items/{item_id}", headers={"X-User-Id": user_a}
        )
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"item_id": item_id, "is_active": False}
        assert client.get(
            f"/api/v1/wardrobe/items/{item_id}", headers={"X-User-Id": user_a}
        ).status_code == 404
        assert client.get(
            "/api/v1/wardrobe/items", headers={"X-User-Id": user_a}
        ).json()["data"]["total"] == 0

        with Session(engine) as session:
            persisted = session.exec(
                select(WardrobeItem).where(WardrobeItem.id == item_id)
            ).one()
            assert persisted.is_active is False
            assert persisted.deleted_at is not None
            assert session.get(WardrobeRetrievalDocument, item_id) is None
    finally:
        app.dependency_overrides.clear()


def test_manual_creation_rejects_cross_user_media(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_a, user_b = str(uuid4()), str(uuid4())
    asset_id = str(uuid4())
    content = b"x"
    with Session(engine) as session:
        session.add(User(id=user_a))
        session.add(User(id=user_b))
        session.flush()
        session.add(
            MediaAsset(
                id=asset_id,
                user_id=user_a,
                kind=MediaKind.CROP,
                bucket="wardrobe-private",
                object_key=f"users/{user_a}/items/uploaded/crop/item.jpg",
                mime_type="image/jpeg",
                size_bytes=1,
                width=1,
                height=1,
                sha256=sha256(content).hexdigest(),
            )
        )
        session.commit()

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    try:
        response = TestClient(app).post(
            "/api/v1/wardrobe/items",
            headers={"X-User-Id": user_b},
            json=_item_payload(asset_id),
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN_ASSET"
    finally:
        app.dependency_overrides.clear()
