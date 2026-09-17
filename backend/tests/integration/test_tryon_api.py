from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from app.core.dependencies import (
    get_db_session,
    get_image_provider,
    get_object_storage,
)
from app.main import app
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    TryOnRender,
    User,
    WardrobeCategory,
    WardrobeItem,
)
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.fakes.image_fakes import FakeImageProvider


def _image_bytes(color: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (160, 220), color).save(buffer, format="JPEG")
    return buffer.getvalue()


def _override_session(engine: object):
    def override_db():
        with Session(engine) as session:
            yield session

    return override_db


def _seed_outfit(
    *,
    engine: object,
    storage: LocalObjectStorage,
    user_id: str,
    corrupt_second_crop: bool = False,
) -> str:
    outfit_id = str(uuid4())
    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        session.add(
            OutfitRecommendation(
                id=outfit_id,
                user_id=user_id,
                request_id=str(uuid4()),
                user_query="Đi cafe buổi tối",
                context_snapshot={},
                explanation_vi="Bộ trang phục cân bằng và lịch sự.",
                fashion_score=0.9,
                personalization_score=0.8,
                composite_score=0.86,
                rank=1,
                rule_version="test-v1",
            )
        )
        session.flush()
        for index, (slot, category, sub_category, color) in enumerate(
            (
                (OutfitSlotRole.TOP, WardrobeCategory.TOP, "polo", "white"),
                (OutfitSlotRole.BOTTOM, WardrobeCategory.BOTTOM, "chinos", "navy"),
            )
        ):
            item_id, asset_id = str(uuid4()), str(uuid4())
            crop_bytes = b"broken" if corrupt_second_crop and index == 1 else _image_bytes(color)
            object_key = f"users/{user_id}/items/{item_id}/crop/v1.jpg"
            session.add(
                WardrobeItem(
                    id=item_id,
                    user_id=user_id,
                    category=category,
                    sub_category=sub_category,
                    primary_color=color,
                    pattern="solid",
                    material="cotton",
                    style="smart_casual",
                    fit="regular",
                    formality_level=3,
                    is_active=True,
                    is_user_confirmed=True,
                )
            )
            session.add(
                MediaAsset(
                    id=asset_id,
                    user_id=user_id,
                    kind=MediaKind.CROP,
                    bucket="wardrobe-private",
                    object_key=object_key,
                    mime_type="image/jpeg",
                    size_bytes=len(crop_bytes),
                    width=160,
                    height=220,
                    sha256=sha256(crop_bytes).hexdigest(),
                )
            )
            session.flush()
            session.add(
                ItemMedia(
                    wardrobe_item_id=item_id,
                    media_asset_id=asset_id,
                    user_id=user_id,
                    role=ItemMediaRole.PRIMARY,
                )
            )
            session.add(
                OutfitItem(
                    outfit_id=outfit_id,
                    wardrobe_item_id=item_id,
                    user_id=user_id,
                    slot_role=slot,
                )
            )
            storage.put_object(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=object_key,
                data=crop_bytes,
                content_type="image/jpeg",
            )
        session.commit()
    return outfit_id


def _storage(tmp_path: Path) -> LocalObjectStorage:
    return LocalObjectStorage(
        root=tmp_path / "storage",
        buckets=StorageBuckets(
            wardrobe="wardrobe-private",
            thumbnails="wardrobe-thumbnails",
            tryon="tryon-private",
        ),
    )


def test_generated_tryon_is_persisted_privately_with_benchmark_metadata(
    migrated_database: tuple[object, object],
    tmp_path: Path,
) -> None:
    _, engine = migrated_database
    user_id, other_user_id = str(uuid4()), str(uuid4())
    storage = _storage(tmp_path)
    outfit_id = _seed_outfit(engine=engine, storage=storage, user_id=user_id)
    with Session(engine) as session:
        session.add(User(id=other_user_id))
        session.commit()

    app.dependency_overrides[get_db_session] = _override_session(engine)
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_image_provider] = lambda: FakeImageProvider(
        model="fake-lookbook-v2"
    )
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/tryons",
            headers={"X-User-Id": user_id},
            json={"outfit_id": outfit_id},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["outfit_id"] == outfit_id
        assert data["render_kind"] == "generated_lookbook"
        assert data["fallback_used"] is False
        assert data["status"] == "ready"
        assert data["duration_ms"] >= 0
        assert data["image_url"].startswith("/api/v1/media/")
        assert "object_key" not in response.text

        asset_id = data["image_url"].rsplit("/", maxsplit=1)[-1]
        owner_media = client.get(data["image_url"], headers={"X-User-Id": user_id})
        assert owner_media.status_code == 200
        assert owner_media.headers["content-type"].startswith("image/webp")
        forbidden = client.get(data["image_url"], headers={"X-User-Id": other_user_id})
        assert forbidden.status_code == 403

        with Session(engine) as session:
            render = session.get(TryOnRender, data["tryon_id"])
            asset = session.get(MediaAsset, asset_id)
            assert render is not None
            assert render.provider == "fake"
            assert render.model == "fake-lookbook-v2"
            assert render.media_asset_id == asset_id
            assert asset is not None
            assert asset.bucket == "tryon-private"
            assert asset.object_key == f"users/{user_id}/tryons/{render.id}/render.webp"
            assert storage.object_exists(
                user_id=user_id,
                bucket=asset.bucket,
                object_key=asset.object_key,
            )
    finally:
        app.dependency_overrides.clear()


def test_provider_error_or_disabled_provider_returns_moodboard_200(
    migrated_database: tuple[object, object],
    tmp_path: Path,
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    storage = _storage(tmp_path)
    outfit_id = _seed_outfit(engine=engine, storage=storage, user_id=user_id)

    app.dependency_overrides[get_db_session] = _override_session(engine)
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        client = TestClient(app)
        for provider in (
            FakeImageProvider(model="fake-failing", scenario="provider_error"),
            None,
        ):
            app.dependency_overrides[get_image_provider] = lambda provider=provider: provider
            response = client.post(
                "/api/v1/tryons",
                headers={"X-User-Id": user_id},
                json={"outfit_id": outfit_id},
            )
            assert response.status_code == 200
            data = response.json()["data"]
            assert data["render_kind"] == "moodboard"
            assert data["fallback_used"] is True
    finally:
        app.dependency_overrides.clear()


def test_tryon_rejects_cross_user_outfit_and_returns_504_when_fallback_fails(
    migrated_database: tuple[object, object],
    tmp_path: Path,
) -> None:
    _, engine = migrated_database
    owner_id, other_user_id = str(uuid4()), str(uuid4())
    storage = _storage(tmp_path)
    outfit_id = _seed_outfit(
        engine=engine,
        storage=storage,
        user_id=owner_id,
        corrupt_second_crop=True,
    )
    with Session(engine) as session:
        session.add(User(id=other_user_id))
        session.commit()

    app.dependency_overrides[get_db_session] = _override_session(engine)
    app.dependency_overrides[get_object_storage] = lambda: storage
    app.dependency_overrides[get_image_provider] = lambda: None
    try:
        client = TestClient(app)
        forbidden = client.post(
            "/api/v1/tryons",
            headers={"X-User-Id": other_user_id},
            json={"outfit_id": outfit_id},
        )
        assert forbidden.status_code == 404
        assert forbidden.json()["error"]["code"] == "OUTFIT_NOT_FOUND"

        failed = client.post(
            "/api/v1/tryons",
            headers={"X-User-Id": owner_id},
            json={"outfit_id": outfit_id},
        )
        assert failed.status_code == 504
        assert failed.json()["error"] == {
            "code": "TRYON_FAILED",
            "message": "Không thể tạo ảnh minh họa lúc này. Vui lòng thử lại sau.",
            "details": None,
        }
        with Session(engine) as session:
            assert session.exec(select(TryOnRender)).all() == []
    finally:
        app.dependency_overrides.clear()
