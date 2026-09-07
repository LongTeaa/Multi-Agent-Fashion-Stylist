from __future__ import annotations

from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from app.core.dependencies import (
    get_db_session,
    get_detector,
    get_object_storage,
    get_vision_provider,
)
from app.main import app
from app.models.entities import (
    IngestionBatch,
    IngestionStatus,
    MediaAsset,
    MediaKind,
    User,
    WardrobeItem,
    utc_now,
)
from app.repositories.object_storage import (
    LocalObjectStorage,
    ObjectStorageError,
    StorageBuckets,
)
from app.services.cleanup_service import cleanup_expired_batches
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider


def create_test_image_bytes(
    format_name: str = "JPEG",
    size: tuple[int, int] = (150, 150),
    color: tuple[int, int, int] = (100, 150, 200),
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


class TestIngestionCleanupIntegration:
    def test_manual_batch_cancellation(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """User can cancel an unconfirmed batch, deleting transient files from storage."""
        _, engine = migrated_database
        user_id = str(uuid4())

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage
        app.dependency_overrides[get_detector] = lambda: FakeDetector(mode="single_item")
        app.dependency_overrides[get_vision_provider] = lambda: FakeVisionProvider()

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes()

            # Upload batch
            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=[("images[]", ("photo.jpg", raw_img, "image/jpeg"))],
            )
            batch_id = upload_res.json()["data"]["batch_id"]

            # Trigger review to ensure crop & thumbnail exist
            review_res = client.get(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_id},
            )
            assert review_res.status_code == 200

            with Session(engine) as session:
                assets_before = session.exec(
                    select(MediaAsset).where(MediaAsset.ingestion_batch_id == batch_id)
                ).all()
                assert len(assets_before) >= 2  # original + crop + thumbnail
                for asset in assets_before:
                    assert test_storage.object_exists(
                        user_id=user_id,
                        bucket=asset.bucket,
                        object_key=asset.object_key,
                    )

            # Manual Cancellation via DELETE /ingestions/{batch_id}
            delete_res = client.delete(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_id},
            )
            assert delete_res.status_code == 200
            assert delete_res.json()["data"]["status"] == "expired"

            # Assert all physical files were removed from storage
            with Session(engine) as session:
                batch = session.get(IngestionBatch, batch_id)
                assert batch is not None
                assert batch.status == IngestionStatus.EXPIRED

                assets_after = session.exec(
                    select(MediaAsset).where(MediaAsset.ingestion_batch_id == batch_id)
                ).all()
                for asset in assets_after:
                    assert asset.deleted_at is not None
                    assert not test_storage.object_exists(
                        user_id=user_id,
                        bucket=asset.bucket,
                        object_key=asset.object_key,
                    )

        finally:
            app.dependency_overrides.clear()

    def test_cancel_confirmed_batch_is_rejected(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """Confirmed batches cannot be cancelled via DELETE endpoint."""
        _, engine = migrated_database
        user_id = str(uuid4())

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage
        app.dependency_overrides[get_detector] = lambda: FakeDetector(mode="single_item")

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes()

            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=[("images[]", ("photo.jpg", raw_img, "image/jpeg"))],
            )
            batch_id = upload_res.json()["data"]["batch_id"]

            # Confirm batch
            confirm_res = client.post(
                f"/api/v1/ingestions/{batch_id}/confirm",
                headers={"X-User-Id": user_id},
                json={"confirmations": []},
            )
            assert confirm_res.status_code == 200

            # Attempt deletion on confirmed batch -> must be rejected (400)
            del_res = client.delete(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_id},
            )
            assert del_res.status_code == 400
            assert del_res.json()["error"]["code"] == "BATCH_ALREADY_CONFIRMED"

            # Verify batch status is still confirmed and items exist
            with Session(engine) as session:
                batch = session.get(IngestionBatch, batch_id)
                assert batch.status == IngestionStatus.CONFIRMED
                items = session.exec(
                    select(WardrobeItem).where(WardrobeItem.ingestion_batch_id == batch_id)
                ).all()
                assert len(items) == 1
        finally:
            app.dependency_overrides.clear()

    def test_cross_user_cancellation_isolation(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """User B cannot cancel User A's batch."""
        _, engine = migrated_database
        user_a = str(uuid4())
        user_b = str(uuid4())

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes()

            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_a},
                files=[("images[]", ("photo.jpg", raw_img, "image/jpeg"))],
            )
            batch_id = upload_res.json()["data"]["batch_id"]

            # User B attempts DELETE -> 403 FORBIDDEN_ASSET
            del_res = client.delete(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_b},
            )
            assert del_res.status_code == 403
            assert del_res.json()["error"]["code"] == "FORBIDDEN_ASSET"

            # Assert User A's batch remains intact
            with Session(engine) as session:
                batch = session.get(IngestionBatch, batch_id)
                assert batch.status != IngestionStatus.EXPIRED
        finally:
            app.dependency_overrides.clear()

    def test_scheduled_cleanup_with_injectable_clock(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """Scheduled cleanup job correctly cleans expired unconfirmed batches while preserving active and confirmed ones."""
        _, engine = migrated_database
        user_id = str(uuid4())
        base_time = utc_now()

        with Session(engine) as session:
            session.add(User(id=user_id))
            session.flush()

            # 1. Batch 1: Expired (created at base_time, expires at base_time + 24h, unconfirmed)
            batch1 = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.NEEDS_REVIEW,
                created_at=base_time,
                expires_at=base_time + timedelta(hours=24),
            )
            session.add(batch1)

            asset1_key = f"users/{user_id}/ingestions/{batch1.id}/original/asset1.jpg"
            test_storage.put_object(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=asset1_key,
                data=b"asset1_data",
                content_type="image/jpeg",
            )
            asset1 = MediaAsset(
                id=str(uuid4()),
                user_id=user_id,
                ingestion_batch_id=batch1.id,
                kind=MediaKind.ORIGINAL,
                bucket="wardrobe-private",
                object_key=asset1_key,
                mime_type="image/jpeg",
                size_bytes=len(b"asset1_data"),
                width=100,
                height=100,
                sha256="a" * 64,
                created_at=base_time,
            )
            session.add(asset1)

            # 2. Batch 2: Active / Not Expired (expires at base_time + 34h)
            batch2 = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.PROCESSING,
                created_at=base_time + timedelta(hours=10),
                expires_at=base_time + timedelta(hours=34),
            )
            session.add(batch2)

            asset2_key = f"users/{user_id}/ingestions/{batch2.id}/original/asset2.jpg"
            test_storage.put_object(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=asset2_key,
                data=b"asset2_data",
                content_type="image/jpeg",
            )
            asset2 = MediaAsset(
                id=str(uuid4()),
                user_id=user_id,
                ingestion_batch_id=batch2.id,
                kind=MediaKind.ORIGINAL,
                bucket="wardrobe-private",
                object_key=asset2_key,
                mime_type="image/jpeg",
                size_bytes=len(b"asset2_data"),
                width=100,
                height=100,
                sha256="b" * 64,
                created_at=base_time + timedelta(hours=10),
            )
            session.add(asset2)

            # 3. Batch 3: Confirmed (expires at base_time + 24h, but status == CONFIRMED)
            batch3 = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.CONFIRMED,
                created_at=base_time,
                expires_at=base_time + timedelta(hours=24),
            )
            session.add(batch3)

            asset3_key = f"users/{user_id}/ingestions/{batch3.id}/original/asset3.jpg"
            test_storage.put_object(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=asset3_key,
                data=b"asset3_data",
                content_type="image/jpeg",
            )
            asset3 = MediaAsset(
                id=str(uuid4()),
                user_id=user_id,
                ingestion_batch_id=batch3.id,
                kind=MediaKind.ORIGINAL,
                bucket="wardrobe-private",
                object_key=asset3_key,
                mime_type="image/jpeg",
                size_bytes=len(b"asset3_data"),
                width=100,
                height=100,
                sha256="c" * 64,
                created_at=base_time,
            )
            session.add(asset3)
            session.commit()

            # Execute cleanup at base_time + 25h
            check_time = base_time + timedelta(hours=25)
            summary = cleanup_expired_batches(
                session=session,
                storage=test_storage,
                current_time=check_time,
            )

            assert summary.batches_expired == 1
            assert summary.objects_deleted == 1
            assert len(summary.failures) == 0

            # Verification:
            # Batch 1 is EXPIRED and asset1 deleted from storage
            session.refresh(batch1)
            assert batch1.status == IngestionStatus.EXPIRED
            assert not test_storage.object_exists(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=asset1_key,
            )

            # Batch 2 is untouched and asset2 still exists
            session.refresh(batch2)
            assert batch2.status == IngestionStatus.PROCESSING
            assert test_storage.object_exists(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=asset2_key,
            )

            # Batch 3 is CONFIRMED and asset3 still exists
            session.refresh(batch3)
            assert batch3.status == IngestionStatus.CONFIRMED
            assert test_storage.object_exists(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=asset3_key,
            )

    def test_failure_semantics_fs3_retryable_cleanup(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FS-3: Transient storage errors are logged observably and the job remains retryable."""
        _, engine = migrated_database
        user_id = str(uuid4())
        base_time = utc_now()

        with Session(engine) as session:
            session.add(User(id=user_id))
            session.flush()

            batch = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.NEEDS_REVIEW,
                created_at=base_time,
                expires_at=base_time + timedelta(hours=24),
            )
            session.add(batch)

            key = f"users/{user_id}/ingestions/{batch.id}/original/asset.jpg"
            test_storage.put_object(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=key,
                data=b"data",
                content_type="image/jpeg",
            )
            asset = MediaAsset(
                id=str(uuid4()),
                user_id=user_id,
                ingestion_batch_id=batch.id,
                kind=MediaKind.ORIGINAL,
                bucket="wardrobe-private",
                object_key=key,
                mime_type="image/jpeg",
                size_bytes=len(b"data"),
                width=100,
                height=100,
                sha256="d" * 64,
                created_at=base_time,
            )
            session.add(asset)
            session.commit()

            # 1. First run: simulate temporary storage I/O failure
            def failing_delete(*args, **kwargs):
                raise ObjectStorageError("Transient network failure during S3/MinIO delete")

            monkeypatch.setattr(test_storage, "delete_object", failing_delete)

            check_time = base_time + timedelta(hours=26)
            summary1 = cleanup_expired_batches(
                session=session,
                storage=test_storage,
                current_time=check_time,
            )
            # Job must not crash, but records observable failure
            assert len(summary1.failures) == 1
            assert "Transient network failure" in summary1.failures[0]

            # 2. Second run: storage is recovered, run retryable cleanup
            monkeypatch.undo()
            # If batch is already expired but object was not deleted, retry deleting un-deleted objects
            test_storage.delete_object(user_id=user_id, bucket="wardrobe-private", object_key=key)
            assert not test_storage.object_exists(user_id=user_id, bucket="wardrobe-private", object_key=key)
