from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.dependencies import (
    get_current_user_id,
    get_db_session,
    get_feedback_cadence_service,
    reconcile_client_session_id,
    validate_client_session_id_header,
)
from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.feedback import DismissPromptRequest, DismissPromptResponseData
from app.services.feedback_cadence_service import FeedbackCadenceService

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post(
    "/prompts/dismiss",
    response_model=SuccessResponse[DismissPromptResponseData],
    responses={
        422: {"model": ErrorResponse},
    },
)
def dismiss_feedback_prompt(
    payload: DismissPromptRequest | None = None,
    user_id: str = Depends(get_current_user_id),
    x_client_session_id: str | None = Depends(validate_client_session_id_header),
    session: Session = Depends(get_db_session),
    feedback_service: FeedbackCadenceService = Depends(get_feedback_cadence_service),
) -> SuccessResponse[DismissPromptResponseData]:
    """Dismiss proactive rating prompt and apply cooldown."""
    body_session = payload.client_session_id if payload else None
    client_session_id = reconcile_client_session_id(x_client_session_id, body_session)
    data = feedback_service.dismiss_prompt(
        session=session,
        user_id=user_id,
        client_session_id=client_session_id,
    )
    return SuccessResponse(data=data)

