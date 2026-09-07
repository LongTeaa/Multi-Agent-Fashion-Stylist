from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from app.core.dependencies import get_db_session, get_object_storage
from app.main import app
from app.models.entities import IngestionBatch, IngestionStatus, MediaAsset, MediaKind, User
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.schemas.common import ForbiddenAssetError, ValidationError
from app.services.ingestion_service import create_ingestion_batch
from app.services.upload_validation import (
    MAX_FILE_SIZE_BYTES,
    MIN_PIXEL_DIMENSION,
    ValidatedImage,
    validate_image_bytes,
)


def create_test_image_bytes(
    format_name: str = "JPEG",
    size: tuple[int, int] = (128, 128),
    color: tuple[int, int, int] = (255, 0, 0),
) -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(buffer, format=format_name)
    return buffer.getvalue()


@pytest.fixture
def test_storage(tmp_path: Path) -> LocalObjectStorage:
    buckets = StorageBuckets(
        wardrobe="wardrobe-private",
        thumbnails="wardrobe-thumbnails",
        tryon="tryon-private",
    )
    return LocalObjectStorage(root=tmp_path / "storage", buckets=buckets)


class TestUploadValidationService:
    def test_accepts_valid_formats(self) -> None:
        for fmt, expected_mime, expected_ext in [
            ("JPEG", "image/jpeg", "jpg"),
            ("PNG", "image/png", "png"),
            ("WEBP", "image/webp", "webp"),
        ]:
            data = create_test_image_bytes(format_name=fmt, size=(100, 100))
            validated = validate_image_bytes(data)
            assert isinstance(validated, ValidatedImage)
            assert validated.mime_type == expected_mime
            assert validated.extension == expected_ext
            assert validated.width == 100
            assert validated.height == 100
            assert len(validated.sha256) == 64
            assert validated.size_bytes == len(data)

    def test_rejects_empty_bytes(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            validate_image_bytes(b"")
        assert exc_info.value.code == "VALIDATION_ERROR"
        assert "rỗng" in exc_info.value.message

    def test_rejects_spoofed_or_corrupt_files(self) -> None:
        fake_files = [
            b"This is a plain text file pretending to be an image.",
            b"MZ\x90\x00\x03\x00\x00\x00",  # Fake DOS/Windows executable header
            b"\x89PNG\r\n\x1a\nCorrupted byte stream",
        ]
        for fake_data in fake_files:
            with pytest.raises(ValidationError) as exc_info:
                validate_image_bytes(fake_data)
            assert exc_info.value.code == "VALIDATION_ERROR"

    def test_rejects_oversized_file(self) -> None:
        large_bytes = b"0" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(ValidationError) as exc_info:
            validate_image_bytes(large_bytes)
        assert exc_info.value.code == "VALIDATION_ERROR"
        assert "10MB" in exc_info.value.message

    def test_rejects_too_small_pixels(self) -> None:
        too_small_data = create_test_image_bytes(size=(MIN_PIXEL_DIMENSION - 1, 100))
        with pytest.raises(ValidationError) as exc_info:
            validate_image_bytes(too_small_data)
        assert exc_info.value.code == "VALIDATION_ERROR"
        assert "quá nhỏ" in exc_info.value.message


class TestIngestionApiAndFailureSemantics:
    def test_upload_success_and_persistence(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        def override_storage():
            return test_storage

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = override_storage

        try:
            client = TestClient(app)
            img1_bytes = create_test_image_bytes("JPEG", (120, 120), (255, 0, 0))
            img2_bytes = create_test_image_bytes("PNG", (150, 150), (0, 255, 0))

            files = [
                ("images[]", ("photo1.jpg", img1_bytes, "image/jpeg")),
                ("images[]", ("photo2.png", img2_bytes, "image/png")),
            ]
            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=files,
            )

            assert response.status_code == 202
            body = response.json()
            assert body["success"] is True
            assert "batch_id" in body["data"]
            assert body["data"]["status"] == "processing"

            batch_id = body["data"]["batch_id"]

            with Session(engine) as session:
                batch = session.get(IngestionBatch, batch_id)
                assert batch is not None
                assert batch.status in (IngestionStatus.PROCESSING, IngestionStatus.NEEDS_REVIEW)

                original_assets = session.exec(
                    select(MediaAsset).where(
                        MediaAsset.ingestion_batch_id == batch_id,
                        MediaAsset.kind == MediaKind.ORIGINAL,
                    )
                ).all()
                assert len(original_assets) == 2
                for asset in original_assets:
                    assert test_storage.object_exists(
                        user_id=user_id,
                        bucket=asset.bucket,
                        object_key=asset.object_key,
                    )
        finally:
            app.dependency_overrides.clear()

    def test_upload_rejects_exceeding_10_files(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            single_img = create_test_image_bytes("JPEG", (80, 80))
            files = [("images[]", (f"img_{i}.jpg", single_img, "image/jpeg")) for i in range(11)]

            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=files,
            )
            assert response.status_code == 422
            body = response.json()
            assert body["success"] is False
            assert body["error"]["code"] == "VALIDATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_media_streaming_and_cross_user_isolation(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_a = str(uuid4())
        user_b = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            test_img = create_test_image_bytes("JPEG", (100, 100), (0, 0, 255))
            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_a},
                files=[("images[]", ("item.jpg", test_img, "image/jpeg"))],
            )
            assert upload_res.status_code == 202
            batch_id = upload_res.json()["data"]["batch_id"]

            with Session(engine) as session:
                asset = session.exec(
                    select(MediaAsset).where(MediaAsset.ingestion_batch_id == batch_id)
                ).first()
                assert asset is not None
                asset_id = asset.id

            # 1. User A (owner) can stream the asset
            res_owner = client.get(
                f"/api/v1/media/{asset_id}",
                headers={"X-User-Id": user_a},
            )
            assert res_owner.status_code == 200
            assert res_owner.headers["content-type"] == "image/jpeg"
            assert res_owner.content == test_img

            # 2. User B (non-owner) receives 403 FORBIDDEN_ASSET with normative Vietnamese message
            res_non_owner = client.get(
                f"/api/v1/media/{asset_id}",
                headers={"X-User-Id": user_b},
            )
            assert res_non_owner.status_code == 403
            err_body = res_non_owner.json()
            assert err_body["success"] is False
            assert err_body["error"]["code"] == "FORBIDDEN_ASSET"
            assert err_body["error"]["message"] == "Bạn không có quyền truy cập ảnh này."

            # 3. Non-existent asset ID returns 404
            res_not_found = client.get(
                f"/api/v1/media/{uuid4()}",
                headers={"X-User-Id": user_a},
            )
            assert res_not_found.status_code == 404
            assert res_not_found.json()["error"]["code"] == "MEDIA_NOT_FOUND"
        finally:
            app.dependency_overrides.clear()

    def test_failure_semantics_fs1_storage_failure_rollback(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())

        def broken_put_object(*args, **kwargs):
            raise RuntimeError("Simulated ObjectStorage I/O failure")

        monkeypatch.setattr(test_storage, "put_object", broken_put_object)

        with Session(engine) as session:
            img = create_test_image_bytes()
            with pytest.raises(Exception):
                create_ingestion_batch(
                    session=session,
                    storage=test_storage,
                    user_id=user_id,
                    raw_files=[("test.jpg", img)],
                )

            # Assert database transaction was rolled back cleanly
            batches = session.exec(select(IngestionBatch).where(IngestionBatch.user_id == user_id)).all()
            assert len(batches) == 0
            assets = session.exec(select(MediaAsset).where(MediaAsset.user_id == user_id)).all()
            assert len(assets) == 0

    def test_failure_semantics_fs2_db_error_compensating_cleanup(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())
        deleted_keys: list[str] = []

        original_delete = test_storage.delete_object

        def track_delete(*, user_id: str, bucket: str, object_key: str):
            deleted_keys.append(object_key)
            original_delete(user_id=user_id, bucket=bucket, object_key=object_key)

        monkeypatch.setattr(test_storage, "delete_object", track_delete)

        with Session(engine) as session:
            # Simulate DB commit failure
            def broken_commit():
                raise RuntimeError("Simulated DB lock/commit crash")

            monkeypatch.setattr(session, "commit", broken_commit)

            img = create_test_image_bytes()
            with pytest.raises(Exception):
                create_ingestion_batch(
                    session=session,
                    storage=test_storage,
                    user_id=user_id,
                    raw_files=[("test.jpg", img)],
                )

            # Assert compensating cleanup deleted the uploaded object
            assert len(deleted_keys) == 1
            assert "original" in deleted_keys[0]
            # Verify the object no longer exists in storage
            assert not test_storage.object_exists(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=deleted_keys[0],
            )
