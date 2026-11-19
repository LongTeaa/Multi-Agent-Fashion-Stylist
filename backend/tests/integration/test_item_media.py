from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.dependencies import get_db_session
from app.main import app
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    User,
    WardrobeCategory,
    WardrobeItem,
)
from app.services.item_media import primary_media_id, primary_media_ids
from app.services.retrieval_document_service import refresh_retrieval_document


def _add_item(session: Session, user_id: str) -> str:
    item = WardrobeItem(
        user_id=user_id,
        category=WardrobeCategory.TOP,
        sub_category="polo",
        primary_color="white",
        pattern="solid",
        material="cotton",
        style="smart_casual",
        fit="regular",
        formality_level=3,
        is_user_confirmed=True,
    )
    session.add(item)
    session.flush()
    refresh_retrieval_document(session, item)
    return item.id


def _link(
    session: Session, user_id: str, item_id: str, role: ItemMediaRole, *, deleted: bool = False
) -> str:
    asset = MediaAsset(
        user_id=user_id,
        kind=MediaKind.THUMBNAIL if role == ItemMediaRole.THUMBNAIL else MediaKind.CROP,
        bucket="wardrobe-private",
        object_key=f"users/{user_id}/items/{item_id}/{role.value}/{uuid4()}.png",
        mime_type="image/png",
        size_bytes=10,
        width=10,
        height=10,
        sha256="b" * 64,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    session.add(asset)
    session.flush()
    session.add(
        ItemMedia(wardrobe_item_id=item_id, media_asset_id=asset.id, user_id=user_id, role=role)
    )
    session.flush()
    return asset.id


def test_primary_media_ids_prefers_roles_and_skips_soft_deleted_assets(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id, other_user_id = str(uuid4()), str(uuid4())

    with Session(engine) as session:
        session.add_all([User(id=user_id), User(id=other_user_id)])
        session.flush()

        full = _add_item(session, user_id)
        alternate = _link(session, user_id, full, ItemMediaRole.ALTERNATE)
        thumbnail = _link(session, user_id, full, ItemMediaRole.THUMBNAIL)
        primary = _link(session, user_id, full, ItemMediaRole.PRIMARY)

        fallback = _add_item(session, user_id)
        _link(session, user_id, fallback, ItemMediaRole.PRIMARY, deleted=True)
        fallback_thumbnail = _link(session, user_id, fallback, ItemMediaRole.THUMBNAIL)

        only_alternate = _add_item(session, user_id)
        _link(session, user_id, only_alternate, ItemMediaRole.PRIMARY, deleted=True)
        _link(session, user_id, only_alternate, ItemMediaRole.THUMBNAIL, deleted=True)
        lone_alternate = _link(session, user_id, only_alternate, ItemMediaRole.ALTERNATE)

        gone = _add_item(session, user_id)
        _link(session, user_id, gone, ItemMediaRole.PRIMARY, deleted=True)

        bare = _add_item(session, user_id)
        session.commit()

        result = primary_media_ids(session, user_id, [full, fallback, only_alternate, gone, bare])

        assert result == {
            full: primary,
            fallback: fallback_thumbnail,
            only_alternate: lone_alternate,
        }
        assert alternate not in result.values() and thumbnail not in result.values()
        assert primary_media_id(session, full, user_id) == primary
        assert primary_media_id(session, gone, user_id) is None
        assert primary_media_ids(session, user_id, []) == {}
        # Another user's identifier never resolves this user's media.
        assert primary_media_ids(session, other_user_id, [full, fallback]) == {}


def test_wardrobe_api_does_not_return_soft_deleted_media_urls(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        fallback = _add_item(session, user_id)
        _link(session, user_id, fallback, ItemMediaRole.PRIMARY, deleted=True)
        thumbnail = _link(session, user_id, fallback, ItemMediaRole.THUMBNAIL)
        gone = _add_item(session, user_id)
        _link(session, user_id, gone, ItemMediaRole.PRIMARY, deleted=True)
        session.commit()

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        headers = {"X-User-Id": user_id}

        detail = client.get(f"/api/v1/wardrobe/items/{fallback}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["data"]["media_url"] == f"/api/v1/media/{thumbnail}"

        gone_detail = client.get(f"/api/v1/wardrobe/items/{gone}", headers=headers)
        assert gone_detail.json()["data"]["media_url"] is None

        listing = client.get("/api/v1/wardrobe/items", headers=headers)
        assert listing.status_code == 200
        urls = {item["id"]: item["media_url"] for item in listing.json()["data"]["items"]}
        assert urls == {fallback: f"/api/v1/media/{thumbnail}", gone: None}

        searched = client.get("/api/v1/wardrobe/items", headers=headers, params={"text": "polo"})
        assert {item["id"]: item["media_url"] for item in searched.json()["data"]["items"]} == urls
    finally:
        app.dependency_overrides.clear()
