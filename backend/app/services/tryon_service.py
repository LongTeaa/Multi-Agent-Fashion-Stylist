from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import logging
from pathlib import Path
from time import monotonic
from typing import Literal, cast

from PIL import Image, UnidentifiedImageError
from sqlalchemy import and_
from sqlmodel import Session, select

from app.models.entities import (
    InputKind,
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    OutfitItem,
    OutfitRecommendation,
    TryOnAvatar,
    TryOnRender,
    User,
    WardrobeCategory,
    WardrobeItem,
    new_uuid,
    utc_now,
)
from app.repositories.object_storage import ObjectNotFoundError, ObjectStorage
from app.schemas.common import (
    ForbiddenAssetError,
    ItemNotFoundError,
    OutfitNotFoundError,
    TryOnFailedError,
    ValidationError,
)
from app.schemas.tryons import TryOnAvatarResponse, TryOnResponseData
from app.services.classifier import PERSON_LABELS
from app.services.cleanup_service import record_orphan_cleanup, stage_object_upload
from app.services.image_generation import render_lookbook_with_fallback
from app.services.moodboard import MoodboardItem
from app.services.providers import (
    DetectorProtocol,
    ImageProviderProtocol,
    ImageReference,
    TryOnProviderProtocol,
    TryOnRequest as ProviderTryOnRequest,
)
from app.services.tryon_prompt import LookbookPromptItem, build_lookbook_prompt

logger = logging.getLogger(__name__)

PRESET_AVATARS: tuple[dict[str, object], ...] = (
    {
        "id": "preset-male",
        "name": "Nam mẫu (Chuẩn)",
        "is_preset": True,
        "preset_gender": "male",
        "is_default": False,
        "image_url": "/api/v1/tryons/presets/male",
    },
    {
        "id": "preset-female",
        "name": "Nữ mẫu (Chuẩn)",
        "is_preset": True,
        "preset_gender": "female",
        "is_default": False,
        "image_url": "/api/v1/tryons/presets/female",
    },
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "tryon_presets"


def _image_dimensions(image_bytes: bytes) -> tuple[int, int]:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
            return image.size
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise TryOnFailedError() from error


def get_preset_avatar_bytes(preset_gender: str) -> bytes:
    """Return raw WebP image bytes for standard system preset models."""
    gender = preset_gender.lower().strip()
    if gender not in ("male", "female"):
        raise ValidationError(
            message="Giới tính người mẫu không hợp lệ.",
            details={"field": "preset_gender", "allowed": ["male", "female"]},
        )
    preset_file = ASSETS_DIR / f"{gender}.webp"
    if not preset_file.is_file():
        raise TryOnFailedError(message=f"Không tìm thấy ảnh mẫu {preset_gender}.")
    return preset_file.read_bytes()


def list_tryon_avatars(session: Session, user_id: str) -> list[TryOnAvatarResponse]:
    """List system preset avatars followed by user-uploaded avatars."""
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    results: list[TryOnAvatarResponse] = [
        TryOnAvatarResponse(
            id=str(p["id"]),
            name=str(p["name"]),
            is_preset=bool(p["is_preset"]),
            preset_gender=str(p["preset_gender"]),
            is_default=bool(p["is_default"]),
            image_url=str(p["image_url"]),
            created_at=base_time,
        )
        for p in PRESET_AVATARS
    ]

    user_avatars = session.exec(
        select(TryOnAvatar)
        .where(
            TryOnAvatar.user_id == user_id,
            TryOnAvatar.deleted_at.is_(None),
        )
        .order_by(TryOnAvatar.created_at.desc())
    ).all()

    for avatar in user_avatars:
        if avatar.media_asset_id:
            results.append(
                TryOnAvatarResponse(
                    id=avatar.id,
                    name=avatar.name,
                    is_preset=False,
                    preset_gender=avatar.preset_gender,
                    is_default=avatar.is_default,
                    image_url=f"/api/v1/media/{avatar.media_asset_id}",
                    created_at=avatar.created_at,
                )
            )

    return results


def create_user_avatar(
    *,
    session: Session,
    storage: ObjectStorage,
    detector: DetectorProtocol | None,
    user_id: str,
    file_bytes: bytes,
    filename: str,
    tryon_bucket: str,
) -> TryOnAvatarResponse:
    """Validate, transcode, verify person presence, and persist user-uploaded avatar."""
    if len(file_bytes) > 10 * 1024 * 1024:
        raise ValidationError(message="Kích thước ảnh tối đa là 10MB.")

    try:
        with Image.open(BytesIO(file_bytes)) as pil_img:
            pil_img.verify()
        with Image.open(BytesIO(file_bytes)) as pil_img:
            rgb_img = pil_img.convert("RGB")
            max_dim = max(rgb_img.size)
            if max_dim > 1536:
                scale = 1536.0 / max_dim
                new_size = (int(rgb_img.width * scale), int(rgb_img.height * scale))
                rgb_img = rgb_img.resize(new_size, Image.Resampling.LANCZOS)
            out_buf = BytesIO()
            rgb_img.save(out_buf, format="WEBP", quality=90)
            webp_bytes = out_buf.getvalue()
            width, height = rgb_img.size
    except Exception as err:
        raise ValidationError(message="Định dạng ảnh không hợp lệ hoặc tệp bị hỏng.") from err

    if detector is not None:
        try:
            detection = detector.detect(file_bytes)
            input_kind_val = getattr(detection.input_kind, "value", str(detection.input_kind))
            has_person = (
                detection.person_box is not None
                or input_kind_val == InputKind.WORN_OUTFIT.value
                or any(
                    getattr(b, "label", "").strip().lower() in PERSON_LABELS
                    for b in detection.boxes
                )
            )
            if not has_person:
                raise ValidationError(
                    message="Không phát hiện người hoặc toàn thân trong ảnh. Vui lòng chụp rõ toàn bộ người."
                )
        except ValidationError:
            raise
        except Exception as det_err:
            logger.warning("Detector error during avatar person validation: %s", det_err)

    if session.get(User, user_id) is None:
        session.add(User(id=user_id))
        session.commit()

    avatar_id = new_uuid()
    media_asset_id = new_uuid()
    object_key = f"users/{user_id}/avatars/{avatar_id}/source.webp"

    upload_manifest = stage_object_upload(
        session=session,
        user_id=user_id,
        bucket=tryon_bucket,
        object_key=object_key,
    )
    storage.put_object(
        user_id=user_id,
        bucket=tryon_bucket,
        object_key=object_key,
        data=webp_bytes,
        content_type="image/webp",
    )

    media_asset = MediaAsset(
        id=media_asset_id,
        user_id=user_id,
        kind=MediaKind.TRYON,
        bucket=tryon_bucket,
        object_key=object_key,
        mime_type="image/webp",
        size_bytes=len(webp_bytes),
        width=width,
        height=height,
        sha256=sha256(webp_bytes).hexdigest(),
    )
    clean_name = (filename or "Ảnh của tôi").strip()[:100]
    avatar = TryOnAvatar(
        id=avatar_id,
        user_id=user_id,
        media_asset_id=media_asset_id,
        name=clean_name if clean_name else "Ảnh của tôi",
        is_preset=False,
        is_default=False,
        consent_at=utc_now(),
        created_at=utc_now(),
    )

    try:
        session.add(media_asset)
        session.flush()
        session.add(avatar)
        session.delete(upload_manifest)
        session.commit()
        session.refresh(avatar)
    except Exception:
        session.rollback()
        try:
            storage.delete_object(
                user_id=user_id,
                bucket=tryon_bucket,
                object_key=object_key,
            )
        except Exception as delete_error:
            logger.error("Avatar upload cleanup failed for %s: %s", object_key, delete_error)
        raise

    return TryOnAvatarResponse(
        id=avatar.id,
        name=avatar.name,
        is_preset=False,
        preset_gender=None,
        is_default=avatar.is_default,
        image_url=f"/api/v1/media/{media_asset_id}",
        created_at=avatar.created_at,
    )


def delete_user_avatar(
    *,
    session: Session,
    user_id: str,
    avatar_id: str,
    storage: ObjectStorage | None = None,
) -> None:
    """Soft-delete a user-uploaded avatar and remove its underlying media object."""
    avatar = session.exec(
        select(TryOnAvatar).where(
            TryOnAvatar.id == avatar_id,
            TryOnAvatar.user_id == user_id,
            TryOnAvatar.deleted_at.is_(None),
        )
    ).first()
    if avatar is None:
        raise ItemNotFoundError(message="Không tìm thấy ảnh đại diện / người mẫu này.")

    now = utc_now()
    avatar.deleted_at = now
    if avatar.media_asset_id:
        asset = session.get(MediaAsset, avatar.media_asset_id)
        if asset is not None and asset.user_id == user_id:
            asset.deleted_at = now
            if storage is not None:
                try:
                    storage.delete_object(
                        user_id=asset.user_id,
                        bucket=asset.bucket,
                        object_key=asset.object_key,
                    )
                except ObjectNotFoundError:
                    pass
                except Exception as del_err:
                    logger.warning(
                        "Failed to delete avatar file %s from storage: %s",
                        asset.object_key,
                        del_err,
                    )
                    record_orphan_cleanup(
                        session=session,
                        user_id=asset.user_id,
                        bucket=asset.bucket,
                        object_key=asset.object_key,
                        last_error=str(del_err),
                    )
    session.commit()


def get_tryon_render_by_id(
    session: Session,
    user_id: str,
    tryon_id: str,
) -> TryOnResponseData:
    """Retrieve an existing tryon render by id for status polling."""
    render = session.get(TryOnRender, tryon_id)
    if render is None or render.user_id != user_id:
        raise ItemNotFoundError(message="Không tìm thấy kết quả thử đồ này.")

    render_kind_val: Literal["virtual_tryon", "generated_lookbook", "moodboard"] = "moodboard"
    if render.render_mode == "virtual_tryon":
        render_kind_val = "virtual_tryon"
    elif render.render_mode == "lookbook":
        render_kind_val = "moodboard" if render.fallback_used else "generated_lookbook"

    return TryOnResponseData(
        tryon_id=render.id,
        outfit_id=render.outfit_id,
        image_url=f"/api/v1/media/{render.media_asset_id}" if render.media_asset_id else None,
        render_kind=render_kind_val,
        fallback_used=render.fallback_used,
        duration_ms=render.duration_ms,
        status="ready" if render.status == "ready" else "failed",
        error_code=render.error_code,
    )


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

    item_ids = [oi.wardrobe_item_id for oi in outfit_items]

    wardrobe_items_map: dict[str, WardrobeItem] = {
        wi.id: wi
        for wi in session.exec(
            select(WardrobeItem).where(
                WardrobeItem.id.in_(item_ids),
                WardrobeItem.user_id == user_id,
                WardrobeItem.is_user_confirmed.is_(True),
            )
        ).all()
    }

    media_rows = session.exec(
        select(ItemMedia, MediaAsset)
        .join(
            MediaAsset,
            and_(
                ItemMedia.media_asset_id == MediaAsset.id,
                ItemMedia.user_id == MediaAsset.user_id,
            ),
        )
        .where(
            ItemMedia.wardrobe_item_id.in_(item_ids),
            ItemMedia.user_id == user_id,
            ItemMedia.role == ItemMediaRole.PRIMARY,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at, MediaAsset.id)
    ).all()
    media_map: dict[str, MediaAsset] = {}
    for item_media, media_asset in media_rows:
        if item_media.wardrobe_item_id not in media_map:
            media_map[item_media.wardrobe_item_id] = media_asset

    prompt_items: list[LookbookPromptItem] = []
    references: list[ImageReference] = []
    moodboard_items: list[MoodboardItem] = []
    for outfit_item in outfit_items:
        wardrobe_item = wardrobe_items_map.get(outfit_item.wardrobe_item_id)
        media_asset = media_map.get(outfit_item.wardrobe_item_id)
        if wardrobe_item is None or media_asset is None:
            raise TryOnFailedError()

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
    provider: ImageProviderProtocol | None = None,
    tryon_provider: TryOnProviderProtocol | None = None,
    outfit_id: str | None = None,
    user_id: str,
    tryon_bucket: str,
    avatar_id: str | None = None,
    item_ids: list[str] | None = None,
    timeout_seconds: float = 8,
    performance_clock: Callable[[], float] = monotonic,
) -> TryOnResponseData:
    """Create either an illustrative lookbook or a personalized 2D virtual try-on render."""
    if not outfit_id:
        raise ValidationError(message="Cần chọn một bộ trang phục để mặc thử.")

    started_at = performance_clock()
    prompt_items, references, moodboard_items = _load_outfit_assets(
        session=session,
        storage=storage,
        outfit_id=outfit_id,
        user_id=user_id,
    )

    # ---------------------------------------------------------
    # Mode A: Personalized Virtual Try-On (avatar_id provided)
    # ---------------------------------------------------------
    if avatar_id:
        return _execute_virtual_tryon(
            session=session,
            storage=storage,
            tryon_provider=tryon_provider,
            outfit_id=outfit_id,
            user_id=user_id,
            avatar_id=avatar_id,
            requested_item_ids=item_ids,
            tryon_bucket=tryon_bucket,
            moodboard_items=moodboard_items,
            started_at=started_at,
            performance_clock=performance_clock,
        )

    # ---------------------------------------------------------
    # Mode B: Standard Lookbook / Moodboard (avatar_id not provided)
    # ---------------------------------------------------------
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
    upload_manifest = stage_object_upload(
        session=session,
        user_id=user_id,
        bucket=tryon_bucket,
        object_key=object_key,
    )
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
        render_mode="lookbook",
    )
    try:
        session.add(media_asset)
        session.flush()
        session.add(render)
        session.delete(upload_manifest)
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
            logger.error("Try-on cleanup failed for %s: %s", object_key, delete_error)
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


def _execute_virtual_tryon(
    *,
    session: Session,
    storage: ObjectStorage,
    tryon_provider: TryOnProviderProtocol | None,
    outfit_id: str,
    user_id: str,
    avatar_id: str,
    requested_item_ids: list[str] | None,
    tryon_bucket: str,
    moodboard_items: tuple[MoodboardItem, ...],
    started_at: float,
    performance_clock: Callable[[], float],
) -> TryOnResponseData:
    """Execute personalized virtual try-on with avatar, caching, and deterministic fallback."""

    # 1. Resolve avatar person image
    avatar_record: TryOnAvatar | None = None
    if avatar_id in ("preset-male", "male"):
        person_bytes = get_preset_avatar_bytes("male")
    elif avatar_id in ("preset-female", "female"):
        person_bytes = get_preset_avatar_bytes("female")
    else:
        avatar_record = session.exec(
            select(TryOnAvatar).where(
                TryOnAvatar.id == avatar_id,
                TryOnAvatar.user_id == user_id,
                TryOnAvatar.deleted_at.is_(None),
            )
        ).first()
        if avatar_record is None or not avatar_record.media_asset_id:
            raise ValidationError(message="Không tìm thấy người mẫu / ảnh đại diện đã chọn.")

        avatar_asset = session.get(MediaAsset, avatar_record.media_asset_id)
        if avatar_asset is None or avatar_asset.user_id != user_id:
            raise ValidationError(message="Không tìm thấy tệp ảnh của người mẫu đã chọn.")

        person_bytes = storage.get_object(
            user_id=user_id,
            bucket=avatar_asset.bucket,
            object_key=avatar_asset.object_key,
        )

    # 2. Resolve outfit items
    outfit_items = session.exec(
        select(OutfitItem)
        .where(
            OutfitItem.outfit_id == outfit_id,
            OutfitItem.user_id == user_id,
        )
    ).all()
    all_item_ids = [oi.wardrobe_item_id for oi in outfit_items]

    wardrobe_items = session.exec(
        select(WardrobeItem).where(
            WardrobeItem.id.in_(all_item_ids),
            WardrobeItem.user_id == user_id,
            WardrobeItem.is_user_confirmed.is_(True),
        )
    ).all()
    item_map = {item.id: item for item in wardrobe_items}

    # Primary media mapping
    media_rows = session.exec(
        select(ItemMedia, MediaAsset)
        .join(
            MediaAsset,
            and_(
                ItemMedia.media_asset_id == MediaAsset.id,
                ItemMedia.user_id == MediaAsset.user_id,
            ),
        )
        .where(
            ItemMedia.wardrobe_item_id.in_(all_item_ids),
            ItemMedia.user_id == user_id,
            ItemMedia.role == ItemMediaRole.PRIMARY,
            MediaAsset.deleted_at.is_(None),
        )
        .order_by(MediaAsset.created_at, MediaAsset.id)
    ).all()
    media_map: dict[str, MediaAsset] = {}
    for im, ma in media_rows:
        if im.wardrobe_item_id not in media_map:
            media_map[im.wardrobe_item_id] = ma

    # 3. Categorize candidate try-on items
    # Categories supported by FASHN: tops, bottoms, one-pieces.
    tops_item: WardrobeItem | None = None
    bottoms_item: WardrobeItem | None = None
    dress_item: WardrobeItem | None = None

    for item in wardrobe_items:
        if requested_item_ids is not None and item.id not in requested_item_ids:
            continue
        if item.id not in media_map:
            continue
        if item.category == WardrobeCategory.DRESS:
            dress_item = item
        elif item.category == WardrobeCategory.BOTTOM:
            bottoms_item = item
        elif item.category == WardrobeCategory.OUTERWEAR:
            # Outerwear takes precedence over top when both exist
            tops_item = item
        elif item.category == WardrobeCategory.TOP and tops_item is None:
            tops_item = item

    # Collect selected items for try-on
    chosen_items: list[WardrobeItem] = []
    if dress_item is not None:
        chosen_items = [dress_item]
    else:
        if tops_item is not None:
            chosen_items.append(tops_item)
        if bottoms_item is not None:
            chosen_items.append(bottoms_item)

    selected_ids = sorted([it.id for it in chosen_items])

    # 4. Cache check: sha256(user_id:avatar_id:sorted_item_ids)
    cache_key = sha256(f"{user_id}:{avatar_id}:{','.join(selected_ids)}".encode()).hexdigest()
    cached_render = session.exec(
        select(TryOnRender).where(
            TryOnRender.user_id == user_id,
            TryOnRender.cache_key == cache_key,
            TryOnRender.status == "ready",
            TryOnRender.fallback_used == False,
        )
    ).first()
    if cached_render is not None and cached_render.media_asset_id:
        return TryOnResponseData(
            tryon_id=cached_render.id,
            outfit_id=cached_render.outfit_id,
            image_url=f"/api/v1/media/{cached_render.media_asset_id}",
            render_kind="virtual_tryon" if cached_render.render_mode == "virtual_tryon" else "moodboard",
            fallback_used=cached_render.fallback_used,
            duration_ms=0,
            status="ready",
            error_code=cached_render.error_code,
        )

    # 5. Check if provider is available
    if tryon_provider is None or not chosen_items:
        # Fall back to deterministic moodboard immediately
        return _fallback_to_moodboard(
            session=session,
            storage=storage,
            outfit_id=outfit_id,
            user_id=user_id,
            avatar_id=avatar_id,
            selected_ids=selected_ids,
            cache_key=cache_key,
            moodboard_items=moodboard_items,
            tryon_bucket=tryon_bucket,
            started_at=started_at,
            performance_clock=performance_clock,
            error_code="PROVIDER_DISABLED" if tryon_provider is None else "NO_COMPATIBLE_GARMENTS",
        )

    # 6. Execute multi-pass try-on
    try:
        current_person_bytes = person_bytes

        if dress_item is not None:
            garment_asset = media_map[dress_item.id]
            garment_bytes = storage.get_object(
                user_id=user_id,
                bucket=garment_asset.bucket,
                object_key=garment_asset.object_key,
            )
            g_mime = cast(
                Literal["image/jpeg", "image/png", "image/webp"],
                garment_asset.mime_type or "image/jpeg",
            )
            res = tryon_provider.try_on(
                ProviderTryOnRequest(
                    person_image_bytes=current_person_bytes,
                    person_mime_type="image/webp",
                    garment_image_bytes=garment_bytes,
                    garment_mime_type=g_mime,
                    category="one-pieces",
                )
            )
            current_person_bytes = res.image_bytes
        else:
            if tops_item is not None:
                garment_asset = media_map[tops_item.id]
                garment_bytes = storage.get_object(
                    user_id=user_id,
                    bucket=garment_asset.bucket,
                    object_key=garment_asset.object_key,
                )
                g_mime = cast(
                    Literal["image/jpeg", "image/png", "image/webp"],
                    garment_asset.mime_type or "image/jpeg",
                )
                res = tryon_provider.try_on(
                    ProviderTryOnRequest(
                        person_image_bytes=current_person_bytes,
                        person_mime_type="image/webp",
                        garment_image_bytes=garment_bytes,
                        garment_mime_type=g_mime,
                        category="tops",
                    )
                )
                current_person_bytes = res.image_bytes

            if bottoms_item is not None:
                garment_asset = media_map[bottoms_item.id]
                garment_bytes = storage.get_object(
                    user_id=user_id,
                    bucket=garment_asset.bucket,
                    object_key=garment_asset.object_key,
                )
                g_mime = cast(
                    Literal["image/jpeg", "image/png", "image/webp"],
                    garment_asset.mime_type or "image/jpeg",
                )
                res = tryon_provider.try_on(
                    ProviderTryOnRequest(
                        person_image_bytes=current_person_bytes,
                        person_mime_type="image/webp",
                        garment_image_bytes=garment_bytes,
                        garment_mime_type=g_mime,
                        category="bottoms",
                    )
                )
                current_person_bytes = res.image_bytes

        final_image_bytes = current_person_bytes
        width, height = _image_dimensions(final_image_bytes)
        duration_ms = max(0, round((performance_clock() - started_at) * 1000))

        tryon_id, media_asset_id = new_uuid(), new_uuid()
        object_key = f"users/{user_id}/tryons/{tryon_id}/render.webp"
        upload_manifest = stage_object_upload(
            session=session,
            user_id=user_id,
            bucket=tryon_bucket,
            object_key=object_key,
        )
        storage.put_object(
            user_id=user_id,
            bucket=tryon_bucket,
            object_key=object_key,
            data=final_image_bytes,
            content_type="image/webp",
        )

        media_asset = MediaAsset(
            id=media_asset_id,
            user_id=user_id,
            kind=MediaKind.TRYON,
            bucket=tryon_bucket,
            object_key=object_key,
            mime_type="image/webp",
            size_bytes=len(final_image_bytes),
            width=width,
            height=height,
            sha256=sha256(final_image_bytes).hexdigest(),
        )
        render = TryOnRender(
            id=tryon_id,
            user_id=user_id,
            outfit_id=outfit_id,
            media_asset_id=media_asset_id,
            avatar_id=avatar_id,
            selected_item_ids=selected_ids,
            cache_key=cache_key,
            render_mode="virtual_tryon",
            provider=tryon_provider.provider_name,
            model=tryon_provider.model,
            fallback_used=False,
            duration_ms=duration_ms,
            status="ready",
        )
        try:
            session.add(media_asset)
            session.flush()
            session.add(render)
            session.delete(upload_manifest)
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
                logger.error("Virtual try-on cleanup failed for %s: %s", object_key, delete_error)
            raise

        return TryOnResponseData(
            tryon_id=tryon_id,
            outfit_id=outfit_id,
            image_url=f"/api/v1/media/{media_asset_id}",
            render_kind="virtual_tryon",
            fallback_used=False,
            duration_ms=duration_ms,
            status="ready",
        )

    except Exception as exc:
        logger.warning(
            "Virtual try-on execution failed, falling back to deterministic Moodboard: %s",
            exc,
            exc_info=True,
        )
        return _fallback_to_moodboard(
            session=session,
            storage=storage,
            outfit_id=outfit_id,
            user_id=user_id,
            avatar_id=avatar_id,
            selected_ids=selected_ids,
            cache_key=cache_key,
            moodboard_items=moodboard_items,
            tryon_bucket=tryon_bucket,
            started_at=started_at,
            performance_clock=performance_clock,
            error_code="PROVIDER_FAILED",
        )


def _fallback_to_moodboard(
    *,
    session: Session,
    storage: ObjectStorage,
    outfit_id: str,
    user_id: str,
    avatar_id: str,
    selected_ids: list[str],
    cache_key: str,
    moodboard_items: tuple[MoodboardItem, ...],
    tryon_bucket: str,
    started_at: float,
    performance_clock: Callable[[], float],
    error_code: str,
) -> TryOnResponseData:
    """Create and persist a deterministic moodboard image when try-on fails or is unavailable."""
    from app.services.moodboard import render_moodboard

    moodboard_res = render_moodboard(moodboard_items)
    moodboard_bytes = moodboard_res.image_bytes
    width, height = moodboard_res.width, moodboard_res.height
    duration_ms = max(0, round((performance_clock() - started_at) * 1000))

    tryon_id, media_asset_id = new_uuid(), new_uuid()
    object_key = f"users/{user_id}/tryons/{tryon_id}/render.webp"
    upload_manifest = stage_object_upload(
        session=session,
        user_id=user_id,
        bucket=tryon_bucket,
        object_key=object_key,
    )
    storage.put_object(
        user_id=user_id,
        bucket=tryon_bucket,
        object_key=object_key,
        data=moodboard_bytes,
        content_type="image/webp",
    )

    media_asset = MediaAsset(
        id=media_asset_id,
        user_id=user_id,
        kind=MediaKind.MOODBOARD,
        bucket=tryon_bucket,
        object_key=object_key,
        mime_type="image/webp",
        size_bytes=len(moodboard_bytes),
        width=width,
        height=height,
        sha256=sha256(moodboard_bytes).hexdigest(),
    )
    render = TryOnRender(
        id=tryon_id,
        user_id=user_id,
        outfit_id=outfit_id,
        media_asset_id=media_asset_id,
        avatar_id=avatar_id,
        selected_item_ids=selected_ids,
        cache_key=cache_key,
        render_mode="moodboard",
        provider="local",
        model="deterministic-moodboard",
        fallback_used=True,
        error_code=error_code,
        duration_ms=duration_ms,
        status="ready",
    )
    try:
        session.add(media_asset)
        session.flush()
        session.add(render)
        session.delete(upload_manifest)
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
            logger.error("Fallback moodboard cleanup failed for %s: %s", object_key, delete_error)
        raise

    return TryOnResponseData(
        tryon_id=tryon_id,
        outfit_id=outfit_id,
        image_url=f"/api/v1/media/{media_asset_id}",
        render_kind="moodboard",
        fallback_used=True,
        duration_ms=duration_ms,
        status="ready",
        error_code=error_code,
    )
