from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    database_url: str = "sqlite:///./data/fashion_stylist.db"
    frontend_url: AnyHttpUrl = AnyHttpUrl("http://localhost:3000")

    vision_provider: Literal["fake", "gemini"] = "fake"
    vision_timeout_seconds: PositiveInt = 30
    context_provider: Literal["fallback", "fake", "gemini"] = "fallback"
    context_timeout_seconds: PositiveInt = 15
    weather_provider: Literal["disabled", "fake", "openweather"] = "disabled"
    weather_timeout_seconds: PositiveInt = 5
    llm_model: str | None = None
    vision_model: str | None = None
    image_model: str | None = None
    gemini_api_key: SecretStr | None = None
    weather_api_key: SecretStr | None = None

    object_storage_backend: Literal["minio", "local"] = "minio"
    minio_endpoint: AnyHttpUrl = AnyHttpUrl("http://localhost:9000")
    minio_access_key: SecretStr | None = None
    minio_secret_key: SecretStr | None = None
    minio_secure: bool = False
    minio_bucket_wardrobe: str = "wardrobe-private"
    minio_bucket_thumbnails: str = "wardrobe-thumbnails"
    minio_bucket_tryon: str = "tryon-private"
    signed_url_ttl_seconds: PositiveInt = 900


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable view of application settings."""

    return Settings()


def validate_vision_provider_configuration(settings: Settings) -> None:
    """Fail application startup when the selected Vision provider is unusable."""
    if settings.vision_provider != "gemini":
        return
    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value().strip():
        raise ValueError("VISION_PROVIDER is set to 'gemini' but GEMINI_API_KEY is not configured.")
    if not settings.vision_model or not settings.vision_model.strip():
        raise ValueError("VISION_PROVIDER is set to 'gemini' but VISION_MODEL is not configured.")


def validate_context_provider_configuration(settings: Settings) -> None:
    """Fail fast when an explicitly selected context provider is unusable."""
    if settings.context_provider != "gemini":
        return
    if not settings.gemini_api_key or not settings.gemini_api_key.get_secret_value().strip():
        raise ValueError("CONTEXT_PROVIDER is set to 'gemini' but GEMINI_API_KEY is not configured.")
    if not settings.llm_model or not settings.llm_model.strip():
        raise ValueError("CONTEXT_PROVIDER is set to 'gemini' but LLM_MODEL is not configured.")


def validate_weather_provider_configuration(settings: Settings) -> None:
    """Fail fast when an explicitly selected weather provider is unusable."""
    if settings.weather_provider != "openweather":
        return
    if not settings.weather_api_key or not settings.weather_api_key.get_secret_value().strip():
        raise ValueError("WEATHER_PROVIDER is set to 'openweather' but WEATHER_API_KEY is not configured.")
