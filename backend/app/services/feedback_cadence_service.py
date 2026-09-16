from __future__ import annotations

import random
import time
from collections.abc import Callable
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from app.models.entities import (
    FeedbackDeliveredOutfit,
    FeedbackPromptState,
    FeedbackSuppressedSession,
    OutfitRecommendation,
    Rating,
)
from app.schemas.feedback import DismissPromptResponseData
from uuid import uuid4


class FeedbackCadenceService:
    """Service for managing proactive rating prompt cadence, cooldown, and lifecycle."""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        threshold_chooser: Callable[[], int] | None = None,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.threshold_chooser = threshold_chooser or (lambda: random.randint(5, 10))

    def _get_threshold(self) -> int:
        val = self.threshold_chooser()
        return max(5, min(10, int(val)))

    def process_chat_recommendations(
        self,
        session: Session,
        user_id: str,
        new_outfit_ids: list[str],
        client_session_id: str | None = None,
        request_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Evaluates feedback prompt eligibility for newly displayed outfits.

        - Deduplicates new_outfit_ids within the current response.
        - Filters out outfit IDs that were already delivered to this user (per FeedbackDeliveredOutfit).
        - If empty or no new distinct outfits and counter < threshold, returns (False, None).
        - Records new distinct outfits in FeedbackDeliveredOutfit.
        - Decrements cooldown_remaining if active.
        - If cooldown completed, increments eligible_count_since_prompt with remaining outfits.
        - If eligible_count_since_prompt >= next_threshold:
          - Checks if client_session_id is in feedback_suppressed_sessions. If so, suppressed (returns False, None).
          - Selects highest-ranked owned, persisted, unrated outfit.
          - If found: resets eligible_count_since_prompt to 0, sets last_prompted_at = clock(),
            reseeds next_threshold in [5, 10], commits, and returns (True, target_outfit_id).
          - If no valid unrated target exists: does not return fake eligibility, returns (False, None).
        """
        # 1. Explicit list deduplication
        seen: set[str] = set()
        deduped_ids = [oid for oid in new_outfit_ids if not (oid in seen or seen.add(oid))]
        if not deduped_ids:
            return False, None

        max_attempts = 5
        now = self.clock()

        for attempt in range(max_attempts):
            try:
                # 2. Retrieve or initialize FeedbackPromptState
                prompt_state = session.get(FeedbackPromptState, user_id)
                if prompt_state is None:
                    chosen_threshold = self._get_threshold()
                    prompt_state = FeedbackPromptState(
                        user_id=user_id,
                        eligible_count_since_prompt=0,
                        next_threshold=chosen_threshold,
                        cooldown_remaining=0,
                        last_prompted_at=None,
                        last_rated_at=None,
                    )
                    session.add(prompt_state)
                    session.flush()

                # 3. Filter out outfit IDs already delivered to this user previously
                existing_delivered = set(
                    session.exec(
                        select(FeedbackDeliveredOutfit.outfit_id).where(
                            FeedbackDeliveredOutfit.user_id == user_id,
                            FeedbackDeliveredOutfit.outfit_id.in_(deduped_ids),
                        )
                    ).all()
                )
                new_distinct_ids = [oid for oid in deduped_ids if oid not in existing_delivered]

                # 4. Record new distinct outfits in FeedbackDeliveredOutfit
                if new_distinct_ids:
                    persisted_outfit_ids = set(
                        session.exec(
                            select(OutfitRecommendation.id).where(
                                OutfitRecommendation.user_id == user_id,
                                OutfitRecommendation.id.in_(new_distinct_ids),
                            )
                        ).all()
                    )
                    for oid in new_distinct_ids:
                        if oid in persisted_outfit_ids:
                            session.add(
                                FeedbackDeliveredOutfit(
                                    user_id=user_id,
                                    outfit_id=oid,
                                    request_id=request_id or str(uuid4()),
                                    delivered_at=now,
                                )
                            )

                # 5. Handle cooldown deduction and cadence increment with new distinct outfits only
                num_new = len(new_distinct_ids)
                if num_new > 0:
                    if prompt_state.cooldown_remaining > 0:
                        consumed = min(prompt_state.cooldown_remaining, num_new)
                        prompt_state.cooldown_remaining -= consumed
                        remaining_outfits = num_new - consumed
                        if prompt_state.cooldown_remaining == 0 and remaining_outfits > 0:
                            prompt_state.eligible_count_since_prompt += remaining_outfits
                    else:
                        prompt_state.eligible_count_since_prompt += num_new

                session.add(prompt_state)

                # 6. Check if cooldown still active
                if prompt_state.cooldown_remaining > 0:
                    session.commit()
                    return False, None

                # 7. Check if threshold reached
                if prompt_state.eligible_count_since_prompt < prompt_state.next_threshold:
                    session.commit()
                    return False, None

                # 8. Threshold reached: check same-session suppression
                if client_session_id:
                    suppressed = session.exec(
                        select(FeedbackSuppressedSession).where(
                            FeedbackSuppressedSession.user_id == user_id,
                            FeedbackSuppressedSession.client_session_id == client_session_id,
                        )
                    ).first()
                    if suppressed is not None:
                        session.commit()
                        return False, None

                # 9. Select highest-ranked owned, persisted, unrated outfit
                target_outfit_id: str | None = None
                for oid in deduped_ids:
                    already_rated = session.exec(
                        select(Rating).where(
                            Rating.outfit_id == oid,
                            Rating.user_id == user_id,
                        )
                    ).first()
                    if already_rated is None:
                        outfit = session.exec(
                            select(OutfitRecommendation).where(
                                OutfitRecommendation.id == oid,
                                OutfitRecommendation.user_id == user_id,
                            )
                        ).first()
                        if outfit is not None:
                            target_outfit_id = oid
                            break

                # If all outfits in current response are already rated, check older unrated outfits
                if target_outfit_id is None:
                    unrated_subquery = select(Rating.outfit_id).where(Rating.user_id == user_id)
                    fallback_outfit = session.exec(
                        select(OutfitRecommendation.id)
                        .where(
                            OutfitRecommendation.user_id == user_id,
                            ~OutfitRecommendation.id.in_(unrated_subquery),
                        )
                        .order_by(
                            OutfitRecommendation.created_at.desc(),
                            OutfitRecommendation.rank.asc(),
                        )
                    ).first()
                    if fallback_outfit is not None:
                        target_outfit_id = fallback_outfit

                # If no unrated owned outfit exists, do not return fake eligibility
                if target_outfit_id is None:
                    session.commit()
                    return False, None

                # 10. Reset cadence upon triggering prompt
                prompt_state.eligible_count_since_prompt = 0
                prompt_state.last_prompted_at = now
                prompt_state.next_threshold = self._get_threshold()
                session.add(prompt_state)
                session.commit()

                return True, target_outfit_id

            except (IntegrityError, OperationalError):
                session.rollback()
                if attempt == max_attempts - 1:
                    raise
                time.sleep(0.01 * (attempt + 1))

        return False, None

    def dismiss_prompt(
        self,
        session: Session,
        user_id: str,
        client_session_id: str | None = None,
    ) -> DismissPromptResponseData:
        """Dismiss the current prompt and apply a cooldown of at least three outfits.

        A dismissal is intentionally different from a rating. It must not add the
        client session to ``feedback_suppressed_sessions`` because prompts may
        resume in the same session after the cooldown and normal cadence elapse.
        ``client_session_id`` remains accepted for API compatibility and request
        reconciliation at the endpoint boundary.
        """
        now = self.clock()
        max_attempts = 5

        for attempt in range(max_attempts):
            try:
                prompt_state = session.get(FeedbackPromptState, user_id)
                if prompt_state is None:
                    prompt_state = FeedbackPromptState(
                        user_id=user_id,
                        eligible_count_since_prompt=0,
                        next_threshold=self._get_threshold(),
                        cooldown_remaining=3,
                        last_prompted_at=now,
                    )
                    session.add(prompt_state)
                else:
                    prompt_state.cooldown_remaining = max(prompt_state.cooldown_remaining, 3)
                    prompt_state.eligible_count_since_prompt = 0
                    session.add(prompt_state)

                session.commit()
                return DismissPromptResponseData(
                    cooldown_remaining=prompt_state.cooldown_remaining,
                    dismissed=True,
                )

            except (IntegrityError, OperationalError):
                session.rollback()
                if attempt == max_attempts - 1:
                    raise
                time.sleep(0.01 * (attempt + 1))

        raise RuntimeError("Failed to dismiss feedback prompt after retries")
