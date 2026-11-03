"""Durable request binding and atomic delivery/feedback response snapshots."""
from hashlib import sha256
import json

from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert
from sqlmodel import Session, select

from app.models.entities import RecommendationRequest, User, Rating, FeedbackSuppressedSession, utc_now
from app.schemas.common import AppException
from app.schemas.stylist import StylistChatRequest, StylistChatResponseData
from app.services.feedback_cadence_service import FeedbackCadenceService


def conflict() -> AppException:
    return AppException(status_code=409, code="IDEMPOTENCY_KEY_REUSED",
                        message="Mã yêu cầu đã dùng cho nội dung khác. Vui lòng gửi yêu cầu mới.")


def bind_request(session: Session, user_id: str, key: str, payload: StylistChatRequest) -> RecommendationRequest | None:
    if session.get(User, user_id) is None:
        return None
    fingerprint = sha256(json.dumps({"query": payload.query, "location": payload.location},
                                    sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    session.execute(insert(RecommendationRequest).values(user_id=user_id, request_id=key,
        fingerprint=fingerprint, created_at=utc_now()).on_conflict_do_nothing())
    session.commit()
    record = session.get(RecommendationRequest, (user_id, key))
    assert record is not None
    session.refresh(record)
    if record.fingerprint != fingerprint:
        raise conflict()
    return record


def deliver_response(session: Session, record: RecommendationRequest | None, response: StylistChatResponseData,
                     user_id: str, client_session_id: str | None,
                     feedback: FeedbackCadenceService) -> StylistChatResponseData:
    # Serialize delivery with retries. Snapshot writes share the feedback commit,
    # so a disconnected client cannot lose prompt metadata or advance cadence twice.
    session.execute(update(User).where(User.id == user_id).values(id=User.id))
    if record is not None:
        session.refresh(record)
        if record.response_data is not None:
            cached = StylistChatResponseData.model_validate(record.response_data)
            def membership(data: StylistChatResponseData) -> dict[str, set[tuple[str, str]]]:
                return {outfit.outfit_id: {(item.item_id, item.slot.value) for item in outfit.items}
                        for outfit in data.recommendations}
            if membership(cached) != membership(response):
                session.rollback()
                raise AppException(status_code=409, code="STALE_RECOMMENDATION",
                                   message="Gợi ý đã thay đổi. Vui lòng gửi yêu cầu mới.")
            target = cached.feedback_target_outfit_id
            rated = session.exec(select(Rating).where(Rating.user_id == user_id, Rating.outfit_id == target)).first() if target else None
            suppressed = session.exec(select(FeedbackSuppressedSession).where(
                FeedbackSuppressedSession.user_id == user_id,
                FeedbackSuppressedSession.client_session_id == client_session_id)).first() if client_session_id else None
            if rated or suppressed:
                cached = cached.model_copy(update={"feedback_prompt_eligible": False, "feedback_target_outfit_id": None})
            session.commit()
            return cached

    def retain(eligible: bool, target: str | None) -> None:
        response.feedback_prompt_eligible = eligible
        response.feedback_target_outfit_id = target
        if record is not None:
            record.response_data = response.model_dump(mode="json")
            session.add(record)

    feedback.process_chat_recommendations(session=session, user_id=user_id,
        new_outfit_ids=[outfit.outfit_id for outfit in response.recommendations],
        client_session_id=client_session_id, request_id=response.request_id, before_commit=retain)
    return response
