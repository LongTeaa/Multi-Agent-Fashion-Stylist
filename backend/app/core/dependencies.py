from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Header
from sqlmodel import Session

from app.core.config import (
    REPOSITORY_ROOT,
    Settings,
    get_settings,
    validate_vision_provider_configuration,
)
from app.core.database import get_engine
from app.repositories.object_storage import (
    LocalObjectStorage,
    MinioObjectStorage,
    ObjectStorage,
    StorageBuckets,
)
from app.schemas.common import ValidationError
from app.services.providers import DetectorProtocol, VisionProviderProtocol


def get_db_session() -> Iterator[Session]:
    """Yield a database session within an automatic transaction boundary."""
    with Session(get_engine()) as session:
        yield session


@lru_cache
def get_object_storage() -> ObjectStorage:
    """Return the configured process-wide ObjectStorage adapter."""
    settings = get_settings()
    buckets = StorageBuckets.from_settings(settings)

    if settings.object_storage_backend == "local":
        storage_root = REPOSITORY_ROOT / "data" / "storage"
        return LocalObjectStorage(root=storage_root, buckets=buckets)

    return MinioObjectStorage.from_settings(settings)


def get_current_user_id(
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> str:
    """Extract and validate the authenticated user identity from the request header."""
    if not x_user_id or not x_user_id.strip():
        raise ValidationError(
            message="Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.",
            details={"field": "X-User-Id", "reason": "missing_or_empty"},
        )
    return x_user_id.strip()


def get_detector() -> DetectorProtocol:
    """Return the vision detector instance based on configured VISION_PROVIDER."""
    settings = get_settings()

    if settings.vision_provider == "fake":
        from app.services.fakes.vision_fakes import FakeDetector

        return FakeDetector(mode="multi_item")

    if settings.vision_provider == "gemini":
        validate_vision_provider_configuration(settings)

        from app.services.gemini_provider import GeminiDetector

        return GeminiDetector(
            api_key=settings.gemini_api_key,
            model=settings.vision_model,
            timeout_seconds=float(settings.vision_timeout_seconds),
        )

    raise ValueError(f"Unsupported vision_provider: '{settings.vision_provider}'")


def get_vision_provider() -> VisionProviderProtocol:
    """Return the vision attribute extraction provider instance based on configured VISION_PROVIDER."""
    settings = get_settings()

    if settings.vision_provider == "fake":
        from app.services.fakes.vision_fakes import FakeVisionProvider

        return FakeVisionProvider(scenario="golden_polo")

    if settings.vision_provider == "gemini":
        validate_vision_provider_configuration(settings)

        from app.services.gemini_provider import GeminiVisionProvider

        return GeminiVisionProvider(
            api_key=settings.gemini_api_key,
            model=settings.vision_model,
            timeout_seconds=float(settings.vision_timeout_seconds),
        )

    raise ValueError(f"Unsupported vision_provider: '{settings.vision_provider}'")


def get_utc_clock() -> Callable[[], datetime]:
    """Return a callable that produces the current timezone-aware UTC datetime."""
    return lambda: datetime.now(timezone.utc)


StylistRunner = Callable[..., Any]


def get_stylist_runner() -> StylistRunner:
    """Return the runner callable for stylist recommendations."""
    from app.agents.stylist_graph import execute_stylist_recommendation

    return execute_stylist_recommendation
