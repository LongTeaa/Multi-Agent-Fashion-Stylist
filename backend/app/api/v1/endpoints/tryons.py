from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.dependencies import (
    get_current_user_id,
    get_db_session,
    get_image_provider,
    get_object_storage,
)
from app.repositories.object_storage import ObjectStorage
from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.tryons import TryOnRequest, TryOnResponseData
from app.services.providers import ImageProviderProtocol
from app.services.tryon_service import create_tryon

router = APIRouter(prefix="/tryons", tags=["tryons"])


@router.post(
    "",
    response_model=SuccessResponse[TryOnResponseData],
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
)
def generate_tryon(
    payload: TryOnRequest,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    provider: ImageProviderProtocol | None = Depends(get_image_provider),
    settings: Settings = Depends(get_settings),
) -> SuccessResponse[TryOnResponseData]:
    data = create_tryon(
        session=session,
        storage=storage,
        provider=provider,
        outfit_id=payload.outfit_id,
        user_id=user_id,
        tryon_bucket=settings.minio_bucket_tryon,
        timeout_seconds=float(settings.image_timeout_seconds),
    )
    return SuccessResponse(data=data)
