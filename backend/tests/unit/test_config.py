from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

EXPECTED_ENV_KEYS = {
    "DATABASE_URL",
    "FRONTEND_URL",
    "LLM_MODEL",
    "VISION_MODEL",
    "IMAGE_MODEL",
    "GEMINI_API_KEY",
    "WEATHER_API_KEY",
    "OBJECT_STORAGE_BACKEND",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_SECURE",
    "MINIO_BUCKET_WARDROBE",
    "MINIO_BUCKET_THUMBNAILS",
    "MINIO_BUCKET_TRYON",
    "SIGNED_URL_TTL_SECONDS",
}


def test_defaults_match_environment_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)

    settings = Settings(_env_file=None)

    assert settings.database_url == "sqlite:///./data/fashion_stylist.db"
    assert str(settings.frontend_url) == "http://localhost:3000/"
    assert settings.object_storage_backend == "minio"
    assert str(settings.minio_endpoint) == "http://localhost:9000/"
    assert settings.minio_secure is False
    assert settings.minio_bucket_wardrobe == "wardrobe-private"
    assert settings.minio_bucket_thumbnails == "wardrobe-thumbnails"
    assert settings.minio_bucket_tryon == "tryon-private"
    assert settings.signed_url_ttl_seconds == 900


def test_environment_values_are_parsed_and_secrets_are_masked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("MINIO_SECURE", "true")
    monkeypatch.setenv("SIGNED_URL_TTL_SECONDS", "120")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-secret")

    settings = Settings(_env_file=None)

    assert settings.object_storage_backend == "local"
    assert settings.minio_secure is True
    assert settings.signed_url_ttl_seconds == 120
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "test-only-secret"
    assert "test-only-secret" not in repr(settings)

    with pytest.raises(ValidationError):
        settings.database_url = "sqlite:///./data/other.db"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("OBJECT_STORAGE_BACKEND", "public-cloud"),
        ("SIGNED_URL_TTL_SECONDS", "0"),
        ("FRONTEND_URL", "not-a-url"),
    ],
)
def test_invalid_environment_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_env_example_contains_the_complete_contract() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    lines = (repository_root / ".env.example").read_text(encoding="utf-8").splitlines()
    entries = dict(
        line.split("=", maxsplit=1)
        for line in lines
        if line and not line.startswith("#")
    )

    assert entries.keys() == EXPECTED_ENV_KEYS
    assert entries["GEMINI_API_KEY"] == "your_api_key"
    assert entries["WEATHER_API_KEY"] == "your_weather_api_key"
    assert entries["MINIO_ACCESS_KEY"] == "your_access_key"
    assert entries["MINIO_SECRET_KEY"] == "your_secret_key"
