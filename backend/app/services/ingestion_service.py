from __future__ import annotations

import logging
from datetime import timedelta
from typing import Sequence

from sqlmodel import Session, select
from sqlalchemy.orm.attributes import flag_modified

from app.models.entities import (
    DetectionStatus,
    IngestionBatch,
    IngestionDetection,
    IngestionStatus,
    InputKind,
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    User,
    WardrobeCategory,
    WardrobeItem,
    new_uuid,
    utc_now,
)
from app.repositories.object_storage import ObjectStorage
from app.schemas.common import (
    AppException,
    ForbiddenAssetError,
    ItemNotFoundError,
    ProviderError,
    ValidationError,
)
from app.schemas.ingestion import (
    DetectionConfirmationItem,
    DetectionReviewItem,
    IngestionBatchReviewResponseData,
)
from app.services.crop_engine import crop_item_and_generate_thumbnail
from app.services.providers import (
    DetectorProtocol,
    VisionExtractionResult,
    VisionProviderProtocol,
)
from app.services.upload_validation import ValidatedImage, validate_image_bytes

logger = logging.getLogger(__name__)


def create_ingestion_batch(
    *,
    session: Session,
    storage: ObjectStorage,
    user_id: str,
    raw_files: Sequence[tuple[str, bytes]],
    declared_input_kind: InputKind | None = None,
) -> IngestionBatch:
    """Create an ingestion batch, store raw images privately in ObjectStorage,

    and record the batch and media assets in the database.
    """
    if len(raw_files) < 1 or len(raw_files) > 10:
        raise ValidationError(
            message="Số lượng ảnh tải lên phải từ 1 đến 10 ảnh.",
            details={"count": len(raw_files), "min": 1, "max": 10},
        )

    validated_images: list[ValidatedImage] = []
    for filename, raw_bytes in raw_files:
        validated_img = validate_image_bytes(raw_bytes)
        validated_images.append(validated_img)

    if session.get(User, user_id) is None:
        session.add(User(id=user_id))
        session.flush()

    batch_id = new_uuid()
    now = utc_now()
    batch = IngestionBatch(
        id=batch_id,
        user_id=user_id,
        input_kind=declared_input_kind or InputKind.UNKNOWN,
        status=IngestionStatus.PROCESSING,
        quality_warnings=[],
        created_at=now,
        expires_at=now + timedelta(hours=24),
    )
    session.add(batch)

    uploaded_objects: list[tuple[str, str]] = []
    try:
        for val_img in validated_images:
            asset_id = new_uuid()
            bucket_name = "wardrobe-private"
            object_key = f"users/{user_id}/ingestions/{batch_id}/original/{asset_id}.{val_img.extension}"

            storage.put_object(
                user_id=user_id,
                bucket=bucket_name,
                object_key=object_key,
                data=val_img.raw_bytes,
                content_type=val_img.mime_type,
            )
            uploaded_objects.append((bucket_name, object_key))

            media_asset = MediaAsset(
                id=asset_id,
                user_id=user_id,
                ingestion_batch_id=batch_id,
                kind=MediaKind.ORIGINAL,
                bucket=bucket_name,
                object_key=object_key,
                mime_type=val_img.mime_type,
                size_bytes=val_img.size_bytes,
                width=val_img.width,
                height=val_img.height,
                sha256=val_img.sha256,
                created_at=now,
            )
            session.add(media_asset)

        session.commit()
        session.refresh(batch)
        return batch

    except Exception as exc:
        session.rollback()
        for bucket, key in uploaded_objects:
            try:
                storage.delete_object(user_id=user_id, bucket=bucket, object_key=key)
            except Exception as cleanup_err:
                logger.error(
                    "Compensating cleanup failed for user=%s bucket=%s key=%s: %s",
                    user_id,
                    bucket,
                    key,
                    cleanup_err,
                )

        if isinstance(exc, (AppException, ValidationError)):
            raise exc

        logger.error("Failed to create ingestion batch for user %s: %s", user_id, exc)
        raise AppException(
            message="Không thể xử lý yêu cầu tải ảnh lên. Vui lòng thử lại sau.",
            status_code=500,
            code="INGESTION_UPLOAD_FAILED",
        ) from exc


def process_ingestion_batch(
    *,
    session: Session,
    storage: ObjectStorage,
    detector: DetectorProtocol,
    vision_provider: VisionProviderProtocol,
    batch_id: str,
    user_id: str,
) -> IngestionBatch:
    """Run object detection, crop candidate items, extract vision attributes,

    and persist IngestionDetection records in state `needs_review`.

    INVARIANT: MUST NOT create any WardrobeItem records here.
    """
    batch = session.get(IngestionBatch, batch_id)
    if batch is None:
        raise ItemNotFoundError("Không tìm thấy lượt tải lên này.")
    if batch.user_id != user_id:
        raise ForbiddenAssetError()
    if batch.status != IngestionStatus.PROCESSING:
        return batch

    original_assets = session.exec(
        select(MediaAsset).where(
            MediaAsset.ingestion_batch_id == batch_id,
            MediaAsset.kind == MediaKind.ORIGINAL,
        )
    ).all()

    crop_objects_created: list[tuple[str, str]] = []
    warnings_accumulator: list[str] = list(batch.quality_warnings or [])

    def add_warning(msg: str) -> None:
        if msg not in warnings_accumulator:
            warnings_accumulator.append(msg)

    try:
        for asset in original_assets:
            image_bytes = storage.get_object(
                user_id=user_id,
                bucket=asset.bucket,
                object_key=asset.object_key,
            )

            try:
                detection_res = detector.detect(image_bytes)
            except TimeoutError:
                logger.warning("Detector timed out for batch %s", batch_id)
                add_warning("AI nhận diện quá thời gian (timeout). Vui lòng kiểm tra thủ công.")
                batch.quality_warnings = list(warnings_accumulator)
                flag_modified(batch, "quality_warnings")
                batch.status = IngestionStatus.NEEDS_REVIEW
                session.add(batch)
                session.commit()
                return batch
            except ProviderError as p_err:
                logger.error("Detector provider error for batch %s: %s", batch_id, p_err)
                raise
            except Exception as det_err:
                logger.warning("Detector error for batch %s: %s", batch_id, det_err)
                add_warning("AI không thể tự động phát hiện vật phẩm. Vui lòng kiểm tra thủ công.")
                batch.quality_warnings = list(warnings_accumulator)
                flag_modified(batch, "quality_warnings")
                batch.status = IngestionStatus.NEEDS_REVIEW
                session.add(batch)
                session.commit()
                return batch

            batch.input_kind = detection_res.input_kind
            for warning in detection_res.quality_warnings:
                add_warning(warning)

            # For each candidate detected region, crop and extract attributes
            for box_det in detection_res.boxes:
                cropped = crop_item_and_generate_thumbnail(image_bytes, box_det.box)
                item_candidate_id = new_uuid()

                # Store crop in wardrobe-private
                crop_key = f"users/{user_id}/items/{item_candidate_id}/crop/v1.{cropped.crop_extension}"
                storage.put_object(
                    user_id=user_id,
                    bucket="wardrobe-private",
                    object_key=crop_key,
                    data=cropped.crop_bytes,
                    content_type=cropped.crop_mime_type,
                )
                crop_objects_created.append(("wardrobe-private", crop_key))

                # Store thumbnail in wardrobe-thumbnails
                thumb_key = f"users/{user_id}/items/{item_candidate_id}/thumbnail/v1.{cropped.thumb_extension}"
                storage.put_object(
                    user_id=user_id,
                    bucket="wardrobe-thumbnails",
                    object_key=thumb_key,
                    data=cropped.thumb_bytes,
                    content_type=cropped.thumb_mime_type,
                )
                crop_objects_created.append(("wardrobe-thumbnails", thumb_key))

                crop_asset_id = new_uuid()
                crop_media_asset = MediaAsset(
                    id=crop_asset_id,
                    user_id=user_id,
                    ingestion_batch_id=batch_id,
                    kind=MediaKind.CROP,
                    bucket="wardrobe-private",
                    object_key=crop_key,
                    mime_type=cropped.crop_mime_type,
                    size_bytes=cropped.crop_size_bytes,
                    width=cropped.crop_width,
                    height=cropped.crop_height,
                    sha256=cropped.crop_sha256,
                )
                session.add(crop_media_asset)
                session.flush()

                thumb_asset_id = new_uuid()
                thumb_media_asset = MediaAsset(
                    id=thumb_asset_id,
                    user_id=user_id,
                    ingestion_batch_id=batch_id,
                    kind=MediaKind.THUMBNAIL,
                    bucket="wardrobe-thumbnails",
                    object_key=thumb_key,
                    mime_type=cropped.thumb_mime_type,
                    size_bytes=cropped.thumb_size_bytes,
                    width=cropped.thumb_width,
                    height=cropped.thumb_height,
                    sha256=cropped.thumb_sha256,
                )
                session.add(thumb_media_asset)
                session.flush()

                # Extract structured attributes
                try:
                    extraction = vision_provider.extract_attributes(cropped.crop_bytes)
                except TimeoutError:
                    logger.warning("Vision provider timed out for batch %s crop", batch_id)
                    extraction = VisionExtractionResult(
                        attributes={"category": "unknown", "style": "casual"},
                        field_confidence={"category": 0.5, "style": 0.5},
                        quality_warnings=["AI nhận diện thuộc tính quá thời gian (timeout). Vui lòng kiểm tra thủ công."],
                    )
                except ProviderError as p_err:
                    logger.error("Vision provider error for batch %s crop: %s", batch_id, p_err)
                    raise

                # Flag fields with confidence < 0.70
                low_conf_fields = [
                    field for field, conf in extraction.field_confidence.items() if conf < 0.70
                ]
                if low_conf_fields:
                    add_warning(f"Một số trường có độ tin cậy thấp (< 70%): {', '.join(low_conf_fields)}.")

                for warning in extraction.quality_warnings:
                    add_warning(warning)

                detection_id = new_uuid()
                detection = IngestionDetection(
                    id=detection_id,
                    user_id=user_id,
                    ingestion_batch_id=batch_id,
                    crop_media_asset_id=crop_asset_id,
                    bounding_box=box_det.box,
                    proposed_attributes=extraction.attributes,
                    field_confidence=extraction.field_confidence,
                    status=DetectionStatus.PROPOSED,
                )
                session.add(detection)

        batch.quality_warnings = list(warnings_accumulator)
        flag_modified(batch, "quality_warnings")
        batch.status = IngestionStatus.NEEDS_REVIEW
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return batch

    except (ProviderError, Exception) as exc:
        session.rollback()
        # Compensating cleanup of transient crops
        for bucket, key in crop_objects_created:
            try:
                storage.delete_object(user_id=user_id, bucket=bucket, object_key=key)
            except Exception as cleanup_err:
                logger.error("Transient crop cleanup error %s: %s", key, cleanup_err)

        batch = session.get(IngestionBatch, batch_id)
        if batch:
            batch.status = IngestionStatus.FAILED
            err_msg = str(getattr(exc, "message", exc))
            fail_warnings = list(batch.quality_warnings or [])
            fail_warnings.append(f"Xử lý ảnh thất bại: {err_msg}")
            batch.quality_warnings = fail_warnings
            flag_modified(batch, "quality_warnings")
            session.add(batch)
            session.commit()
            session.refresh(batch)
            return batch
        raise


def get_batch_review(
    *,
    session: Session,
    batch_id: str,
    user_id: str,
) -> IngestionBatchReviewResponseData:
    """Retrieve review details for an ingestion batch, ensuring user ownership isolation."""
    batch = session.get(IngestionBatch, batch_id)
    if batch is None:
        raise ItemNotFoundError("Không tìm thấy lượt tải lên này.")
    if batch.user_id != user_id:
        raise ForbiddenAssetError()

    detections = session.exec(
        select(IngestionDetection).where(IngestionDetection.ingestion_batch_id == batch_id)
    ).all()

    detection_items: list[DetectionReviewItem] = []
    for det in detections:
        crop_url = f"/api/v1/media/{det.crop_media_asset_id}" if det.crop_media_asset_id else ""
        detection_items.append(
            DetectionReviewItem(
                detection_id=det.id,
                crop_url=crop_url,
                bounding_box=det.bounding_box,
                attributes=det.proposed_attributes,
                field_confidence=det.field_confidence,
            )
        )

    return IngestionBatchReviewResponseData(
        batch_id=batch.id,
        input_kind=batch.input_kind.value,
        status=batch.status.value,
        detections=detection_items,
        quality_warnings=batch.quality_warnings,
    )


def confirm_ingestion_batch(
    *,
    session: Session,
    batch_id: str,
    user_id: str,
    confirmations: list[DetectionConfirmationItem],
) -> list[str]:
    """Idempotently confirm an ingestion batch.

    Creates WardrobeItem and ItemMedia records for accepted detections.
    If already confirmed, returns existing item IDs without duplicate creation.
    """
    batch = session.get(IngestionBatch, batch_id)
    if batch is None:
        raise ItemNotFoundError("Không tìm thấy lượt tải lên này.")
    if batch.user_id != user_id:
        raise ForbiddenAssetError()

    # Idempotency: Return existing confirmed items if already completed
    if batch.status == IngestionStatus.CONFIRMED:
        existing_items = session.exec(
            select(WardrobeItem).where(
                WardrobeItem.ingestion_batch_id == batch_id,
                WardrobeItem.user_id == user_id,
            )
        ).all()
        return [item.id for item in existing_items]

    conf_map = {c.detection_id: c for c in confirmations}
    detections = session.exec(
        select(IngestionDetection).where(IngestionDetection.ingestion_batch_id == batch_id)
    ).all()

    created_item_ids: list[str] = []

    for detection in detections:
        conf = conf_map.get(detection.id)
        # If user explicitly supplied confirmations, only accept those explicitly approved
        if confirmations:
            if conf is None or not conf.accepted:
                detection.status = DetectionStatus.REJECTED
                session.add(detection)
                continue
        elif conf and not conf.accepted:
            detection.status = DetectionStatus.REJECTED
            session.add(detection)
            continue

        detection.status = DetectionStatus.ACCEPTED
        session.add(detection)

        # Merge user custom attributes if supplied
        attrs = dict(detection.proposed_attributes)
        if conf and conf.custom_attributes:
            attrs.update(conf.custom_attributes)

        # Align item_id with the object key storage path users/{user_id}/items/{item_id}/...
        item_id = new_uuid()
        crop_asset = (
            session.get(MediaAsset, detection.crop_media_asset_id)
            if detection.crop_media_asset_id
            else None
        )
        if crop_asset and crop_asset.object_key:
            parts = crop_asset.object_key.split("/")
            if len(parts) >= 4 and parts[2] == "items":
                item_id = parts[3]

        category_raw = attrs.get("category", "top")
        try:
            category_enum = WardrobeCategory(category_raw)
        except ValueError:
            category_enum = WardrobeCategory.TOP

        wardrobe_item = WardrobeItem(
            id=item_id,
            user_id=user_id,
            ingestion_batch_id=batch_id,
            ingestion_detection_id=detection.id,
            category=category_enum,
            sub_category=str(attrs.get("sub_category", "clothing")),
            primary_color=str(attrs.get("primary_color", "unknown")),
            secondary_color=attrs.get("secondary_color"),
            pattern=str(attrs.get("pattern", "unknown")),
            material=str(attrs.get("material", "unknown")),
            style=str(attrs.get("style", "casual")),
            fit=str(attrs.get("fit", "regular")),
            formality_level=int(attrs.get("formality_level", 3)),
            season=list(attrs.get("season", [])),
            weather_suitability=list(attrs.get("weather_suitability", [])),
            functional_flags=list(attrs.get("functional_flags", [])),
            free_text_tags=list(attrs.get("free_text_tags", [])),
            field_confidence=detection.field_confidence,
            is_active=True,
            is_user_confirmed=True,
            times_worn=0,
        )
        session.add(wardrobe_item)
        session.flush()
        created_item_ids.append(item_id)

        # Link Primary ItemMedia (Crop)
        if detection.crop_media_asset_id:
            item_media_primary = ItemMedia(
                wardrobe_item_id=item_id,
                media_asset_id=detection.crop_media_asset_id,
                user_id=user_id,
                role=ItemMediaRole.PRIMARY,
            )
            session.add(item_media_primary)

        # Link Thumbnail ItemMedia
        thumb_asset = session.exec(
            select(MediaAsset).where(
                MediaAsset.ingestion_batch_id == batch_id,
                MediaAsset.kind == MediaKind.THUMBNAIL,
                MediaAsset.object_key.like(f"%items/{item_id}/thumbnail/%"),
            )
        ).first()
        if thumb_asset:
            item_media_thumb = ItemMedia(
                wardrobe_item_id=item_id,
                media_asset_id=thumb_asset.id,
                user_id=user_id,
                role=ItemMediaRole.THUMBNAIL,
            )
            session.add(item_media_thumb)

    batch.status = IngestionStatus.CONFIRMED
    session.add(batch)
    session.commit()

    return created_item_ids
