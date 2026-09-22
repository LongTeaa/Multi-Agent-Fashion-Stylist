from __future__ import annotations

from datetime import timedelta
from uuid import uuid4
import pytest
from sqlmodel import Session

from app.models.entities import (
    DetectionStatus,
    IngestionBatch,
    IngestionDetection,
    IngestionStatus,
    MediaAsset,
    MediaKind,
    User,
    utc_now,
)
from app.schemas.common import ForbiddenAssetError, ItemNotFoundError
from app.services.ingestion_service import get_batch_review


def test_get_batch_review_returns_original_media_url(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    batch_id = str(uuid4())
    original_asset_id = str(uuid4())
    crop_asset_id = str(uuid4())
    det_id = str(uuid4())

    with Session(engine) as session:
        user = User(id=user_id, email=f"{user_id}@example.com", name="Review Tester")
        session.add(user)
        session.flush()

        batch = IngestionBatch(
            id=batch_id,
            user_id=user_id,
            status=IngestionStatus.NEEDS_REVIEW,
            expires_at=utc_now() + timedelta(hours=24),
        )
        session.add(batch)
        session.flush()

        original_asset = MediaAsset(
            id=original_asset_id,
            user_id=user_id,
            ingestion_batch_id=batch_id,
            kind=MediaKind.ORIGINAL,
            bucket="wardrobe-raw",
            object_key=f"users/{user_id}/ingestion/{batch_id}/orig.jpg",
            mime_type="image/jpeg",
            size_bytes=1024,
            width=800,
            height=600,
            sha256="a" * 64,
        )
        session.add(original_asset)

        crop_asset = MediaAsset(
            id=crop_asset_id,
            user_id=user_id,
            ingestion_batch_id=batch_id,
            kind=MediaKind.CROP,
            bucket="wardrobe-items",
            object_key=f"users/{user_id}/items/crop.jpg",
            mime_type="image/jpeg",
            size_bytes=512,
            width=400,
            height=300,
            sha256="b" * 64,
        )
        session.add(crop_asset)
        session.flush()

        detection = IngestionDetection(
            id=det_id,
            user_id=user_id,
            ingestion_batch_id=batch_id,
            crop_media_asset_id=crop_asset_id,
            bounding_box=(0.1, 0.1, 0.9, 0.9),
            proposed_attributes={"category": "top", "sub_category": "shirt"},
            field_confidence={"category": 0.95},
            status=DetectionStatus.PROPOSED,
        )
        session.add(detection)
        session.commit()

        review = get_batch_review(
            session=session,
            batch_id=batch_id,
            user_id=user_id,
        )

        assert review.batch_id == batch_id
        assert review.original_media_url == f"/api/v1/media/{original_asset_id}"
        assert len(review.detections) == 1
        assert review.detections[0].detection_id == det_id
        assert review.detections[0].crop_url == f"/api/v1/media/{crop_asset_id}"


def test_get_batch_review_without_original_media_returns_none(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    batch_id = str(uuid4())

    with Session(engine) as session:
        user = User(id=user_id, email=f"{user_id}@example.com", name="Review Tester")
        session.add(user)
        session.flush()

        batch = IngestionBatch(
            id=batch_id,
            user_id=user_id,
            status=IngestionStatus.NEEDS_REVIEW,
            expires_at=utc_now() + timedelta(hours=24),
        )
        session.add(batch)
        session.commit()

        review = get_batch_review(
            session=session,
            batch_id=batch_id,
            user_id=user_id,
        )

        assert review.batch_id == batch_id
        assert review.original_media_url is None
        assert len(review.detections) == 0


def test_get_batch_review_non_existent_batch_raises_item_not_found(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = str(uuid4())
    fake_batch_id = str(uuid4())

    with Session(engine) as session:
        with pytest.raises(ItemNotFoundError) as exc_info:
            get_batch_review(
                session=session,
                batch_id=fake_batch_id,
                user_id=user_id,
            )
        assert "Không tìm thấy lượt tải lên này" in str(exc_info.value.message)


def test_get_batch_review_unauthorized_user_raises_forbidden(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    owner_id = str(uuid4())
    other_user_id = str(uuid4())
    batch_id = str(uuid4())

    with Session(engine) as session:
        owner = User(id=owner_id, email=f"{owner_id}@example.com", name="Owner")
        other = User(id=other_user_id, email=f"{other_user_id}@example.com", name="Other")
        session.add_all([owner, other])
        session.flush()

        batch = IngestionBatch(
            id=batch_id,
            user_id=owner_id,
            status=IngestionStatus.NEEDS_REVIEW,
            expires_at=utc_now() + timedelta(hours=24),
        )
        session.add(batch)
        session.commit()

        with pytest.raises(ForbiddenAssetError):
            get_batch_review(
                session=session,
                batch_id=batch_id,
                user_id=other_user_id,
            )
