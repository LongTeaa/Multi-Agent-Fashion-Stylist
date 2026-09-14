from __future__ import annotations

from collections import defaultdict
from sqlalchemy import func
from sqlmodel import Session, select

from app.agents.wardrobe_agent import format_localized_item_name
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    Rating,
    WardrobeCategory,
    WardrobeItem,
    WearLog,
    utc_now,
)
from app.schemas.common import OutfitNotFoundError
from app.schemas.outfits import (
    BookmarkOutfitResponseData,
    OutfitDetailResponseData,
    OutfitItemDetailResponse,
    SavedOutfitsResponseData,
)

SLOT_ORDER: dict[OutfitSlotRole, int] = {
    OutfitSlotRole.TOP: 0,
    OutfitSlotRole.BOTTOM: 1,
    OutfitSlotRole.DRESS: 2,
    OutfitSlotRole.OUTERWEAR: 3,
    OutfitSlotRole.FOOTWEAR: 4,
    OutfitSlotRole.ACCESSORY: 5,
}

MEDIA_ROLE_PRIORITY: dict[ItemMediaRole, int] = {
    ItemMediaRole.PRIMARY: 0,
    ItemMediaRole.THUMBNAIL: 1,
    ItemMediaRole.ALTERNATE: 2,
}


def _primary_media_id(session: Session, item_id: str, user_id: str) -> str | None:
    """Find highest-priority active media asset ID linked to a wardrobe item.

    Must join MediaAsset and verify deleted_at is None to prevent returning broken URLs.
    """
    links = session.exec(
        select(ItemMedia, MediaAsset)
        .join(MediaAsset, ItemMedia.media_asset_id == MediaAsset.id)
        .where(
            ItemMedia.wardrobe_item_id == item_id,
            ItemMedia.user_id == user_id,
            MediaAsset.deleted_at.is_(None),
        )
    ).all()
    if not links:
        return None
    return min(links, key=lambda pair: MEDIA_ROLE_PRIORITY.get(pair[0].role, 99))[0].media_asset_id


def _build_outfit_item_dto(
    oi: OutfitItem,
    w_item: WardrobeItem | None,
    media_id: str | None,
    user_id: str,
) -> OutfitItemDetailResponse:
    """Build a single OutfitItemDetailResponse with safe fallbacks."""
    if w_item is not None and w_item.user_id == user_id:
        image_url = f"/api/v1/media/{media_id}" if media_id else None
        is_active = w_item.is_active and (w_item.deleted_at is None)
        return OutfitItemDetailResponse(
            slot_role=oi.slot_role,
            wardrobe_item_id=oi.wardrobe_item_id,
            name=format_localized_item_name(w_item),
            category=w_item.category,
            sub_category=w_item.sub_category,
            primary_color=w_item.primary_color,
            secondary_color=w_item.secondary_color,
            pattern=w_item.pattern,
            material=w_item.material,
            style=w_item.style,
            image_url=image_url,
            is_active=is_active,
        )

    cat = (
        WardrobeCategory(oi.slot_role.value)
        if oi.slot_role.value in WardrobeCategory._value2member_map_
        else WardrobeCategory.TOP
    )
    return OutfitItemDetailResponse(
        slot_role=oi.slot_role,
        wardrobe_item_id=oi.wardrobe_item_id,
        name=f"Trang phục ({oi.slot_role.value})",
        category=cat,
        sub_category=oi.slot_role.value,
        primary_color="không xác định",
        secondary_color=None,
        pattern="trơn",
        material="vải",
        style="casual",
        image_url=None,
        is_active=False,
    )


def _build_outfit_detail_response(
    session: Session,
    outfit: OutfitRecommendation,
    user_id: str,
) -> OutfitDetailResponseData:
    """Transform an OutfitRecommendation entity into an OutfitDetailResponseData DTO."""
    # 1. Fetch and sort outfit items
    outfit_items = session.exec(
        select(OutfitItem).where(
            OutfitItem.outfit_id == outfit.id,
            OutfitItem.user_id == user_id,
        )
    ).all()
    sorted_outfit_items = sorted(
        outfit_items,
        key=lambda oi: SLOT_ORDER.get(oi.slot_role, 99),
    )

    # 2. Build item DTOs with active media check
    item_dtos: list[OutfitItemDetailResponse] = []
    for oi in sorted_outfit_items:
        w_item = session.get(WardrobeItem, oi.wardrobe_item_id)
        media_id = _primary_media_id(session, oi.wardrobe_item_id, user_id) if w_item else None
        item_dtos.append(_build_outfit_item_dto(oi, w_item, media_id, user_id))

    # 3. Aggregate wear history
    wear_stats = session.exec(
        select(
            func.count(WearLog.id),
            func.max(WearLog.worn_at),
        ).where(
            WearLog.outfit_id == outfit.id,
            WearLog.user_id == user_id,
        )
    ).first()
    times_worn = wear_stats[0] if wear_stats else 0
    last_worn_at = wear_stats[1] if wear_stats else None

    # 4. Fetch user rating
    rating = session.exec(
        select(Rating).where(
            Rating.outfit_id == outfit.id,
            Rating.user_id == user_id,
        )
    ).first()
    user_rating = rating.stars if rating is not None else None

    return OutfitDetailResponseData(
        id=outfit.id,
        request_id=outfit.request_id,
        user_query=outfit.user_query,
        explanation_vi=outfit.explanation_vi,
        fashion_score=outfit.fashion_score,
        personalization_score=outfit.personalization_score,
        composite_score=outfit.composite_score,
        rank=outfit.rank,
        is_bookmarked=outfit.is_bookmarked,
        times_worn=times_worn,
        last_worn_at=last_worn_at,
        user_rating=user_rating,
        items=item_dtos,
        created_at=outfit.created_at,
    )


def get_outfit_detail(
    session: Session,
    outfit_id: str,
    user_id: str,
) -> OutfitDetailResponseData:
    """Retrieve detailed outfit recommendation with item attributes, wear logs, and ratings."""
    outfit = session.exec(
        select(OutfitRecommendation).where(
            OutfitRecommendation.id == outfit_id,
            OutfitRecommendation.user_id == user_id,
        )
    ).first()
    if outfit is None:
        raise OutfitNotFoundError()
    return _build_outfit_detail_response(session, outfit, user_id)


def get_saved_outfits(
    session: Session,
    user_id: str,
    page: int = 1,
    page_size: int = 10,
) -> SavedOutfitsResponseData:
    """Retrieve paginated bookmarked outfits with batch prefetching to prevent N+1 queries."""
    base_query = select(OutfitRecommendation).where(
        OutfitRecommendation.user_id == user_id,
        OutfitRecommendation.is_bookmarked.is_(True),
    )

    # 1. Total count
    count_query = select(func.count()).select_from(base_query.subquery())
    total = session.exec(count_query).one()

    if total == 0:
        return SavedOutfitsResponseData(items=[], page=page, page_size=page_size, total=0)

    # 2. Deterministic order by created_at DESC, id DESC
    paginated_query = (
        base_query.order_by(
            OutfitRecommendation.created_at.desc(),
            OutfitRecommendation.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    outfits = session.exec(paginated_query).all()
    outfit_ids = [o.id for o in outfits]

    # 3. Batch prefetch outfit items
    all_outfit_items = session.exec(
        select(OutfitItem).where(
            OutfitItem.outfit_id.in_(outfit_ids),
            OutfitItem.user_id == user_id,
        )
    ).all()

    items_by_outfit: dict[str, list[OutfitItem]] = defaultdict(list)
    wardrobe_item_ids: set[str] = set()
    for oi in all_outfit_items:
        items_by_outfit[oi.outfit_id].append(oi)
        wardrobe_item_ids.add(oi.wardrobe_item_id)

    # 4. Batch prefetch wardrobe items
    wardrobe_map: dict[str, WardrobeItem] = {}
    if wardrobe_item_ids:
        w_items = session.exec(
            select(WardrobeItem).where(
                WardrobeItem.id.in_(wardrobe_item_ids),
                WardrobeItem.user_id == user_id,
            )
        ).all()
        wardrobe_map = {w.id: w for w in w_items}

    # 5. Batch prefetch active media (excluding soft-deleted MediaAsset)
    primary_media_map: dict[str, str] = {}
    if wardrobe_item_ids:
        media_links = session.exec(
            select(ItemMedia, MediaAsset)
            .join(MediaAsset, ItemMedia.media_asset_id == MediaAsset.id)
            .where(
                ItemMedia.wardrobe_item_id.in_(wardrobe_item_ids),
                ItemMedia.user_id == user_id,
                MediaAsset.deleted_at.is_(None),
            )
        ).all()

        media_by_item: dict[str, list[tuple[ItemMedia, MediaAsset]]] = defaultdict(list)
        for im, ma in media_links:
            media_by_item[im.wardrobe_item_id].append((im, ma))

        for w_id, links in media_by_item.items():
            best_link = min(links, key=lambda pair: MEDIA_ROLE_PRIORITY.get(pair[0].role, 99))
            primary_media_map[w_id] = best_link[0].media_asset_id

    # 6. Batch aggregate wear logs (COUNT and MAX)
    wear_stats = session.exec(
        select(
            WearLog.outfit_id,
            func.count(WearLog.id),
            func.max(WearLog.worn_at),
        )
        .where(
            WearLog.outfit_id.in_(outfit_ids),
            WearLog.user_id == user_id,
        )
        .group_by(WearLog.outfit_id)
    ).all()
    wear_map = {row[0]: (row[1], row[2]) for row in wear_stats}

    # 7. Batch prefetch ratings
    ratings = session.exec(
        select(Rating.outfit_id, Rating.stars).where(
            Rating.outfit_id.in_(outfit_ids),
            Rating.user_id == user_id,
        )
    ).all()
    rating_map = {r[0]: r[1] for r in ratings}

    # 8. Assemble response objects in-memory
    items: list[OutfitDetailResponseData] = []
    for outfit in outfits:
        ois = items_by_outfit.get(outfit.id, [])
        sorted_ois = sorted(ois, key=lambda oi: SLOT_ORDER.get(oi.slot_role, 99))
        item_dtos = [
            _build_outfit_item_dto(
                oi,
                wardrobe_map.get(oi.wardrobe_item_id),
                primary_media_map.get(oi.wardrobe_item_id),
                user_id,
            )
            for oi in sorted_ois
        ]

        tw, lw = wear_map.get(outfit.id, (0, None))
        ur = rating_map.get(outfit.id, None)

        items.append(
            OutfitDetailResponseData(
                id=outfit.id,
                request_id=outfit.request_id,
                user_query=outfit.user_query,
                explanation_vi=outfit.explanation_vi,
                fashion_score=outfit.fashion_score,
                personalization_score=outfit.personalization_score,
                composite_score=outfit.composite_score,
                rank=outfit.rank,
                is_bookmarked=outfit.is_bookmarked,
                times_worn=tw,
                last_worn_at=lw,
                user_rating=ur,
                items=item_dtos,
                created_at=outfit.created_at,
            )
        )

    return SavedOutfitsResponseData(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
    )


def set_outfit_bookmark(
    session: Session,
    outfit_id: str,
    user_id: str,
    is_bookmarked: bool,
) -> BookmarkOutfitResponseData:
    """Idempotently set or toggle the bookmark status of an owned outfit.

    Returns the persistent updated_at timestamp. On idempotent retries where
    the state does not change, updated_at remains stable.
    """
    outfit = session.exec(
        select(OutfitRecommendation).where(
            OutfitRecommendation.id == outfit_id,
            OutfitRecommendation.user_id == user_id,
        )
    ).first()
    if outfit is None:
        raise OutfitNotFoundError()

    if outfit.is_bookmarked != is_bookmarked:
        outfit.is_bookmarked = is_bookmarked
        outfit.updated_at = utc_now()
        session.add(outfit)
        session.commit()
        session.refresh(outfit)

    return BookmarkOutfitResponseData(
        outfit_id=outfit.id,
        is_bookmarked=outfit.is_bookmarked,
        updated_at=outfit.updated_at,
    )
