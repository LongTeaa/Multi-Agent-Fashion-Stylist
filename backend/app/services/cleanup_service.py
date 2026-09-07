from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, select

from app.models.entities import (
    IngestionBatch,
    IngestionStatus,
    ItemMedia,
    MediaAsset,
    utc_now,
)
from app.repositories.object_storage import ObjectNotFoundError, ObjectStorage
from app.schemas.common import AppException, ForbiddenAssetError, ItemNotFoundError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupSummary:
    batches_expired: int
    objects_deleted: int
    failures: list[str] = field(default_factory=list)


def cancel_ingestion_batch(
    *,
    session: Session,
    storage: ObjectStorage,
    batch_id: str,
    user_id: str,
) -> IngestionBatch:
    """Manually cancel an unconfirmed ingestion batch and delete its transient files.

    Raises:
        ItemNotFoundError: If batch does not exist.
        ForbiddenAssetError: If batch belongs to a different user.
        AppException(400): If batch has already been confirmed.
    """
    batch = session.get(IngestionBatch, batch_id)
    if batch is None:
        raise ItemNotFoundError("Không tìm thấy lượt tải lên này.")

    if batch.user_id != user_id:
        raise ForbiddenAssetError()

    if batch.status == IngestionStatus.CONFIRMED:
        raise AppException(
            message="Không thể hủy lượt tải lên đã được xác nhận vào tủ đồ.",
            status_code=400,
            code="BATCH_ALREADY_CONFIRMED",
        )

    if batch.status == IngestionStatus.EXPIRED:
        return batch

    now = utc_now()
    assets = session.exec(
        select(MediaAsset).where(MediaAsset.ingestion_batch_id == batch_id)
    ).all()

    for asset in assets:
        if asset.deleted_at is None:
            try:
                storage.delete_object(
                    user_id=asset.user_id,
                    bucket=asset.bucket,
                    object_key=asset.object_key,
                )
            except ObjectNotFoundError:
                pass
            except Exception as del_err:
                logger.warning("Failed to delete transient file %s: %s", asset.object_key, del_err)

            asset.deleted_at = now
            session.add(asset)

    batch.status = IngestionStatus.EXPIRED
    session.add(batch)
    session.commit()
    session.refresh(batch)
    return batch


def cleanup_expired_batches(
    *,
    session: Session,
    storage: ObjectStorage,
    current_time: datetime | None = None,
) -> CleanupSummary:
    """Scan and clean up all unconfirmed batches older than 24 hours.

    Enforces Failure Semantics FS-3:
    - Transient object deletion errors do not abort the cleanup job.
    - Errors are logged observably and the job remains safely retryable.
    - Confirmed batches and assets linked to WardrobeItem are strictly protected.
    """
    now = current_time or utc_now()

    # Find unconfirmed batches that have expired
    expired_batches = session.exec(
        select(IngestionBatch).where(
            IngestionBatch.status != IngestionStatus.CONFIRMED,
            IngestionBatch.status != IngestionStatus.EXPIRED,
            IngestionBatch.expires_at <= now,
        )
    ).all()

    batches_expired = 0
    objects_deleted = 0
    failures: list[str] = []

    for batch in expired_batches:
        assets = session.exec(
            select(MediaAsset).where(MediaAsset.ingestion_batch_id == batch.id)
        ).all()

        for asset in assets:
            if asset.deleted_at is not None:
                continue

            # Defense-in-depth: Never delete an asset linked to an active WardrobeItem
            linked_item = session.exec(
                select(ItemMedia).where(ItemMedia.media_asset_id == asset.id)
            ).first()
            if linked_item:
                logger.error(
                    "Safety check triggered: Asset %s in unconfirmed batch %s is linked to WardrobeItem %s. Skipping.",
                    asset.id,
                    batch.id,
                    linked_item.wardrobe_item_id,
                )
                continue

            try:
                storage.delete_object(
                    user_id=asset.user_id,
                    bucket=asset.bucket,
                    object_key=asset.object_key,
                )
                objects_deleted += 1
            except ObjectNotFoundError:
                pass
            except Exception as exc:
                err_msg = f"FS-3 Object deletion failed for {asset.object_key}: {exc}"
                logger.error(err_msg)
                failures.append(err_msg)

            asset.deleted_at = now
            session.add(asset)

        batch.status = IngestionStatus.EXPIRED
        session.add(batch)
        session.commit()
        batches_expired += 1

    return CleanupSummary(
        batches_expired=batches_expired,
        objects_deleted=objects_deleted,
        failures=failures,
    )
