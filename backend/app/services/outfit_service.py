from __future__ import annotations

import random
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import timezone
from sqlalchemy import case, distinct, func, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from app.agents.wardrobe_agent import format_localized_item_name
from app.models.entities import (
    FeedbackPromptState,
    FeedbackSuppressedSession,
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    Rating,
    RatingSource,
    UserPreference,
    WardrobeCategory,
    WardrobeItem,
    WearLog,
    utc_now,
)
from app.schemas.common import IdempotencyConflictError, OutfitNotFoundError, ValidationError
from app.schemas.outfits import (
    BookmarkOutfitResponseData,
    OutfitDetailResponseData,
    OutfitItemDetailResponse,
    OutfitRatingRequest,
    OutfitRatingResponseData,
    SavedOutfitsResponseData,
    WornOutfitRequest,
    WornOutfitResponseData,
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


def _normalize_utc(dt: datetime | None) -> datetime | None:
    """Normalize datetime to timezone-aware UTC, or None."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
    last_worn_at = _normalize_utc(wear_stats[1]) if wear_stats else None

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
        lw = _normalize_utc(lw)
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


def _check_wear_log_idempotency_or_conflict(
    session: Session,
    existing_log: WearLog,
    outfit_id: str,
    user_id: str,
    payload: WornOutfitRequest,
) -> WornOutfitResponseData:
    """Validate idempotency retry or detect conflicting payload.

    Raises IdempotencyConflictError (409) if:
    - existing_log.outfit_id != outfit_id
    - payload.worn_at != existing_log.requested_worn_at
    """
    if existing_log.outfit_id != outfit_id:
        raise IdempotencyConflictError()

    req_worn = _normalize_utc(payload.worn_at)
    exist_req_worn = _normalize_utc(existing_log.requested_worn_at)

    if (req_worn is None and exist_req_worn is not None) or (
        req_worn is not None and exist_req_worn is None
    ):
        raise IdempotencyConflictError()

    if req_worn is not None and exist_req_worn is not None:
        if req_worn != exist_req_worn:
            raise IdempotencyConflictError()

    times_worn = session.exec(
        select(func.count(WearLog.id)).where(
            WearLog.outfit_id == outfit_id,
            WearLog.user_id == user_id,
        )
    ).one()

    ret_worn_at = _normalize_utc(existing_log.worn_at)

    return WornOutfitResponseData(
        wear_log_id=existing_log.id,
        outfit_id=outfit_id,
        worn_at=ret_worn_at,
        times_worn=times_worn,
        already_processed=True,
    )


def record_outfit_worn(
    session: Session,
    outfit_id: str,
    user_id: str,
    payload: WornOutfitRequest,
) -> WornOutfitResponseData:
    """Idempotently record that an owned outfit was worn, projecting wear history to wardrobe cache.

    - Validates outfit is owned and persisted.
    - Idempotency key scoped per user: repeated requests with identical key for the same outfit and payload
      return the existing wear record with already_processed=True.
    - Conflicting reuse of the key for a different outfit or different worn_at raises IdempotencyConflictError (409).
    - In an atomic transaction, persists WearLog and atomically increments times_worn on WardrobeItems via SQL UPDATE.
    - Preserves last_worn_at so historical/past timestamps do not rewind more recent wear events.
    - Concurrency-safe: catches IntegrityError on commit race and recovers gracefully.
    """
    # 1. Ownership & existence check
    outfit = session.exec(
        select(OutfitRecommendation).where(
            OutfitRecommendation.id == outfit_id,
            OutfitRecommendation.user_id == user_id,
        )
    ).first()
    if outfit is None:
        raise OutfitNotFoundError()

    # 2. Check for existing wear log with this idempotency key for this user
    existing_log = session.exec(
        select(WearLog).where(
            WearLog.user_id == user_id,
            WearLog.idempotency_key == payload.idempotency_key,
        )
    ).first()

    if existing_log is not None:
        return _check_wear_log_idempotency_or_conflict(
            session=session,
            existing_log=existing_log,
            outfit_id=outfit_id,
            user_id=user_id,
            payload=payload,
        )

    # 3. Fresh wear event: determine timestamp
    target_worn_at = _normalize_utc(payload.worn_at) or utc_now()
    req_worn_at = _normalize_utc(payload.worn_at)

    # 4. Fetch constituent outfit items BEFORE adding new_log to avoid autoflush race
    outfit_items = session.exec(
        select(OutfitItem).where(
            OutfitItem.outfit_id == outfit_id,
            OutfitItem.user_id == user_id,
        )
    ).all()
    wardrobe_item_ids = list({oi.wardrobe_item_id for oi in outfit_items})

    # Create new wear log with both applied worn_at and client-requested timestamp
    new_log = WearLog(
        user_id=user_id,
        outfit_id=outfit_id,
        worn_at=target_worn_at,
        requested_worn_at=req_worn_at,
        idempotency_key=payload.idempotency_key,
    )

    # 5. Persist log and perform atomic SQL UPDATE inside protected block
    try:
        session.add(new_log)

        if wardrobe_item_ids:
            update_stmt = (
                update(WardrobeItem)
                .where(
                    WardrobeItem.id.in_(wardrobe_item_ids),
                    WardrobeItem.user_id == user_id,
                )
                .values(
                    times_worn=WardrobeItem.times_worn + 1,
                    last_worn_at=case(
                        (WardrobeItem.last_worn_at.is_(None), target_worn_at),
                        (target_worn_at > WardrobeItem.last_worn_at, target_worn_at),
                        else_=WardrobeItem.last_worn_at,
                    ),
                    updated_at=utc_now(),
                )
            )
            session.exec(update_stmt)

        session.commit()
    except IntegrityError:
        session.rollback()
        # Concurrent race: another worker committed the same (user_id, idempotency_key)
        recovered_log = session.exec(
            select(WearLog).where(
                WearLog.user_id == user_id,
                WearLog.idempotency_key == payload.idempotency_key,
            )
        ).first()
        if recovered_log is not None:
            return _check_wear_log_idempotency_or_conflict(
                session=session,
                existing_log=recovered_log,
                outfit_id=outfit_id,
                user_id=user_id,
                payload=payload,
            )
        raise

    session.refresh(new_log)

    times_worn = session.exec(
        select(func.count(WearLog.id)).where(
            WearLog.outfit_id == outfit_id,
            WearLog.user_id == user_id,
        )
    ).one()

    ret_worn_at = _normalize_utc(new_log.worn_at)

    return WornOutfitResponseData(
        wear_log_id=new_log.id,
        outfit_id=outfit_id,
        worn_at=ret_worn_at,
        times_worn=times_worn,
        already_processed=False,
    )


RATING_WEIGHT_SIGNALS: dict[int, float] = {
    1: -1.0,
    2: -0.5,
    3: 0.0,
    4: 0.5,
    5: 1.0,
}
LEARNED_AFFINITY_EMA_ALPHA = 0.30
LEARNED_AFFINITY_MIN_WEIGHT = -1.0
LEARNED_AFFINITY_MAX_WEIGHT = 1.0


def _update_learned_feature_weights(
    session: Session,
    user_id: str,
    preferences: UserPreference,
) -> None:
    """Rebuild versioned learned weights using a deterministic per-feature EMA.

    - Features extracted per outfit:
      - style:{item.style}
      - color:{item.primary_color}
      - pattern:{item.pattern}
      - formality:low (level <= 2), formality:medium (level == 3), formality:high (level >= 4)
    - Signals mapped: 1=-1.0, 2=-0.5, 3=0.0, 4=0.5, 5=1.0.
    - Replays ratings by ``updated_at`` then ``id`` so an edited rating becomes
      the newest observation and repeated rebuilds produce the same result.
    - Applies alpha=0.30 independently per observed feature and clamps weights
      to [-1.0, 1.0].
    - Increments version number in {"version": v, "weights": weights}.
    """
    user_ratings = session.exec(
        select(Rating)
        .where(Rating.user_id == user_id)
        .order_by(Rating.updated_at.asc(), Rating.id.asc())
    ).all()

    if not user_ratings:
        return

    weights: dict[str, float] = {}

    for r in user_ratings:
        signal = RATING_WEIGHT_SIGNALS.get(r.stars, 0.0)

        outfit_items = session.exec(
            select(OutfitItem, WardrobeItem)
            .join(WardrobeItem, OutfitItem.wardrobe_item_id == WardrobeItem.id)
            .where(
                OutfitItem.outfit_id == r.outfit_id,
                OutfitItem.user_id == user_id,
            )
        ).all()

        outfit_features: set[str] = set()
        for _, item in outfit_items:
            if item.style:
                outfit_features.add(f"style:{item.style.lower().strip()}")
            if item.primary_color:
                outfit_features.add(f"color:{item.primary_color.lower().strip()}")
            if item.pattern:
                outfit_features.add(f"pattern:{item.pattern.lower().strip()}")
            if item.formality_level <= 2:
                outfit_features.add("formality:low")
            elif item.formality_level == 3:
                outfit_features.add("formality:medium")
            else:
                outfit_features.add("formality:high")

        for feat in sorted(outfit_features):
            previous = weights.get(feat)
            next_weight = (
                signal
                if previous is None
                else (
                    LEARNED_AFFINITY_EMA_ALPHA * signal
                    + (1.0 - LEARNED_AFFINITY_EMA_ALPHA) * previous
                )
            )
            weights[feat] = round(
                max(
                    LEARNED_AFFINITY_MIN_WEIGHT,
                    min(LEARNED_AFFINITY_MAX_WEIGHT, next_weight),
                ),
                4,
            )

    curr_version = 1
    if isinstance(preferences.learned_feature_weights, dict):
        raw_version = preferences.learned_feature_weights.get("version", 1)
        if isinstance(raw_version, int):
            curr_version = raw_version

    preferences.learned_feature_weights = {
        "version": curr_version + 1,
        "ema_alpha": LEARNED_AFFINITY_EMA_ALPHA,
        "min_weight": LEARNED_AFFINITY_MIN_WEIGHT,
        "max_weight": LEARNED_AFFINITY_MAX_WEIGHT,
        "weights": weights,
    }
    preferences.updated_at = utc_now()
    session.add(preferences)


def record_outfit_rating(
    session: Session,
    outfit_id: str,
    user_id: str,
    payload: OutfitRatingRequest,
    client_session_id: str | None = None,
    threshold_chooser: Callable[[], int] | None = None,
) -> OutfitRatingResponseData:
    """Idempotently create or update a 1–5 rating for an outfit and learn preferences."""
    # 1. Ownership & existence check
    outfit = session.exec(
        select(OutfitRecommendation).where(
            OutfitRecommendation.id == outfit_id,
            OutfitRecommendation.user_id == user_id,
        )
    ).first()
    if outfit is None:
        raise OutfitNotFoundError()

    effective_session_id = payload.client_session_id or client_session_id
    if payload.source == RatingSource.PROMPTED and not effective_session_id:
        raise ValidationError(
            message="Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.",
            details={"field": "client_session_id", "reason": "required_when_prompted"},
        )

    now = utc_now()
    max_attempts = 5

    for attempt in range(max_attempts):
        try:
            # 2. Check existing rating
            rating = session.exec(
                select(Rating).where(
                    Rating.outfit_id == outfit_id,
                    Rating.user_id == user_id,
                )
            ).first()

            # 3. Exact duplicate PUT check (true idempotency: strict no-op)
            if (
                rating is not None
                and rating.stars == payload.stars
                and rating.source == payload.source
            ):
                if effective_session_id:
                    existing_suppression = session.exec(
                        select(FeedbackSuppressedSession).where(
                            FeedbackSuppressedSession.user_id == user_id,
                            FeedbackSuppressedSession.client_session_id == effective_session_id,
                        )
                    ).first()
                    if existing_suppression is None:
                        suppression = FeedbackSuppressedSession(
                            user_id=user_id,
                            client_session_id=effective_session_id,
                            created_at=now,
                        )
                        session.add(suppression)
                        session.commit()
                        session.refresh(rating)

                preferences = session.get(UserPreference, user_id)
                if preferences and preferences.ratings_count is not None:
                    ratings_count = preferences.ratings_count
                else:
                    ratings_count = session.exec(
                        select(func.count(distinct(Rating.outfit_id))).where(
                            Rating.user_id == user_id
                        )
                    ).one()

                return OutfitRatingResponseData(
                    rating_id=rating.id,
                    outfit_id=outfit_id,
                    stars=rating.stars,
                    source=rating.source,
                    ratings_count=ratings_count,
                    created_at=_normalize_utc(rating.created_at),
                    updated_at=_normalize_utc(rating.updated_at),
                )

            # 4. Upsert rating record
            if rating is None:
                rating = Rating(
                    user_id=user_id,
                    outfit_id=outfit_id,
                    stars=payload.stars,
                    source=payload.source,
                    created_at=now,
                    updated_at=now,
                )
                session.add(rating)
            else:
                rating.stars = payload.stars
                rating.source = payload.source
                rating.updated_at = now
                session.add(rating)

            session.flush()

            # 5. Calculate distinct ratings count for this user
            ratings_count = session.exec(
                select(func.count(distinct(Rating.outfit_id))).where(
                    Rating.user_id == user_id
                )
            ).one()

            # 6. Ensure UserPreference and update learned weights
            preferences = session.get(UserPreference, user_id)
            if preferences is None:
                preferences = UserPreference(user_id=user_id)
                session.add(preferences)
                session.flush()

            preferences.ratings_count = ratings_count
            _update_learned_feature_weights(session, user_id, preferences)

            # 7. Multi-session suppression: if client_session_id is provided, record it
            if effective_session_id:
                existing_suppression = session.exec(
                    select(FeedbackSuppressedSession).where(
                        FeedbackSuppressedSession.user_id == user_id,
                        FeedbackSuppressedSession.client_session_id == effective_session_id,
                    )
                ).first()
                if existing_suppression is None:
                    suppression = FeedbackSuppressedSession(
                        user_id=user_id,
                        client_session_id=effective_session_id,
                        created_at=now,
                    )
                    session.add(suppression)

            prompt_state = session.get(FeedbackPromptState, user_id)
            chosen_val = threshold_chooser() if threshold_chooser else random.randint(5, 10)
            chosen_threshold = max(5, min(10, int(chosen_val)))
            if prompt_state is None:
                prompt_state = FeedbackPromptState(
                    user_id=user_id,
                    eligible_count_since_prompt=0,
                    next_threshold=chosen_threshold,
                    cooldown_remaining=0,
                    last_rated_at=now,
                )
                session.add(prompt_state)
            else:
                prompt_state.eligible_count_since_prompt = 0
                prompt_state.cooldown_remaining = 0
                prompt_state.last_rated_at = now
                prompt_state.next_threshold = chosen_threshold
                session.add(prompt_state)

            session.commit()
            session.refresh(rating)

            return OutfitRatingResponseData(
                rating_id=rating.id,
                outfit_id=outfit_id,
                stars=rating.stars,
                source=rating.source,
                ratings_count=ratings_count,
                created_at=_normalize_utc(rating.created_at),
                updated_at=_normalize_utc(rating.updated_at),
            )
        except (IntegrityError, OperationalError):
            session.rollback()
            if attempt == max_attempts - 1:
                raise
            time.sleep(0.01 * (attempt + 1))
