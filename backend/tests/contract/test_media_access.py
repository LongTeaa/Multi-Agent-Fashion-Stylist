from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.dependencies import get_db_session, get_object_storage
from app.main import app
from app.models.entities import MediaAsset, MediaKind, User, utc_now
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets


@pytest.fixture
def private_storage(tmp_path: Path) -> LocalObjectStorage:
    return LocalObjectStorage(
        root=tmp_path / "storage",
        buckets=StorageBuckets(
            wardrobe="wardrobe-private",
            thumbnails="wardrobe-thumbnails",
            tryon="tryon-private",
        ),
    )


def _override_session(engine: object):
    def override_db():
        with Session(engine) as session:
            yield session

    return override_db


def test_media_stream_requires_identity_and_enforces_database_owner(
    migrated_database: tuple[object, object],
    private_storage: LocalObjectStorage,
) -> None:
    _, engine = migrated_database
    owner_id, other_user_id = str(uuid4()), str(uuid4())
    asset_id = str(uuid4())
    content = b"owner-private-image"
    object_key = f"users/{owner_id}/items/item-1/crop/v1.jpg"
    with Session(engine) as session:
        session.add(User(id=owner_id))
        session.add(User(id=other_user_id))
        session.flush()
        session.add(
            MediaAsset(
                id=asset_id,
                user_id=owner_id,
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
        session.commit()
    private_storage.put_object(
        user_id=owner_id,
        bucket="wardrobe-private",
        object_key=object_key,
        data=content,
        content_type="image/jpeg",
    )

    app.dependency_overrides[get_db_session] = _override_session(engine)
    app.dependency_overrides[get_object_storage] = lambda: private_storage
    try:
        client = TestClient(app)
        missing_identity = client.get(f"/api/v1/media/{asset_id}")
        assert missing_identity.status_code == 422
        assert missing_identity.json()["error"]["code"] == "VALIDATION_ERROR"

        owner_response = client.get(
            f"/api/v1/media/{asset_id}", headers={"X-User-Id": owner_id}
        )
        assert owner_response.status_code == 200
        assert owner_response.content == content
        assert owner_response.headers["cache-control"] == "private, max-age=3600"

        forbidden = client.get(
            f"/api/v1/media/{asset_id}", headers={"X-User-Id": other_user_id}
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["error"]["code"] == "FORBIDDEN_ASSET"

        header_precedence = client.get(
            f"/api/v1/media/{asset_id}?user_id={owner_id}",
            headers={"X-User-Id": other_user_id},
        )
        assert header_precedence.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_deleted_media_is_not_streamed(
    migrated_database: tuple[object, object],
    private_storage: LocalObjectStorage,
) -> None:
    _, engine = migrated_database
    owner_id, asset_id = str(uuid4()), str(uuid4())
    content = b"deleted-image"
    object_key = f"users/{owner_id}/items/item-2/crop/v1.jpg"
    with Session(engine) as session:
        session.add(User(id=owner_id))
        session.flush()
        session.add(
            MediaAsset(
                id=asset_id,
                user_id=owner_id,
                kind=MediaKind.CROP,
                bucket="wardrobe-private",
                object_key=object_key,
                mime_type="image/jpeg",
                size_bytes=len(content),
                width=10,
                height=10,
                sha256=sha256(content).hexdigest(),
                deleted_at=utc_now(),
            )
        )
        session.commit()

    app.dependency_overrides[get_db_session] = _override_session(engine)
    app.dependency_overrides[get_object_storage] = lambda: private_storage
    try:
        response = TestClient(app).get(
            f"/api/v1/media/{asset_id}", headers={"X-User-Id": owner_id}
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "MEDIA_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
