from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from io import BytesIO
from time import monotonic
from typing import Literal, cast

from PIL import Image, UnidentifiedImageError
from sqlalchemy import and_
from sqlmodel import Session, select

from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    OutfitItem,
    OutfitRecommendation,
    TryOnRender,
    WardrobeItem,
    new_uuid,
)
from app.repositories.object_storage import ObjectStorage
from app.schemas.common import OutfitNotFoundError, TryOnFailedError
from app.schemas.tryons import TryOnResponseData
from app.services.cleanup_service import record_orphan_cleanup
from app.services.image_generation import render_lookbook_with_fallback
from app.services.moodboard import MoodboardItem
from app.services.providers import ImageProviderProtocol, ImageReference
from app.services.tryon_prompt import LookbookPromptItem, build_lookbook_prompt


def _image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
            return image.size
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise TryOnFailedError() from error


def _load_outfit_assets(
    *,
    session: Session,
    storage: ObjectStorage,
    outfit_id: str,
    user_id: str,
) -> tuple[
    tuple[LookbookPromptItem, ...],
    tuple[ImageReference, ...],
    tuple[MoodboardItem, ...],
]:
    outfit = session.exec(
        select(OutfitRecommendation).where(
            OutfitRecommendation.id == outfit_id,
            OutfitRecommendation.user_id == user_id,
        )
    ).first()
    if outfit is None:
        raise OutfitNotFoundError()

    outfit_items = session.exec(
        select(OutfitItem)
        .where(
            OutfitItem.outfit_id == outfit_id,
            OutfitItem.user_id == user_id,
        )
        .order_by(OutfitItem.slot_role)
    ).all()
    if not 2 <= len(outfit_items) <= 5:
        raise TryOnFailedError()

    prompt_items: list[LookbookPromptItem] = []
    references: list[ImageReference] = []
    moodboard_items: list[MoodboardItem] = []
    for outfit_item in outfit_items:
        wardrobe_item = session.exec(
            select(WardrobeItem).where(
                WardrobeItem.id == outfit_item.wardrobe_item_id,
                WardrobeItem.user_id == user_id,
                WardrobeItem.is_user_confirmed.is_(True),
            )
        ).first()
        media_row = session.exec(
            select(ItemMedia, MediaAsset)
            .join(
                MediaAsset,
                and_(
                    ItemMedia.media_asset_id == MediaAsset.id,
                    ItemMedia.user_id == MediaAsset.user_id,
                ),
            )
            .where(
                ItemMedia.wardrobe_item_id == outfit_item.wardrobe_item_id,
                ItemMedia.user_id == user_id,
                ItemMedia.role == ItemMediaRole.PRIMARY,
                MediaAsset.deleted_at.is_(None),
            )
            .order_by(MediaAsset.created_at, MediaAsset.id)
        ).first()
        if wardrobe_item is None or media_row is None:
            raise TryOnFailedError()

        _, media_asset = media_row
        if media_asset.mime_type not in ("image/jpeg", "image/png", "image/webp"):
            raise TryOnFailedError()
        reference_mime = cast(
            Literal["image/jpeg", "image/png", "image/webp"],
            media_asset.mime_type,
        )
        try:
            crop_bytes = storage.get_object(
                user_id=user_id,
                bucket=media_asset.bucket,
                object_key=media_asset.object_key,
            )
        except Exception as error:
            raise TryOnFailedError() from error

        prompt_items.append(
            LookbookPromptItem(
                slot=outfit_item.slot_role,
                sub_category=wardrobe_item.sub_category,
                primary_color=wardrobe_item.primary_color,
                secondary_color=wardrobe_item.secondary_color,
                pattern=wardrobe_item.pattern,
                material=wardrobe_item.material,
                style=wardrobe_item.style,
                fit=wardrobe_item.fit,
            )
        )
        references.append(
            ImageReference(
                asset_id=media_asset.id,
                image_bytes=crop_bytes,
                mime_type=reference_mime,
            )
        )
        moodboard_items.append(
            MoodboardItem(
                asset_id=media_asset.id,
                slot=outfit_item.slot_role,
                name=wardrobe_item.sub_category,
                color=wardrobe_item.primary_color,
                image_bytes=crop_bytes,
            )
        )

    return tuple(prompt_items), tuple(references), tuple(moodboard_items)


def create_tryon(
    *,
    session: Session,
    storage: ObjectStorage,
    provider: ImageProviderProtocol | None,
    outfit_id: str,
    user_id: str,
    tryon_bucket: str,
    timeout_seconds: float = 8,
    performance_clock: Callable[[], float] = monotonic,
) -> TryOnResponseData:
    """Authorize, render, persist, and expose one private illustrative lookbook."""

    started_at = performance_clock()
    prompt_items, references, moodboard_items = _load_outfit_assets(
        session=session,
        storage=storage,
        outfit_id=outfit_id,
        user_id=user_id,
    )
    prompt = build_lookbook_prompt(prompt_items)
    rendered = render_lookbook_with_fallback(
        provider=provider,
        prompt=prompt,
        reference_images=references,
        moodboard_items=moodboard_items,
        timeout_seconds=timeout_seconds,
    )
    width, height = _image_dimensions(rendered.image_bytes)
    duration_ms = max(0, round((performance_clock() - started_at) * 1000))

    tryon_id, media_asset_id = new_uuid(), new_uuid()
    object_key = f"users/{user_id}/tryons/{tryon_id}/render.webp"
    storage.put_object(
        user_id=user_id,
        bucket=tryon_bucket,
        object_key=object_key,
        data=rendered.image_bytes,
        content_type=rendered.mime_type,
    )

    media_asset = MediaAsset(
        id=media_asset_id,
        user_id=user_id,
        kind=MediaKind.MOODBOARD if rendered.fallback_used else MediaKind.TRYON,
        bucket=tryon_bucket,
        object_key=object_key,
        mime_type=rendered.mime_type,
        size_bytes=len(rendered.image_bytes),
        width=width,
        height=height,
        sha256=sha256(rendered.image_bytes).hexdigest(),
    )
    render = TryOnRender(
        id=tryon_id,
        user_id=user_id,
        outfit_id=outfit_id,
        media_asset_id=media_asset_id,
        provider=rendered.provider,
        model=rendered.model,
        fallback_used=rendered.fallback_used,
        duration_ms=duration_ms,
        status="ready",
    )
    try:
        session.add(media_asset)
        session.flush()
        session.add(render)
        session.commit()
    except Exception:
        session.rollback()
        try:
            storage.delete_object(
                user_id=user_id,
                bucket=tryon_bucket,
                object_key=object_key,
            )
        except Exception as delete_error:
            try:
                record_orphan_cleanup(
                    session=session,
                    user_id=user_id,
                    bucket=tryon_bucket,
                    object_key=object_key,
                    last_error=str(delete_error),
                )
                session.commit()
            except Exception:
                pass
        raise

    return TryOnResponseData(
        tryon_id=tryon_id,
        outfit_id=outfit_id,
        image_url=f"/api/v1/media/{media_asset_id}",
        render_kind="moodboard" if rendered.fallback_used else "generated_lookbook",
        fallback_used=rendered.fallback_used,
        duration_ms=duration_ms,
        status="ready",
    )
