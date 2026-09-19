from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    feedback,
    ingestion,
    media,
    outfits,
    profile,
    stylist,
    system,
    tryons,
    wardrobe,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(ingestion.router)
api_router.include_router(media.router)
api_router.include_router(wardrobe.router)
api_router.include_router(profile.router)
api_router.include_router(stylist.router)
api_router.include_router(outfits.router)
api_router.include_router(feedback.router)
api_router.include_router(tryons.router)
api_router.include_router(system.router)

