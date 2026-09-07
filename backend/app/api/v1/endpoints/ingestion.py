from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Request, status
from sqlmodel import Session

from app.core.dependencies import (
    get_current_user_id,
    get_db_session,
    get_detector,
    get_object_storage,
    get_vision_provider,
)
from app.models.entities import IngestionBatch, IngestionStatus, InputKind
from app.repositories.object_storage import ObjectStorage
from app.schemas.common import SuccessResponse, ValidationError
from app.schemas.ingestion import (
    IngestionBatchReviewResponseData,
    IngestionConfirmRequest,
    IngestionConfirmResponseData,
    IngestionDeleteResponseData,
    IngestionUploadResponseData,
)
from app.services.cleanup_service import cancel_ingestion_batch
from app.services.ingestion_service import (
    confirm_ingestion_batch,
    create_ingestion_batch,
    get_batch_review,
    process_ingestion_batch,
)
from app.services.providers import DetectorProtocol, VisionProviderProtocol

router = APIRouter(prefix="/ingestions", tags=["ingestion"])


def _run_batch_processing_task(
    batch_id: str,
    user_id: str,
    storage: ObjectStorage,
    detector: DetectorProtocol,
    vision_provider: VisionProviderProtocol,
    engine: object | None = None,
) -> None:
    import logging
    from sqlalchemy import Engine
    from app.core.database import get_engine
    task_logger = logging.getLogger(__name__)

    target_engine = engine if isinstance(engine, Engine) else get_engine()
    with Session(target_engine) as session:
        try:
            process_ingestion_batch(
                session=session,
                storage=storage,
                detector=detector,
                vision_provider=vision_provider,
                batch_id=batch_id,
                user_id=user_id,
            )
        except Exception as exc:
            task_logger.error("Background processing failed for batch %s: %s", batch_id, exc)
            try:
                batch = session.get(IngestionBatch, batch_id)
                if batch:
                    batch.status = IngestionStatus.FAILED
                    batch.quality_warnings.append(f"Xử lý ảnh nền thất bại: {str(exc)}")
                    session.add(batch)
                    session.commit()
            except Exception:
                session.rollback()


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SuccessResponse[IngestionUploadResponseData],
)
async def upload_ingestion_images(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    detector: DetectorProtocol = Depends(get_detector),
    vision_provider: VisionProviderProtocol = Depends(get_vision_provider),
) -> SuccessResponse[IngestionUploadResponseData]:
    """Upload 1–10 images for clothing digitization.

    Stores original assets privately and creates an ingestion batch with status `processing`.
    """
    form = await request.form()
    form_files = form.getlist("images[]") or form.getlist("images")

    if not form_files:
        raise ValidationError(
            message="Vui lòng tải lên từ 1 đến 10 ảnh.",
            details={"field": "images[]", "reason": "no_images_provided"},
        )

    # Early rejection if file count exceeds 10 before reading bytes into memory
    if len(form_files) > 10:
        raise ValidationError(
            message="Số lượng ảnh tải lên phải từ 1 đến 10 ảnh.",
            details={"count": len(form_files), "min": 1, "max": 10},
        )

    raw_files: list[tuple[str, bytes]] = []
    for form_item in form_files:
        if hasattr(form_item, "read"):
            content = await form_item.read()
            filename = getattr(form_item, "filename", "upload.jpg")
            raw_files.append((filename, content))

    declared_kind_raw = form.get("declared_input_kind")
    declared_kind: InputKind | None = None
    if declared_kind_raw:
        try:
            declared_kind = InputKind(str(declared_kind_raw))
        except ValueError:
            raise ValidationError(
                message="Loại ảnh khai báo không hợp lệ.",
                details={"declared_input_kind": declared_kind_raw},
            )

    batch = create_ingestion_batch(
        session=session,
        storage=storage,
        user_id=current_user_id,
        raw_files=raw_files,
        declared_input_kind=declared_kind,
    )

    # Trigger async processing background task with injected storage, detector, and engine
    engine = session.get_bind()
    background_tasks.add_task(
        _run_batch_processing_task,
        batch.id,
        current_user_id,
        storage,
        detector,
        vision_provider,
        engine,
    )

    return SuccessResponse(
        data=IngestionUploadResponseData(
            batch_id=batch.id,
            status=batch.status.value,
        )
    )


@router.get(
    "/{batch_id}",
    response_model=SuccessResponse[IngestionBatchReviewResponseData],
)
def get_ingestion_batch(
    batch_id: str,
    current_user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    detector: DetectorProtocol = Depends(get_detector),
    vision_provider: VisionProviderProtocol = Depends(get_vision_provider),
) -> SuccessResponse[IngestionBatchReviewResponseData]:
    """Retrieve review details, detected bounding boxes, attributes, and quality warnings for a batch."""
    batch = session.get(IngestionBatch, batch_id)
    if batch and batch.status == IngestionStatus.PROCESSING and batch.user_id == current_user_id:
        # Just-in-time processing if background task hasn't finished yet
        process_ingestion_batch(
            session=session,
            storage=storage,
            detector=detector,
            vision_provider=vision_provider,
            batch_id=batch_id,
            user_id=current_user_id,
        )

    data = get_batch_review(session=session, batch_id=batch_id, user_id=current_user_id)
    return SuccessResponse(data=data)


@router.post(
    "/{batch_id}/confirm",
    response_model=SuccessResponse[IngestionConfirmResponseData],
)
def confirm_ingestion(
    batch_id: str,
    payload: IngestionConfirmRequest = Body(...),
    current_user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[IngestionConfirmResponseData]:
    """Confirm an ingestion batch into canonical wardrobe items idempotently."""
    confirmed_item_ids = confirm_ingestion_batch(
        session=session,
        batch_id=batch_id,
        user_id=current_user_id,
        confirmations=payload.confirmations,
    )

    return SuccessResponse(
        data=IngestionConfirmResponseData(
            batch_id=batch_id,
            status=IngestionStatus.CONFIRMED.value,
            wardrobe_item_ids=confirmed_item_ids,
        )
    )


@router.delete(
    "/{batch_id}",
    response_model=SuccessResponse[IngestionDeleteResponseData],
)
def cancel_ingestion(
    batch_id: str,
    current_user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
) -> SuccessResponse[IngestionDeleteResponseData]:
    """Cancel an unconfirmed ingestion batch and schedule its temporary assets for immediate cleanup."""
    cancelled_batch = cancel_ingestion_batch(
        session=session,
        storage=storage,
        batch_id=batch_id,
        user_id=current_user_id,
    )

    return SuccessResponse(
        data=IngestionDeleteResponseData(
            batch_id=cancelled_batch.id,
            status=cancelled_batch.status.value,
        )
    )
