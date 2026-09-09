from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.core.dependencies import get_current_user_id, get_db_session
from app.models.entities import WardrobeCategory
from app.schemas.common import SuccessResponse
from app.schemas.wardrobe import (
    WardrobeItemCreate,
    WardrobeItemDeleteResponseData,
    WardrobeItemListResponseData,
    WardrobeItemResponseData,
    WardrobeItemUpdate,
)
from app.services.wardrobe_service import (
    create_wardrobe_item,
    delete_wardrobe_item,
    get_wardrobe_item,
    list_wardrobe_items,
    update_wardrobe_item,
)

router = APIRouter(prefix="/wardrobe/items", tags=["wardrobe"])


@router.get("", response_model=SuccessResponse[WardrobeItemListResponseData])
def list_items(
    category: WardrobeCategory | None = None,
    style: str | None = Query(default=None, min_length=1, max_length=100),
    color: str | None = Query(default=None, min_length=1, max_length=50),
    text: str | None = Query(default=None, min_length=1, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[WardrobeItemListResponseData]:
    return SuccessResponse(
        data=list_wardrobe_items(
            session=session,
            user_id=user_id,
            category=category,
            style=style,
            color=color,
            text=text,
            page=page,
            page_size=page_size,
        )
    )


@router.post(
    "", response_model=SuccessResponse[WardrobeItemResponseData], status_code=status.HTTP_201_CREATED
)
def create_item(
    payload: WardrobeItemCreate,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[WardrobeItemResponseData]:
    return SuccessResponse(data=create_wardrobe_item(session=session, user_id=user_id, payload=payload))


@router.get("/{item_id}", response_model=SuccessResponse[WardrobeItemResponseData])
def get_item(
    item_id: str,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[WardrobeItemResponseData]:
    return SuccessResponse(data=get_wardrobe_item(session=session, user_id=user_id, item_id=item_id))


@router.patch("/{item_id}", response_model=SuccessResponse[WardrobeItemResponseData])
def update_item(
    item_id: str,
    payload: WardrobeItemUpdate,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[WardrobeItemResponseData]:
    return SuccessResponse(
        data=update_wardrobe_item(
            session=session, user_id=user_id, item_id=item_id, payload=payload
        )
    )


@router.delete("/{item_id}", response_model=SuccessResponse[WardrobeItemDeleteResponseData])
def delete_item(
    item_id: str,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[WardrobeItemDeleteResponseData]:
    delete_wardrobe_item(session=session, user_id=user_id, item_id=item_id)
    return SuccessResponse(
        data=WardrobeItemDeleteResponseData(item_id=item_id, is_active=False)
    )
