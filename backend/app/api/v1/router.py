from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import ingestion, media, wardrobe

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(ingestion.router)
api_router.include_router(media.router)
api_router.include_router(wardrobe.router)
