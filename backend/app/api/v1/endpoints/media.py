from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlmodel import Session

from app.core.dependencies import get_db_session, get_object_storage
from app.models.entities import MediaAsset
from app.repositories.object_storage import ObjectStorage
from app.schemas.common import ForbiddenAssetError, ItemNotFoundError, ValidationError

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{asset_id}")
def get_media_asset(
    asset_id: str,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    user_id: Annotated[str | None, Query(alias="user_id")] = None,
    session: Session = Depends(get_db_session),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    """Retrieve and stream a private media asset after validating user ownership."""
    effective_user_id = (x_user_id or "").strip() or (user_id or "").strip()
    if not effective_user_id:
        raise ValidationError(
            message="Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.",
            details={"field": "X-User-Id", "reason": "missing_or_empty"},
        )
    media_asset = session.get(MediaAsset, asset_id)
    if media_asset is None or media_asset.deleted_at is not None:
        raise ItemNotFoundError(
            message="Không tìm thấy tệp phương tiện này.",
            code="MEDIA_NOT_FOUND",
        )

    if media_asset.user_id != effective_user_id:
        raise ForbiddenAssetError()

    content = storage.get_object(
        user_id=media_asset.user_id,
        bucket=media_asset.bucket,
        object_key=media_asset.object_key,
    )

    return Response(
        content=content,
        media_type=media_asset.mime_type,
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Length": str(media_asset.size_bytes),
        },
    )
