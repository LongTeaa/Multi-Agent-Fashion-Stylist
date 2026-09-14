from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlmodel import Session

from app.core.dependencies import (
    get_current_user_id,
    get_db_session,
    reconcile_client_session_id,
    validate_client_session_id_header,
)
from app.schemas.common import ErrorResponse, NotImplementedAppError, SuccessResponse
from app.schemas.outfits import (
    BookmarkOutfitRequest,
    BookmarkOutfitResponseData,
    OutfitDetailResponseData,
    OutfitRatingRequest,
    OutfitRatingResponseData,
    SavedOutfitsResponseData,
    WornOutfitRequest,
    WornOutfitResponseData,
)

router = APIRouter(prefix="/outfits", tags=["outfits"])


@router.get(
    "/saved",
    response_model=SuccessResponse[SavedOutfitsResponseData],
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def get_saved_outfits(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[SavedOutfitsResponseData]:
    """Retrieve paginated bookmarked outfits for the authenticated user."""
    raise NotImplementedAppError()


@router.get(
    "/{outfit_id}",
    response_model=SuccessResponse[OutfitDetailResponseData],
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def get_outfit_detail(
    outfit_id: str = Path(min_length=36, max_length=36),
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[OutfitDetailResponseData]:
    """Retrieve a single persisted outfit by ID for the authenticated user."""
    raise NotImplementedAppError()


@router.put(
    "/{outfit_id}/bookmark",
    response_model=SuccessResponse[BookmarkOutfitResponseData],
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def bookmark_outfit(
    payload: BookmarkOutfitRequest,
    outfit_id: str = Path(min_length=36, max_length=36),
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[BookmarkOutfitResponseData]:
    """Bookmark or unbookmark an outfit for the authenticated user."""
    raise NotImplementedAppError()


@router.post(
    "/{outfit_id}/worn",
    response_model=SuccessResponse[WornOutfitResponseData],
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def mark_outfit_worn(
    payload: WornOutfitRequest,
    outfit_id: str = Path(min_length=36, max_length=36),
    user_id: str = Depends(get_current_user_id),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[WornOutfitResponseData]:
    """Confirm that the authenticated user has worn the outfit, with idempotency key."""
    raise NotImplementedAppError()


@router.put(
    "/{outfit_id}/rating",
    response_model=SuccessResponse[OutfitRatingResponseData],
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        501: {"model": ErrorResponse},
    },
)
def rate_outfit(
    payload: OutfitRatingRequest,
    outfit_id: str = Path(min_length=36, max_length=36),
    user_id: str = Depends(get_current_user_id),
    x_client_session_id: str | None = Depends(validate_client_session_id_header),
    session: Session = Depends(get_db_session),
) -> SuccessResponse[OutfitRatingResponseData]:
    """Idempotently create or update a 1–5 rating for an outfit."""
    reconcile_client_session_id(x_client_session_id, payload.client_session_id)
    raise NotImplementedAppError()
