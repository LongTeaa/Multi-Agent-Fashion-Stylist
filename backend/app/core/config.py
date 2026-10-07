from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import AnyHttpUrl, Field, PositiveInt, SecretStr, field_validator, model_validator
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
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
        ]
    )
    cleanup_scheduler_enabled: bool = True
    cleanup_interval_seconds: PositiveInt = 3600

    vision_provider: Literal["fake", "gemini"] = "fake"
    vision_timeout_seconds: PositiveInt = 30
    context_provider: Literal["fallback", "fake", "gemini"] = "fallback"
    context_timeout_seconds: PositiveInt = 15
    weather_provider: Literal["disabled", "fake", "openweather"] = "disabled"
    weather_timeout_seconds: PositiveInt = 5
    image_provider: Literal["disabled", "fake", "gemini"] = "disabled"
    image_timeout_seconds: Literal[8] = 8
    llm_model: str | None = None
    vision_model: str | None = None
    detector_model: str | None = None
    image_model: str | None = None
    gemini_api_key: SecretStr | None = None
    gemini_api_keys: str | list[SecretStr] = Field(default_factory=list)
    gemini_key_cooldown_seconds: PositiveInt = 60
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

    @model_validator(mode="before")
    @classmethod
    def _sync_gemini_keys_dict(cls, data: Any) -> Any:
        if isinstance(data, dict):
            single = data.get("gemini_api_key")
            plural = data.get("gemini_api_keys")
            if not single and plural:
                if isinstance(plural, str):
                    first = [p.strip() for p in plural.split(",") if p.strip()]
                    if first:
                        data["gemini_api_key"] = first[0]
                elif isinstance(plural, (list, tuple)) and plural:
                    data["gemini_api_key"] = plural[0]
        return data

    @field_validator("gemini_api_keys", mode="before")
    @classmethod
    def _parse_gemini_api_keys(cls, value: object) -> list[SecretStr]:
        if value is None:
            return []
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed.startswith("[") and trimmed.endswith("]"):
                try:
                    import json
                    parsed = json.loads(trimmed)
                    if isinstance(parsed, list):
                        return [SecretStr(str(p).strip()) for p in parsed if str(p).strip()]
                except Exception:
                    pass
            parts = [part.strip() for part in trimmed.split(",") if part.strip()]
            return [SecretStr(p) for p in parts]
        if isinstance(value, (list, tuple)):
            result: list[SecretStr] = []
            for item in value:
                if isinstance(item, SecretStr):
                    if item.get_secret_value().strip():
                        result.append(item)
                elif isinstance(item, str) and item.strip():
                    result.append(SecretStr(item.strip()))
            return result
        return []

    def get_gemini_api_keys(self) -> list[SecretStr]:
        """Return non-empty Gemini API keys from gemini_api_keys or gemini_api_key fallback."""
        raw_keys = self.gemini_api_keys
        if isinstance(raw_keys, list):
            active_keys = [k for k in raw_keys if isinstance(k, SecretStr) and k.get_secret_value().strip()]
        else:
            active_keys = []
        if active_keys:
            return active_keys
        if self.gemini_api_key and self.gemini_api_key.get_secret_value().strip():
            return [self.gemini_api_key]
        return []

    def get_primary_gemini_api_key(self) -> SecretStr | None:
        """Return the primary Gemini API key (first available key)."""
        keys = self.get_gemini_api_keys()
        return keys[0] if keys else None

    def get_detector_model(self) -> str:
        """Return the model identifier for garment detection, falling back to vision_model."""
        if self.detector_model and self.detector_model.strip():
            return self.detector_model.strip()
        if self.vision_model and self.vision_model.strip():
            return self.vision_model.strip()
        return "gemini-1.5-flash"

    def get_vision_model(self) -> str:
        """Return the model identifier for fashion attribute extraction."""
        if self.vision_model and self.vision_model.strip():
            return self.vision_model.strip()
        return "gemini-1.5-flash"


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable view of application settings."""

    return Settings()


def validate_vision_provider_configuration(settings: Settings) -> None:
    """Fail application startup when the selected Vision provider is unusable."""
    if settings.vision_provider != "gemini":
        return
    if not settings.get_gemini_api_keys():
        raise ValueError("VISION_PROVIDER is set to 'gemini' but GEMINI_API_KEY is not configured.")
    if not settings.vision_model or not settings.vision_model.strip():
        raise ValueError("VISION_PROVIDER is set to 'gemini' but VISION_MODEL is not configured.")


def validate_context_provider_configuration(settings: Settings) -> None:
    """Fail fast when an explicitly selected context provider is unusable."""
    if settings.context_provider != "gemini":
        return
    if not settings.get_gemini_api_keys():
        raise ValueError("CONTEXT_PROVIDER is set to 'gemini' but GEMINI_API_KEY is not configured.")
    if not settings.llm_model or not settings.llm_model.strip():
        raise ValueError("CONTEXT_PROVIDER is set to 'gemini' but LLM_MODEL is not configured.")


def validate_weather_provider_configuration(settings: Settings) -> None:
    """Fail fast when an explicitly selected weather provider is unusable."""
    if settings.weather_provider != "openweather":
        return
    if not settings.weather_api_key or not settings.weather_api_key.get_secret_value().strip():
        raise ValueError("WEATHER_PROVIDER is set to 'openweather' but WEATHER_API_KEY is not configured.")


def validate_image_provider_configuration(settings: Settings) -> None:
    """Fail fast when an enabled image provider has no model identifier."""
    if settings.image_provider == "disabled":
        return
    if not settings.image_model or not settings.image_model.strip():
        raise ValueError("IMAGE_PROVIDER is enabled but IMAGE_MODEL is not configured.")
    if settings.image_provider == "gemini" and not settings.get_gemini_api_keys():
        raise ValueError("IMAGE_PROVIDER is set to 'gemini' but GEMINI_API_KEY is not configured.")
