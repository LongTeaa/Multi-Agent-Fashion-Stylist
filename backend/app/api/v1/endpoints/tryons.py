from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.dependencies import (
    get_current_user_id,
    get_db_session,
    get_detector,
    get_image_provider,
    get_object_storage,
    get_tryon_provider,
)
from app.repositories.object_storage import ObjectStorage
from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.tryons import TryOnAvatarResponse, TryOnRequest, TryOnResponseData
from app.services.providers import DetectorProtocol, ImageProviderProtocol, TryOnProviderProtocol
from app.services.tryon_service import (
    create_tryon,
    create_user_avatar,
    delete_user_avatar,
    get_preset_avatar_bytes,
    get_tryon_render_by_id,
    list_tryon_avatars,
)

router = APIRouter(prefix="/tryons", tags=["tryons"])


@router.get(
    "/avatars",
    response_model=SuccessResponse[list[TryOnAvatarResponse]],
    summary="Liệt kê danh sách người mẫu và ảnh đại diện có thể mặc thử",
)
def get_avatars(
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[list[TryOnAvatarResponse]]:
    avatars = list_tryon_avatars(session=session, user_id=user_id)
    return SuccessResponse(data=avatars)


@router.post(
    "/avatars",
    response_model=SuccessResponse[TryOnAvatarResponse],
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    summary="Tải lên ảnh toàn thân cá nhân để mặc thử AI",
)
async def upload_user_avatar(
    file: Annotated[UploadFile, File(...)],
    name: Annotated[str, Form()] = "Ảnh của tôi",
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    detector: DetectorProtocol | None = Depends(get_detector),
    settings: Settings = Depends(get_settings),
) -> SuccessResponse[TryOnAvatarResponse]:
    file_bytes = await file.read()
    avatar = create_user_avatar(
        session=session,
        storage=storage,
        detector=detector,
        user_id=user_id,
        file_bytes=file_bytes,
        filename=name or file.filename or "Ảnh của tôi",
        tryon_bucket=settings.minio_bucket_tryon,
    )
    return SuccessResponse(data=avatar)


@router.delete(
    "/avatars/{avatar_id}",
    response_model=SuccessResponse[dict[str, object]],
    responses={
        404: {"model": ErrorResponse},
    },
    summary="Xóa ảnh toàn thân cá nhân đã tải lên",
)
def remove_user_avatar(
    avatar_id: str,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
) -> SuccessResponse[dict[str, object]]:
    delete_user_avatar(session=session, user_id=user_id, avatar_id=avatar_id, storage=storage)
    return SuccessResponse(data={"deleted": True, "avatar_id": avatar_id})


@router.get(
    "/presets/{preset_gender}",
    summary="Truy xuất ảnh người mẫu chuẩn theo giới tính",
)
def get_preset_model_image(preset_gender: str) -> Response:
    image_bytes = get_preset_avatar_bytes(preset_gender)
    return Response(
        content=image_bytes,
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Length": str(len(image_bytes)),
        },
    )


@router.post(
    "",
    response_model=SuccessResponse[TryOnResponseData],
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
    },
    summary="Tạo ảnh mặc thử ảo 2D hoặc lookbook minh họa",
)
def generate_tryon(
    payload: TryOnRequest,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
    image_provider: ImageProviderProtocol | None = Depends(get_image_provider),
    tryon_provider: TryOnProviderProtocol | None = Depends(get_tryon_provider),
    settings: Settings = Depends(get_settings),
) -> SuccessResponse[TryOnResponseData]:
    data = create_tryon(
        session=session,
        storage=storage,
        provider=image_provider,
        tryon_provider=tryon_provider,
        outfit_id=payload.outfit_id,
        user_id=user_id,
        avatar_id=payload.avatar_id,
        item_ids=payload.item_ids,
        force_refresh=payload.force_refresh,
        tryon_bucket=settings.minio_bucket_tryon,
        timeout_seconds=float(settings.image_timeout_seconds),
    )
    return SuccessResponse(data=data)


@router.get(
    "/{tryon_id}",
    response_model=SuccessResponse[TryOnResponseData],
    responses={
        404: {"model": ErrorResponse},
    },
    summary="Tra cứu trạng thái hoặc kết quả của một phiên thử đồ",
)
def get_tryon(
    tryon_id: str,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[TryOnResponseData]:
    data = get_tryon_render_by_id(session=session, user_id=user_id, tryon_id=tryon_id)
    return SuccessResponse(data=data)
