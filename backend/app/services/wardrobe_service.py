from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, cast, func, or_
from sqlmodel import Session, col, select

from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    WardrobeCategory,
    WardrobeItem,
    new_uuid,
)
from app.schemas.common import ForbiddenAssetError, ItemNotFoundError, ValidationError
from app.schemas.wardrobe import (
    WardrobeItemCreate,
    WardrobeItemListResponseData,
    WardrobeItemResponseData,
    WardrobeItemUpdate,
)
from app.services.retrieval_document_service import refresh_retrieval_document


def _owned_active_item(session: Session, item_id: str, user_id: str) -> WardrobeItem:
    item = session.get(WardrobeItem, item_id)
    if item is None or item.deleted_at is not None or not item.is_active:
        raise ItemNotFoundError()
    if item.user_id != user_id:
        raise ItemNotFoundError()
    return item


def _primary_media_id(session: Session, item_id: str, user_id: str) -> str | None:
    links = session.exec(
        select(ItemMedia).where(
            ItemMedia.wardrobe_item_id == item_id,
            ItemMedia.user_id == user_id,
        )
    ).all()
    if not links:
        return None
    priority = {
        ItemMediaRole.PRIMARY: 0,
        ItemMediaRole.THUMBNAIL: 1,
        ItemMediaRole.ALTERNATE: 2,
    }
    return min(links, key=lambda link: priority[link.role]).media_asset_id


def serialize_item(session: Session, item: WardrobeItem) -> WardrobeItemResponseData:
    media_id = _primary_media_id(session, item.id, item.user_id)
    return WardrobeItemResponseData(
        **item.model_dump(),
        media_url=f"/api/v1/media/{media_id}" if media_id else None,
    )


def list_wardrobe_items(
    *,
    session: Session,
    user_id: str,
    category: WardrobeCategory | None,
    style: str | None,
    color: str | None,
    text: str | None,
    page: int,
    page_size: int,
) -> WardrobeItemListResponseData:
    filters = [
        WardrobeItem.user_id == user_id,
        WardrobeItem.is_active.is_(True),
        WardrobeItem.is_user_confirmed.is_(True),
        WardrobeItem.deleted_at.is_(None),
    ]
    if category is not None:
        filters.append(WardrobeItem.category == category)
    if style:
        filters.append(func.lower(WardrobeItem.style) == style.strip().lower())
    if color:
        normalized_color = color.strip().lower()
        filters.append(
            or_(
                func.lower(WardrobeItem.primary_color) == normalized_color,
                func.lower(WardrobeItem.secondary_color) == normalized_color,
            )
        )
    if text:
        pattern = f"%{text.strip().lower()}%"
        filters.append(
            or_(
                func.lower(WardrobeItem.sub_category).like(pattern),
                func.lower(WardrobeItem.primary_color).like(pattern),
                func.lower(WardrobeItem.pattern).like(pattern),
                func.lower(WardrobeItem.material).like(pattern),
                func.lower(WardrobeItem.style).like(pattern),
                func.lower(WardrobeItem.fit).like(pattern),
                func.lower(cast(WardrobeItem.free_text_tags, String)).like(pattern),
            )
        )

    total = session.exec(select(func.count()).select_from(WardrobeItem).where(*filters)).one()
    items = session.exec(
        select(WardrobeItem)
        .where(*filters)
        .order_by(col(WardrobeItem.updated_at).desc(), col(WardrobeItem.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return WardrobeItemListResponseData(
        items=[serialize_item(session, item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


def create_wardrobe_item(
    *, session: Session, user_id: str, payload: WardrobeItemCreate
) -> WardrobeItemResponseData:
    asset = session.get(MediaAsset, payload.media_asset_id)
    if asset is None or asset.deleted_at is not None:
        raise ValidationError(details={"field": "media_asset_id", "reason": "not_found"})
    if asset.user_id != user_id:
        raise ForbiddenAssetError()
    if session.exec(
        select(ItemMedia).where(ItemMedia.media_asset_id == asset.id)
    ).first() is not None:
        raise ValidationError(
            details={"field": "media_asset_id", "reason": "already_linked"}
        )

    values = payload.model_dump(exclude={"media_asset_id"})
    item = WardrobeItem(
        id=new_uuid(),
        user_id=user_id,
        **values,
        field_confidence={},
        is_active=True,
        is_user_confirmed=True,
    )
    session.add(item)
    session.flush()
    refresh_retrieval_document(session, item)
    session.add(
        ItemMedia(
            wardrobe_item_id=item.id,
            media_asset_id=asset.id,
            user_id=user_id,
            role=ItemMediaRole.PRIMARY,
        )
    )
    session.commit()
    session.refresh(item)
    return serialize_item(session, item)


def get_wardrobe_item(
    *, session: Session, user_id: str, item_id: str
) -> WardrobeItemResponseData:
    return serialize_item(session, _owned_active_item(session, item_id, user_id))


def update_wardrobe_item(
    *, session: Session, user_id: str, item_id: str, payload: WardrobeItemUpdate
) -> WardrobeItemResponseData:
    item = _owned_active_item(session, item_id, user_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return serialize_item(session, item)
    for field, value in changes.items():
        setattr(item, field, value)
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
    refresh_retrieval_document(session, item)
    session.commit()
    session.refresh(item)
    return serialize_item(session, item)


def delete_wardrobe_item(*, session: Session, user_id: str, item_id: str) -> None:
    item = _owned_active_item(session, item_id, user_id)
    now = datetime.now(timezone.utc)
    item.is_active = False
    item.deleted_at = now
    item.updated_at = now
    session.add(item)
    refresh_retrieval_document(session, item)
    session.commit()
