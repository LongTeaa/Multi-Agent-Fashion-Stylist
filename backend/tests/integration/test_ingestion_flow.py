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
    DetectionStatus,
    IngestionBatch,
    IngestionDetection,
    IngestionStatus,
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    User,
    WardrobeItem,
    utc_now,
)
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider


def create_test_image_bytes(
    format_name: str = "JPEG",
    size: tuple[int, int] = (200, 200),
    color: tuple[int, int, int] = (200, 100, 50),
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


class TestIngestionFlowIntegration:
    def test_multi_item_produces_two_separately_confirmed_wardrobe_items(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """VERIFICATION GATE TEST:

        A multi-item image can produce at least two separately confirmed WardrobeItem records
        without exposing the original object publicly.
        """
        _, engine = migrated_database
        user_id = str(uuid4())
        detector = FakeDetector(mode="multi_item")
        vision_provider = FakeVisionProvider(scenario="golden_polo")

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage
        app.dependency_overrides[get_detector] = lambda: detector
        app.dependency_overrides[get_vision_provider] = lambda: vision_provider

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes("JPEG", (300, 300))

            # 1. Step 1: Upload multi-item image
            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=[("images[]", ("multi_outfit.jpg", raw_img, "image/jpeg"))],
            )
            assert upload_res.status_code == 202
            upload_data = upload_res.json()["data"]
            batch_id = upload_data["batch_id"]
            assert upload_data["status"] == "processing"

            # 2. Step 2: Retrieve Review API
            review_res = client.get(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_id},
            )
            assert review_res.status_code == 200
            review_data = review_res.json()["data"]
            assert review_data["batch_id"] == batch_id
            assert review_data["status"] == "needs_review"
            assert review_data["input_kind"] == "multi_item"
            assert len(review_data["detections"]) == 2

            # Assert Invariant: All crop URLs are proxied through /api/v1/media/
            # and NO raw MinIO or bucket paths are exposed!
            for det in review_data["detections"]:
                assert det["crop_url"].startswith("/api/v1/media/")
                assert "minio" not in det["crop_url"]
                assert "wardrobe-private" not in det["crop_url"]

            # 3. Assert INVARIANT: Zero WardrobeItem records exist before explicit confirmation
            with Session(engine) as session:
                items_before_confirm = session.exec(select(WardrobeItem)).all()
                assert len(items_before_confirm) == 0

                # Check detections are in 'proposed' state
                detections = session.exec(
                    select(IngestionDetection).where(IngestionDetection.ingestion_batch_id == batch_id)
                ).all()
                assert len(detections) == 2
                for d in detections:
                    assert d.status == DetectionStatus.PROPOSED

            # 4. Step 3: Confirm the detections
            confirm_payload = {
                "idempotency_token": "test-token-123",
                "confirmations": [
                    {
                        "detection_id": review_data["detections"][0]["detection_id"],
                        "accepted": True,
                        "custom_attributes": {"style": "casual"},
                    },
                    {
                        "detection_id": review_data["detections"][1]["detection_id"],
                        "accepted": True,
                        "custom_attributes": {"category": "bottom", "sub_category": "trousers"},
                    },
                ],
            }

            confirm_res = client.post(
                f"/api/v1/ingestions/{batch_id}/confirm",
                headers={"X-User-Id": user_id},
                json=confirm_payload,
            )
            assert confirm_res.status_code == 200
            confirm_data = confirm_res.json()["data"]
            assert confirm_data["status"] == "confirmed"
            confirmed_ids = confirm_data["wardrobe_item_ids"]
            assert len(confirmed_ids) == 2
            assert confirmed_ids[0] != confirmed_ids[1]

            # 5. Verify database records: exactly 2 distinct confirmed items exist with ItemMedia links
            with Session(engine) as session:
                persisted_items = session.exec(
                    select(WardrobeItem).where(WardrobeItem.user_id == user_id)
                ).all()
                assert len(persisted_items) == 2
                for item in persisted_items:
                    assert item.is_user_confirmed is True
                    assert item.ingestion_batch_id == batch_id

                    # Check ItemMedia junction has both PRIMARY (crop) and THUMBNAIL roles
                    item_media_links = session.exec(
                        select(ItemMedia).where(ItemMedia.wardrobe_item_id == item.id)
                    ).all()
                    assert len(item_media_links) == 2
                    roles = {link.role for link in item_media_links}
                    assert roles == {ItemMediaRole.PRIMARY, ItemMediaRole.THUMBNAIL}

                    # Assert item.id matches the physical storage key path
                    assert test_storage.object_exists(
                        user_id=user_id,
                        bucket="wardrobe-private",
                        object_key=f"users/{user_id}/items/{item.id}/crop/v1.png",
                    )
                    assert test_storage.object_exists(
                        user_id=user_id,
                        bucket="wardrobe-thumbnails",
                        object_key=f"users/{user_id}/items/{item.id}/thumbnail/v1.webp",
                    )

                # Verify updated batch and detections status
                batch_rec = session.get(IngestionBatch, batch_id)
                assert batch_rec is not None
                assert batch_rec.status == IngestionStatus.CONFIRMED

            # 6. Step 4: IDEMPOTENCY TEST: Submitting the same confirmation again
            retry_res = client.post(
                f"/api/v1/ingestions/{batch_id}/confirm",
                headers={"X-User-Id": user_id},
                json=confirm_payload,
            )
            assert retry_res.status_code == 200
            retry_data = retry_res.json()["data"]
            assert set(retry_data["wardrobe_item_ids"]) == set(confirmed_ids)

            # Assert no duplicate WardrobeItem records created!
            with Session(engine) as session:
                total_items_after_retry = session.exec(
                    select(WardrobeItem).where(WardrobeItem.user_id == user_id)
                ).all()
                assert len(total_items_after_retry) == 2

        finally:
            app.dependency_overrides.clear()

    def test_cross_user_isolation_for_review_and_confirm(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """Negative security test: User B cannot view or confirm User A's batch."""
        _, engine = migrated_database
        user_a = str(uuid4())
        user_b = str(uuid4())

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes("JPEG", (150, 150))

            # User A uploads
            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_a},
                files=[("images[]", ("photo.jpg", raw_img, "image/jpeg"))],
            )
            assert upload_res.status_code == 202
            batch_id = upload_res.json()["data"]["batch_id"]

            # User B attempts to access review of User A's batch -> 403 FORBIDDEN_ASSET
            review_b = client.get(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_b},
            )
            assert review_b.status_code == 403
            assert review_b.json()["error"]["code"] == "FORBIDDEN_ASSET"

            # User B attempts to confirm User A's batch -> 403 FORBIDDEN_ASSET
            confirm_b = client.post(
                f"/api/v1/ingestions/{batch_id}/confirm",
                headers={"X-User-Id": user_b},
                json={"confirmations": [{"detection_id": str(uuid4()), "accepted": True}]},
            )
            assert confirm_b.status_code == 403
            assert confirm_b.json()["error"]["code"] == "FORBIDDEN_ASSET"
        finally:
            app.dependency_overrides.clear()

    def test_partial_confirmation_rejection_scenario(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """When 1 detection is accepted and 1 is rejected, only 1 WardrobeItem is created."""
        _, engine = migrated_database
        user_id = str(uuid4())
        detector = FakeDetector(mode="multi_item")

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage
        app.dependency_overrides[get_detector] = lambda: detector

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes("JPEG", (150, 150))

            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=[("images[]", ("photo.jpg", raw_img, "image/jpeg"))],
            )
            batch_id = upload_res.json()["data"]["batch_id"]

            review_res = client.get(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_id},
            )
            detections = review_res.json()["data"]["detections"]
            assert len(detections) == 2

            # Accept first, reject second
            confirm_payload = {
                "confirmations": [
                    {"detection_id": detections[0]["detection_id"], "accepted": True},
                    {"detection_id": detections[1]["detection_id"], "accepted": False},
                ]
            }
            confirm_res = client.post(
                f"/api/v1/ingestions/{batch_id}/confirm",
                headers={"X-User-Id": user_id},
                json=confirm_payload,
            )
            assert confirm_res.status_code == 200
            assert len(confirm_res.json()["data"]["wardrobe_item_ids"]) == 1

            with Session(engine) as session:
                # Exactly 1 WardrobeItem in DB
                items = session.exec(select(WardrobeItem).where(WardrobeItem.user_id == user_id)).all()
                assert len(items) == 1

                # 1 ACCEPTED and 1 REJECTED detection
                det1 = session.get(IngestionDetection, detections[0]["detection_id"])
                assert det1 is not None and det1.status == DetectionStatus.ACCEPTED
                det2 = session.get(IngestionDetection, detections[1]["detection_id"])
                assert det2 is not None and det2.status == DetectionStatus.REJECTED
        finally:
            app.dependency_overrides.clear()

    def test_low_quality_scenario_generates_warnings_and_flags_low_confidence(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """SCENARIO 2: Low-quality image produces quality warnings and flags low-confidence fields (< 70%)."""
        _, engine = migrated_database
        user_id = str(uuid4())
        detector = FakeDetector(mode="low_quality")
        vision_provider = FakeVisionProvider(scenario="low_confidence")

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage
        app.dependency_overrides[get_detector] = lambda: detector
        app.dependency_overrides[get_vision_provider] = lambda: vision_provider

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes("JPEG", (120, 120))

            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=[("images[]", ("blurry.jpg", raw_img, "image/jpeg"))],
            )
            assert upload_res.status_code == 202
            batch_id = upload_res.json()["data"]["batch_id"]

            review_res = client.get(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_id},
            )
            assert review_res.status_code == 200
            review_data = review_res.json()["data"]
            assert review_data["status"] == "needs_review"

            # Check quality warnings include low quality & low confidence alerts
            warnings = review_data["quality_warnings"]
            assert any("thiếu sáng" in w or "bị mờ" in w for w in warnings)
            assert any("< 70%" in w for w in warnings)

            # Check field confidence flags
            detections = review_data["detections"]
            assert len(detections) == 1
            confidences = detections[0]["field_confidence"]
            assert confidences.get("pattern", 1.0) < 0.70
            assert confidences.get("material", 1.0) < 0.70

            # User corrects the low-confidence fields during confirm
            confirm_payload = {
                "confirmations": [
                    {
                        "detection_id": detections[0]["detection_id"],
                        "accepted": True,
                        "custom_attributes": {
                            "pattern": "striped",
                            "material": "linen",
                        },
                    }
                ]
            }
            confirm_res = client.post(
                f"/api/v1/ingestions/{batch_id}/confirm",
                headers={"X-User-Id": user_id},
                json=confirm_payload,
            )
            assert confirm_res.status_code == 200
            item_ids = confirm_res.json()["data"]["wardrobe_item_ids"]
            assert len(item_ids) == 1

            with Session(engine) as session:
                item = session.get(WardrobeItem, item_ids[0])
                assert item is not None
                assert item.pattern == "striped"
                assert item.material == "linen"

        finally:
            app.dependency_overrides.clear()

    def test_timeout_scenario_degrades_gracefully_to_manual_review(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """SCENARIO 4: Vision detector or provider timeout degrades gracefully to manual review without crashing."""
        _, engine = migrated_database
        user_id = str(uuid4())
        detector = FakeDetector(mode="timeout")

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage
        app.dependency_overrides[get_detector] = lambda: detector

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes("JPEG", (150, 150))

            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=[("images[]", ("photo.jpg", raw_img, "image/jpeg"))],
            )
            assert upload_res.status_code == 202
            batch_id = upload_res.json()["data"]["batch_id"]

            review_res = client.get(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_id},
            )
            assert review_res.status_code == 200
            review_data = review_res.json()["data"]

            # Degrades to needs_review for manual input, does not hang or crash
            assert review_data["status"] == "needs_review"
            warnings = review_data["quality_warnings"]
            assert any("timeout" in w.lower() or "quá thời gian" in w for w in warnings)

        finally:
            app.dependency_overrides.clear()

    def test_provider_500_error_scenario_fails_gracefully_and_cleans_up_transient_crops(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """SCENARIO 5: Downstream provider 500 error fails batch cleanly and deletes transient crops from storage."""
        _, engine = migrated_database
        user_id = str(uuid4())
        detector = FakeDetector(mode="single_item")
        vision_provider = FakeVisionProvider(scenario="provider_error")

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage
        app.dependency_overrides[get_detector] = lambda: detector
        app.dependency_overrides[get_vision_provider] = lambda: vision_provider

        try:
            client = TestClient(app)
            raw_img = create_test_image_bytes("JPEG", (150, 150))

            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=[("images[]", ("photo.jpg", raw_img, "image/jpeg"))],
            )
            assert upload_res.status_code == 202
            batch_id = upload_res.json()["data"]["batch_id"]

            review_res = client.get(
                f"/api/v1/ingestions/{batch_id}",
                headers={"X-User-Id": user_id},
            )
            assert review_res.status_code == 200
            review_data = review_res.json()["data"]

            # Batch status is failed
            assert review_data["status"] == "failed"
            warnings = review_data["quality_warnings"]
            assert any("thất bại" in w or "không khả dụng" in w for w in warnings)

            # Assert transient crop and thumbnail files were cleaned up from storage!
            with Session(engine) as session:
                crop_assets = session.exec(
                    select(MediaAsset).where(
                        MediaAsset.ingestion_batch_id == batch_id,
                        MediaAsset.kind.in_([MediaKind.CROP, MediaKind.THUMBNAIL]),
                    )
                ).all()
                # DB transaction rollback means zero crop/thumb records exist
                assert len(crop_assets) == 0

                # Original image is still recorded
                original_assets = session.exec(
                    select(MediaAsset).where(
                        MediaAsset.ingestion_batch_id == batch_id,
                        MediaAsset.kind == MediaKind.ORIGINAL,
                    )
                ).all()
                assert len(original_assets) == 1

        finally:
            app.dependency_overrides.clear()


class TestConfirmationStateAndSecurityIntegrity:
    """Integration tests verifying confirmation state guards, cross-batch security, and rollback atomicity."""

    def test_confirm_processing_batch_returns_409(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())
        batch_id = str(uuid4())
        now = utc_now()

        with Session(engine) as session:
            session.add(User(id=user_id))
            session.flush()
            session.add(
                IngestionBatch(
                    id=batch_id,
                    user_id=user_id,
                    status=IngestionStatus.PROCESSING,
                    created_at=now,
                    expires_at=now + timedelta(hours=24),
                )
            )
            session.commit()

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            res = client.post(
                f"/api/v1/ingestions/{batch_id}/confirm",
                headers={"X-User-Id": user_id},
                json={"confirmations": [{"detection_id": str(uuid4()), "accepted": True}]},
            )
            assert res.status_code == 409
            assert res.json()["error"]["code"] == "INGESTION_NOT_READY"

            with Session(engine) as session:
                batch = session.get(IngestionBatch, batch_id)
                assert batch.status == IngestionStatus.PROCESSING
        finally:
            app.dependency_overrides.clear()

    def test_confirm_failed_or_expired_batch_returns_409(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())
        now = utc_now()

        with Session(engine) as session:
            session.add(User(id=user_id))
            session.flush()
            failed_batch = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.FAILED,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            expired_batch = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.EXPIRED,
                created_at=now - timedelta(hours=25),
                expires_at=now - timedelta(hours=1),
            )
            session.add(failed_batch)
            session.add(expired_batch)
            session.commit()

            failed_id = failed_batch.id
            expired_id = expired_batch.id

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            res_failed = client.post(
                f"/api/v1/ingestions/{failed_id}/confirm",
                headers={"X-User-Id": user_id},
                json={"confirmations": [{"detection_id": str(uuid4()), "accepted": True}]},
            )
            assert res_failed.status_code == 409
            assert res_failed.json()["error"]["code"] == "INGESTION_NOT_READY"

            res_expired = client.post(
                f"/api/v1/ingestions/{expired_id}/confirm",
                headers={"X-User-Id": user_id},
                json={"confirmations": [{"detection_id": str(uuid4()), "accepted": True}]},
            )
            assert res_expired.status_code == 409
            assert res_expired.json()["error"]["code"] == "INGESTION_NOT_READY"
        finally:
            app.dependency_overrides.clear()

    def test_confirm_detection_from_another_batch_returns_422(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())
        now = utc_now()

        with Session(engine) as session:
            session.add(User(id=user_id))
            session.flush()
            batch_a = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.NEEDS_REVIEW,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            batch_b = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.NEEDS_REVIEW,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            session.add(batch_a)
            session.add(batch_b)
            session.flush()

            det_b = IngestionDetection(
                id=str(uuid4()),
                user_id=user_id,
                ingestion_batch_id=batch_b.id,
                bounding_box=[0.1, 0.1, 0.9, 0.9],
                proposed_attributes={"category": "top"},
                field_confidence={"category": 0.95},
                status=DetectionStatus.PROPOSED,
                created_at=now,
            )
            session.add(det_b)
            session.commit()

            batch_a_id = batch_a.id
            det_b_id = det_b.id

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            # Attempt to confirm batch A with detection from batch B
            res = client.post(
                f"/api/v1/ingestions/{batch_a_id}/confirm",
                headers={"X-User-Id": user_id},
                json={"confirmations": [{"detection_id": det_b_id, "accepted": True}]},
            )
            assert res.status_code == 422
            assert res.json()["error"]["code"] == "VALIDATION_ERROR"

            # Neither batch should be confirmed
            with Session(engine) as session:
                assert session.get(IngestionBatch, batch_a_id).status == IngestionStatus.NEEDS_REVIEW
                assert session.get(IngestionDetection, det_b_id).status == DetectionStatus.PROPOSED
        finally:
            app.dependency_overrides.clear()

    def test_confirm_cross_user_detection_returns_403(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_a = str(uuid4())
        user_b = str(uuid4())
        now = utc_now()

        with Session(engine) as session:
            session.add(User(id=user_a))
            session.add(User(id=user_b))
            session.flush()
            batch_a = IngestionBatch(
                id=str(uuid4()),
                user_id=user_a,
                status=IngestionStatus.NEEDS_REVIEW,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            batch_b = IngestionBatch(
                id=str(uuid4()),
                user_id=user_b,
                status=IngestionStatus.NEEDS_REVIEW,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            session.add(batch_a)
            session.add(batch_b)
            session.flush()

            det_a = IngestionDetection(
                id=str(uuid4()),
                user_id=user_a,
                ingestion_batch_id=batch_a.id,
                bounding_box=[0.1, 0.1, 0.9, 0.9],
                proposed_attributes={"category": "top"},
                field_confidence={"category": 0.95},
                status=DetectionStatus.PROPOSED,
                created_at=now,
            )
            session.add(det_a)
            session.commit()

            batch_b_id = batch_b.id
            det_a_id = det_a.id

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            # User B attempts to confirm batch B using User A's detection
            res = client.post(
                f"/api/v1/ingestions/{batch_b_id}/confirm",
                headers={"X-User-Id": user_b},
                json={"confirmations": [{"detection_id": det_a_id, "accepted": True}]},
            )
            assert res.status_code == 403
            assert res.json()["error"]["code"] == "FORBIDDEN_ASSET"

            with Session(engine) as session:
                items = session.exec(select(WardrobeItem)).all()
                assert len(items) == 0
        finally:
            app.dependency_overrides.clear()

    def test_confirm_rollback_on_failure_leaves_batch_reviewable(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())
        now = utc_now()

        with Session(engine) as session:
            session.add(User(id=user_id))
            session.flush()
            batch = IngestionBatch(
                id=str(uuid4()),
                user_id=user_id,
                status=IngestionStatus.NEEDS_REVIEW,
                created_at=now,
                expires_at=now + timedelta(hours=24),
            )
            session.add(batch)
            session.flush()

            det1 = IngestionDetection(
                id=str(uuid4()),
                user_id=user_id,
                ingestion_batch_id=batch.id,
                bounding_box=[0.1, 0.1, 0.4, 0.4],
                proposed_attributes={"category": "top"},
                field_confidence={"category": 0.9},
                status=DetectionStatus.PROPOSED,
                created_at=now,
            )
            det2 = IngestionDetection(
                id=str(uuid4()),
                user_id=user_id,
                ingestion_batch_id=batch.id,
                bounding_box=[0.5, 0.5, 0.9, 0.9],
                proposed_attributes={"category": "bottom"},
                field_confidence={"category": 0.9},
                status=DetectionStatus.PROPOSED,
                created_at=now,
            )
            session.add(det1)
            session.add(det2)
            session.commit()

            batch_id = batch.id
            det1_id = det1.id
            det2_id = det2.id

        app.dependency_overrides[get_db_session] = lambda: Session(engine)
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        # Simulate a crash during the loop when processing det2
        original_add = Session.add
        call_count = 0

        def failing_add(sess_self, instance):
            nonlocal call_count
            if isinstance(instance, WardrobeItem):
                call_count += 1
                if call_count >= 2:
                    raise RuntimeError("Simulated database crash on second wardrobe item insert")
            return original_add(sess_self, instance)

        monkeypatch.setattr(Session, "add", failing_add)

        try:
            client = TestClient(app, raise_server_exceptions=False)
            res = client.post(
                f"/api/v1/ingestions/{batch_id}/confirm",
                headers={"X-User-Id": user_id},
                json={
                    "confirmations": [
                        {"detection_id": det1_id, "accepted": True},
                        {"detection_id": det2_id, "accepted": True},
                    ]
                },
            )
            assert res.status_code == 500

            # Verify atomicity: 0 items created, batch remains in NEEDS_REVIEW
            with Session(engine) as session:
                db_batch = session.get(IngestionBatch, batch_id)
                assert db_batch.status == IngestionStatus.NEEDS_REVIEW
                items = session.exec(select(WardrobeItem).where(WardrobeItem.ingestion_batch_id == batch_id)).all()
                assert len(items) == 0
                db_det1 = session.get(IngestionDetection, det1_id)
                # Detections status changes rolled back
                assert db_det1.status == DetectionStatus.PROPOSED
        finally:
            app.dependency_overrides.clear()
