from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.dependencies import get_current_user_id, get_db_session
from app.schemas.common import SuccessResponse
from app.schemas.profile import (
    PreferenceOptionsResponseData,
    PreferenceSelections,
    ProfileResponseData,
)
from app.services.profile_service import get_profile, preference_options, replace_preferences

router = APIRouter(prefix="/user/profile", tags=["profile"])


@router.get("", response_model=SuccessResponse[ProfileResponseData])
def read_profile(
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[ProfileResponseData]:
    return SuccessResponse(data=get_profile(session, user_id))


@router.put("/preferences", response_model=SuccessResponse[ProfileResponseData])
def update_preferences(
    payload: PreferenceSelections,
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[ProfileResponseData]:
    return SuccessResponse(data=replace_preferences(session, user_id, payload))


@router.get(
    "/preference-options", response_model=SuccessResponse[PreferenceOptionsResponseData]
)
def read_preference_options(
    _: str = Depends(get_current_user_id),
) -> SuccessResponse[PreferenceOptionsResponseData]:
    return SuccessResponse(data=preference_options())
