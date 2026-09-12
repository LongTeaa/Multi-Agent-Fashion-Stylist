from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import logging
import math
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlmodel import Session, select

from app.agents.fashion_agent import NO_COMPLETE_OUTFIT_ERROR
from app.agents.state import StylistGraphState
from app.agents.wardrobe_agent import EMPTY_WARDROBE_ERROR
from app.core.dependencies import (
    StylistRunner,
    get_current_user_id,
    get_context_llm_provider,
    get_db_session,
    get_stylist_runner,
    get_utc_clock,
    get_weather_provider,
)
from app.models.entities import (
    OutfitItem,
    OutfitRecommendation,
    WardrobeItem,
    new_uuid,
)
from app.schemas.common import (
    ErrorResponse,
    NoCompleteOutfitError,
    ProviderError,
    SuccessResponse,
    WardrobeEmptyError,
)
from app.schemas.stylist import (
    StylistChatRequest,
    StylistChatResponseData,
    StylistContextResponse,
    StylistRecommendationItemResponse,
    StylistRecommendationResponse,
)
from app.services.providers import ContextLLMProviderProtocol, WeatherProviderProtocol

router = APIRouter(prefix="/stylist", tags=["stylist"])
logger = logging.getLogger(__name__)


def _map_context(ctx: Any) -> StylistContextResponse:
    """Map internal StylistContext to public allowlist StylistContextResponse."""
    return StylistContextResponse(
        occasion=ctx.occasion,
        time_of_day=ctx.time_of_day,
        event_date=ctx.event_date,
        location_text=ctx.location_text,
        environment=ctx.environment,
        weather_condition=ctx.weather_condition,
        temperature_celsius=ctx.temperature_celsius,
        target_formality_range=list(ctx.target_formality_range or []),
        style_hints=list(ctx.style_hints or []),
        vibe_keywords=list(ctx.vibe_keywords or []),
        must_have=list(ctx.must_have or []),
        must_avoid=list(ctx.must_avoid or []),
        weather_source=ctx.weather_source or "default",
    )


@router.post(
    "/chat",
    response_model=SuccessResponse[StylistChatResponseData],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
    },
)
def stylist_chat(
    payload: StylistChatRequest,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
    clock: Callable[[], datetime] = Depends(get_utc_clock),
    runner: StylistRunner = Depends(get_stylist_runner),
    llm_provider: ContextLLMProviderProtocol | None = Depends(get_context_llm_provider),
    weather_provider: WeatherProviderProtocol | None = Depends(get_weather_provider),
) -> SuccessResponse[StylistChatResponseData]:
    """Execute the AI stylist recommendation pipeline for the authenticated user."""
    request_id = new_uuid()
    initial_state: StylistGraphState = {
        "request_id": request_id,
        "user_id": user_id,
        "user_query": payload.query,
        "location": payload.location,
    }

    try:
        final_state = runner(
            initial_state,
            session=session,
            clock=clock,
            llm_provider=llm_provider,
            weather_provider=weather_provider,
        )
    except Exception as exc:
        logger.exception(
            "Stylist recommendation graph failed unexpectedly for user %s: %s",
            user_id,
            exc,
        )
        raise ProviderError()

    errors = final_state.get("errors", [])
    if errors:
        if EMPTY_WARDROBE_ERROR in errors:
            raise WardrobeEmptyError()
        if NO_COMPLETE_OUTFIT_ERROR in errors:
            raise NoCompleteOutfitError()
        logger.error(
            "Stylist recommendation completed with unmapped errors for user %s: %s",
            user_id,
            errors,
        )
        raise ProviderError()

    ctx = final_state.get("context")
    if ctx is None:
        logger.error("Stylist recommendation completed without context for user %s", user_id)
        raise ProviderError()

    mapped_ctx = _map_context(ctx)

    # Clarification path
    if ctx.needs_clarification:
        if not ctx.clarification_question or not ctx.clarification_question.strip():
            logger.error("Clarification requested but clarification_question is empty for user %s", user_id)
            raise ProviderError()
        return SuccessResponse(
            data=StylistChatResponseData(
                request_id=request_id,
                needs_clarification=True,
                clarification_question=ctx.clarification_question.strip(),
                context=mapped_ctx,
                recommendations=[],
                feedback_prompt_eligible=False,
                feedback_target_outfit_id=None,
                warnings=list(final_state.get("warnings", [])),
            )
        )

    # Success path validation
    grounding_validated = final_state.get("grounding_validated", False)
    rec_ids = final_state.get("recommendation_ids", [])
    ranked_outfits = final_state.get("ranked_outfits", [])

    if not grounding_validated or not rec_ids or not (1 <= len(ranked_outfits) <= 3):
        logger.error(
            "Stylist recommendation failed bounds/grounding checks: validated=%s, rec_ids=%s, ranked=%s",
            grounding_validated,
            rec_ids,
            len(ranked_outfits),
        )
        raise ProviderError()

    outfit_ids = [o.outfit_id for o in ranked_outfits if o.outfit_id]
    if len(outfit_ids) != len(ranked_outfits):
        logger.error("At least one ranked outfit is missing outfit_id")
        raise ProviderError()

    # Invariant: recommendation_ids and ranked outfits must match 1-to-1 with strictly unique IDs
    if len(set(rec_ids)) != len(rec_ids) or len(set(outfit_ids)) != len(outfit_ids) or set(rec_ids) != set(outfit_ids):
        logger.error(
            "Mismatched or duplicate recommendation IDs: rec_ids=%s, outfit_ids=%s",
            rec_ids,
            outfit_ids,
        )
        raise ProviderError()

    # Invariant: ranks must be strictly consecutive 1..n
    ranks = [o.rank for o in ranked_outfits]
    if ranks != list(range(1, len(ranked_outfits) + 1)):
        logger.error("Non-consecutive or invalid ranks detected: %s", ranks)
        raise ProviderError()

    # Invariant: composite_score must be a finite float within [0.0, 1.0]
    for o in ranked_outfits:
        score = getattr(o, "composite_score", None)
        if not isinstance(score, (int, float)) or not math.isfinite(score) or not (0.0 <= float(score) <= 1.0):
            logger.error(
                "Invalid composite score detected: %s for outfit %s",
                score,
                getattr(o, "outfit_id", None),
            )
            raise ProviderError()

    # Verify database persistence under user_id
    db_recs = session.exec(
        select(OutfitRecommendation).where(
            OutfitRecommendation.user_id == user_id,
            OutfitRecommendation.id.in_(rec_ids),
        )
    ).all()
    if len(db_recs) != len(rec_ids):
        logger.error(
            "Persisted recommendations mismatch for user %s: expected %s, found %s",
            user_id,
            len(rec_ids),
            len(db_recs),
        )
        raise ProviderError()

    db_items = session.exec(
        select(OutfitItem).where(
            OutfitItem.user_id == user_id,
            OutfitItem.outfit_id.in_(rec_ids),
        )
    ).all()

    # Map persisted items by outfit_id
    db_items_by_outfit: dict[str, set[tuple[str, Any]]] = {}
    for item in db_items:
        db_items_by_outfit.setdefault(item.outfit_id, set()).add(
            (item.wardrobe_item_id, item.slot_role)
        )

    # Query WardrobeItem scoped by user to verify items are active, not soft-deleted, and category matches slot
    all_wardrobe_item_ids = {item.item_id for o in ranked_outfits for item in o.items}
    db_wardrobe_items = session.exec(
        select(WardrobeItem).where(
            WardrobeItem.user_id == user_id,
            WardrobeItem.id.in_(all_wardrobe_item_ids),
            WardrobeItem.is_active.is_(True),
            WardrobeItem.deleted_at.is_(None),
        )
    ).all()
    if len(db_wardrobe_items) != len(all_wardrobe_item_ids):
        logger.error(
            "Wardrobe items active/deleted check failed for user %s: expected %s, found %s",
            user_id,
            len(all_wardrobe_item_ids),
            len(db_wardrobe_items),
        )
        raise ProviderError()

    wardrobe_item_map = {w.id: w for w in db_wardrobe_items}

    recommendations: list[StylistRecommendationResponse] = []
    for outfit in ranked_outfits:
        expected_slots = {(item.item_id, item.slot_role) for item in outfit.items}
        actual_slots = db_items_by_outfit.get(outfit.outfit_id, set())
        if expected_slots != actual_slots:
            logger.error(
                "Persisted outfit items mismatch for outfit %s: expected %s, found %s",
                outfit.outfit_id,
                expected_slots,
                actual_slots,
            )
            raise ProviderError()

        item_dtos: list[StylistRecommendationItemResponse] = []
        for item in outfit.items:
            w_item = wardrobe_item_map.get(item.item_id)
            if not w_item or w_item.category.value != item.slot_role.value:
                logger.error(
                    "Wardrobe item category/slot mismatch for item %s: expected %s, found %s",
                    item.item_id,
                    item.slot_role,
                    getattr(w_item, "category", None),
                )
                raise ProviderError()

            img_url = item.image_url
            if img_url is not None and not img_url.startswith("/api/v1/media/"):
                logger.error("Unsafe image_url on item %s: %s", item.item_id, img_url)
                raise ProviderError()

            item_dtos.append(
                StylistRecommendationItemResponse(
                    slot=item.slot_role,
                    item_id=item.item_id,
                    name=item.name,
                    image_url=img_url,
                )
            )

        recommendations.append(
            StylistRecommendationResponse(
                outfit_id=outfit.outfit_id,
                rank=outfit.rank,
                composite_score=outfit.composite_score,
                items=item_dtos,
                explanation_vi=outfit.explanation_vi,
                applied_preferences=list(outfit.applied_preferences or []),
            )
        )

    return SuccessResponse(
        data=StylistChatResponseData(
            request_id=request_id,
            needs_clarification=False,
            clarification_question=None,
            context=mapped_ctx,
            recommendations=recommendations,
            feedback_prompt_eligible=False,
            feedback_target_outfit_id=None,
            warnings=list(final_state.get("warnings", [])),
        )
    )
