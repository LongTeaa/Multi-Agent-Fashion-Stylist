"""Resolve the image shown for a wardrobe item."""
from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session, select

from app.models.entities import ItemMedia, ItemMediaRole, MediaAsset

MEDIA_ROLE_PRIORITY: dict[ItemMediaRole, int] = {
    ItemMediaRole.PRIMARY: 0,
    ItemMediaRole.THUMBNAIL: 1,
    ItemMediaRole.ALTERNATE: 2,
}


def primary_media_ids(session: Session, user_id: str, item_ids: Iterable[str]) -> dict[str, str]:
    """Map each item to its highest-priority media asset that is not soft-deleted.

    Items whose every linked asset is deleted are absent from the result, so callers
    return no image instead of a URL that answers 404.
    """
    wanted = set(item_ids)
    if not wanted:
        return {}
    links = session.exec(
        select(ItemMedia.wardrobe_item_id, ItemMedia.role, ItemMedia.media_asset_id)
        .join(MediaAsset, ItemMedia.media_asset_id == MediaAsset.id)
        .where(
            ItemMedia.wardrobe_item_id.in_(wanted),
            ItemMedia.user_id == user_id,
            MediaAsset.user_id == user_id,
            MediaAsset.deleted_at.is_(None),
        )
    ).all()
    best: dict[str, tuple[int, str]] = {}
    for item_id, role, asset_id in links:
        rank = (MEDIA_ROLE_PRIORITY.get(role, len(MEDIA_ROLE_PRIORITY)), asset_id)
        if item_id not in best or rank < best[item_id]:
            best[item_id] = rank
    return {item_id: asset_id for item_id, (_, asset_id) in best.items()}


def primary_media_id(session: Session, item_id: str, user_id: str) -> str | None:
    """Return the item's highest-priority media asset that is not soft-deleted."""
    return primary_media_ids(session, user_id, [item_id]).get(item_id)
