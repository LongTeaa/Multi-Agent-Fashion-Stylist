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

    all_cleared = True
    for asset in assets:
        if asset.deleted_at is None:
            try:
                storage.delete_object(
                    user_id=asset.user_id,
                    bucket=asset.bucket,
                    object_key=asset.object_key,
                )
                asset.deleted_at = now
                session.add(asset)
            except ObjectNotFoundError:
                asset.deleted_at = now
                session.add(asset)
            except Exception as del_err:
                logger.warning("Failed to delete transient file %s: %s", asset.object_key, del_err)
                all_cleared = False

    if all_cleared:
        batch.status = IngestionStatus.EXPIRED
    else:
        # If some files failed to delete, ensure batch is eligible for retryable cleanup
        batch.expires_at = min(batch.expires_at, now)
        logger.warning(
            "Batch %s cancelled with partial asset deletion. Retaining unexpired status for retry.",
            batch_id,
        )

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
    - Sets deleted_at ONLY upon successful deletion or confirmed ObjectNotFoundError.
    - Failed deletions leave deleted_at=None and batch remains eligible for next run.
    - Marks batch EXPIRED only when all unprotected transient assets are deleted or absent.
    - Confirmed batches and assets linked to WardrobeItem are strictly protected.
    """
    now = current_time or utc_now()

    # Confirmed batches may still contain transient originals and rejected crops.
    # Include any expired batch with undeleted assets so those unlinked objects can
    # be removed, while preserving media linked to a wardrobe item.
    unlinked_undeleted_asset_batch_ids = select(MediaAsset.ingestion_batch_id).where(
        MediaAsset.deleted_at.is_(None),
        MediaAsset.id.not_in(select(ItemMedia.media_asset_id)),
    )
    expired_batches = session.exec(
        select(IngestionBatch).where(
            IngestionBatch.expires_at <= now,
            (
                (IngestionBatch.status != IngestionStatus.CONFIRMED)
                & (IngestionBatch.status != IngestionStatus.EXPIRED)
            )
            | IngestionBatch.id.in_(unlinked_undeleted_asset_batch_ids),
        ).order_by(IngestionBatch.created_at)
    ).all()

    batches_expired = 0
    objects_deleted = 0
    failures: list[str] = []

    for batch in expired_batches:
        assets = session.exec(
            select(MediaAsset).where(MediaAsset.ingestion_batch_id == batch.id)
        ).all()

        batch_all_cleared = True

        for asset in assets:
            if asset.deleted_at is not None:
                continue

            # Defense-in-depth: Never delete an asset linked to an active WardrobeItem
            linked_item = session.exec(
                select(ItemMedia).where(ItemMedia.media_asset_id == asset.id)
            ).first()
            if linked_item:
                if batch.status != IngestionStatus.CONFIRMED:
                    err_msg = (
                        f"Safety check: asset {asset.id} in unconfirmed batch {batch.id} "
                        f"is linked to wardrobe item {linked_item.wardrobe_item_id}."
                    )
                    logger.error(err_msg)
                    failures.append(err_msg)
                    batch_all_cleared = False
                continue

            try:
                storage.delete_object(
                    user_id=asset.user_id,
                    bucket=asset.bucket,
                    object_key=asset.object_key,
                )
                objects_deleted += 1
                asset.deleted_at = now
                session.add(asset)
            except ObjectNotFoundError:
                # Object is already absent in storage -> treat as successful convergence!
                asset.deleted_at = now
                session.add(asset)
            except Exception as exc:
                err_msg = f"FS-3 Object deletion failed for {asset.object_key}: {exc}"
                logger.error(err_msg)
                failures.append(err_msg)
                batch_all_cleared = False
                # Do NOT set asset.deleted_at! Keep None so it can be retried!

        if batch.status == IngestionStatus.CONFIRMED:
            # Confirmation is a durable domain state. Cleanup only removes its
            # unlinked transient media and never rewrites it to EXPIRED.
            pass
        elif batch_all_cleared:
            if batch.status != IngestionStatus.EXPIRED:
                batch.status = IngestionStatus.EXPIRED
                batches_expired += 1
            session.add(batch)
        else:
            logger.warning(
                "Batch %s has transient assets that failed deletion. Batch remains in %s for subsequent retry.",
                batch.id,
                batch.status,
            )

        session.commit()

    return CleanupSummary(
        batches_expired=batches_expired,
        objects_deleted=objects_deleted,
        failures=failures,
    )
