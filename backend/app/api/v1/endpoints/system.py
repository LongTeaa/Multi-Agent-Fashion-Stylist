from __future__ import annotations

from fastapi import APIRouter

from app.services.cleanup_scheduler import get_cleanup_metrics

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/cleanup-metrics")
def read_cleanup_metrics() -> dict:
    """Return operational metrics for transient 24-hour media cleanup."""
    metrics = get_cleanup_metrics()
    return {
        "success": True,
        "data": metrics.to_dict(),
    }
