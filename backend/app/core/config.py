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
