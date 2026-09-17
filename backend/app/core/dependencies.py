from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Header
from sqlmodel import Session

from app.core.config import (
    REPOSITORY_ROOT,
    Settings,
    get_settings,
    validate_context_provider_configuration,
    validate_image_provider_configuration,
    validate_vision_provider_configuration,
    validate_weather_provider_configuration,
)
from app.core.database import get_engine
from app.repositories.object_storage import (
    LocalObjectStorage,
    MinioObjectStorage,
    ObjectStorage,
    StorageBuckets,
)
from app.schemas.common import ValidationError
from app.services.providers import DetectorProtocol, ImageProviderProtocol, VisionProviderProtocol
from app.services.providers import ContextLLMProviderProtocol, WeatherProviderProtocol


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


def validate_client_session_id_header(
    x_client_session_id: Annotated[str | None, Header(alias="X-Client-Session-Id")] = None,
) -> str | None:
    """Extract and validate optional X-Client-Session-Id header as UUID v4."""
    if x_client_session_id is None:
        return None
    trimmed = x_client_session_id.strip()
    if not trimmed:
        return None
    try:
        parsed = uuid.UUID(trimmed)
        if parsed.version != 4:
            raise ValueError
    except Exception:
        raise ValidationError(
            message="Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.",
            details={"field": "X-Client-Session-Id", "reason": "must_be_valid_uuid_v4"},
        )
    return str(parsed)


def reconcile_client_session_id(
    header_session_id: str | None,
    body_session_id: str | None,
) -> str | None:
    """Reconcile session identifier between X-Client-Session-Id header and request body.

    Enforces contract invariant:
    - If both header and body session IDs are present, they MUST match.
    - Discrepancy raises HTTP 422 ValidationError.
    """
    if header_session_id and body_session_id:
        if header_session_id != body_session_id:
            raise ValidationError(
                message="Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.",
                details={
                    "field": "client_session_id",
                    "reason": "header_and_body_mismatch",
                    "header": header_session_id,
                    "body": body_session_id,
                },
            )
        return header_session_id
    return header_session_id or body_session_id



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


def get_context_llm_provider() -> ContextLLMProviderProtocol | None:
    """Return the configured context provider; offline MVP uses parser fallback."""
    settings = get_settings()
    if settings.context_provider == "fallback":
        return None
    if settings.context_provider == "fake":
        from app.services.fakes.context_fakes import FakeLLMProvider

        return FakeLLMProvider()
    validate_context_provider_configuration(settings)
    from app.services.context_providers import GeminiContextProvider

    return GeminiContextProvider(
        api_key=settings.gemini_api_key,
        model=settings.llm_model,
        timeout_seconds=float(settings.context_timeout_seconds),
    )


def get_weather_provider() -> WeatherProviderProtocol | None:
    """Return the configured weather provider; offline MVP keeps deterministic defaults."""
    settings = get_settings()
    if settings.weather_provider == "disabled":
        return None
    if settings.weather_provider == "fake":
        from app.services.fakes.context_fakes import FakeWeatherProvider

        return FakeWeatherProvider()
    validate_weather_provider_configuration(settings)
    from app.services.context_providers import OpenWeatherProvider

    return OpenWeatherProvider(
        api_key=settings.weather_api_key,
        timeout_seconds=float(settings.weather_timeout_seconds),
    )


def get_image_provider() -> ImageProviderProtocol | None:
    """Return the optional illustrative-lookbook image provider."""
    settings = get_settings()
    if settings.image_provider == "disabled":
        return None

    validate_image_provider_configuration(settings)
    if settings.image_provider == "fake":
        from app.services.fakes.image_fakes import FakeImageProvider

        return FakeImageProvider(model=settings.image_model or "")

    raise ValueError(f"Unsupported image_provider: '{settings.image_provider}'")


StylistRunner = Callable[..., Any]


def get_stylist_runner() -> StylistRunner:
    """Return the runner callable for stylist recommendations."""
    from app.agents.stylist_graph import execute_stylist_recommendation

    return execute_stylist_recommendation


def get_feedback_cadence_service(
    clock: Callable[[], datetime] = Depends(get_utc_clock),
) -> Any:
    """Return configured FeedbackCadenceService with injected UTC clock."""
    from app.services.feedback_cadence_service import FeedbackCadenceService

    return FeedbackCadenceService(clock=clock)
