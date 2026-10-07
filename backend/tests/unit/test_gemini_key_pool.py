from __future__ import annotations

import concurrent.futures
import json
from unittest.mock import MagicMock
import httpx
import pytest
from pydantic import SecretStr

from app.schemas.common import ProviderError
from app.services.gemini_key_pool import GeminiKeyPool
from app.services.gemini_provider import GeminiDetector, GeminiVisionProvider


def test_key_pool_initialization_validation() -> None:
    # Rejects empty list
    with pytest.raises(ValueError, match="at least one non-empty API key"):
        GeminiKeyPool([])

    # Rejects only whitespace/empty keys
    with pytest.raises(ValueError, match="at least one non-empty API key"):
        GeminiKeyPool([SecretStr("   "), SecretStr("")])

    # Deduplicates identical keys
    pool = GeminiKeyPool([
        SecretStr("key-1"),
        SecretStr("key-2"),
        SecretStr("key-1"),
    ])
    assert pool.total_keys == 2
    assert [k.get_secret_value() for k in pool.keys] == ["key-1", "key-2"]


def test_key_pool_round_robin_rotation() -> None:
    k1, k2, k3 = SecretStr("key-1"), SecretStr("key-2"), SecretStr("key-3")
    pool = GeminiKeyPool([k1, k2, k3])

    observed = [pool.get_next_key().get_secret_value() for _ in range(6)]
    assert observed == ["key-1", "key-2", "key-3", "key-1", "key-2", "key-3"]


def test_key_pool_failover_and_cooldown_expiry() -> None:
    simulated_time = 1000.0

    def mock_clock() -> float:
        return simulated_time

    k1, k2, k3 = SecretStr("key-1"), SecretStr("key-2"), SecretStr("key-3")
    pool = GeminiKeyPool([k1, k2, k3], cooldown_seconds=60.0, clock=mock_clock)

    assert pool.get_next_key().get_secret_value() == "key-1"

    # Simulate key-1 receiving 429
    pool.mark_rate_limited(k1)
    assert pool.is_cooling(k1) is True
    assert pool.active_keys_count == 2
    assert pool.cooling_keys_count == 1

    # Next calls should cycle only between key-2 and key-3
    assert pool.get_next_key().get_secret_value() == "key-2"
    assert pool.get_next_key().get_secret_value() == "key-3"
    assert pool.get_next_key().get_secret_value() == "key-2"
    assert pool.get_next_key().get_secret_value() == "key-3"

    # Advance time past cooldown duration (60s)
    simulated_time += 61.0
    assert pool.is_cooling(k1) is False
    assert pool.active_keys_count == 3
    assert pool.cooling_keys_count == 0

    # Key-1 is back in the active rotation
    keys_observed = {pool.get_next_key().get_secret_value() for _ in range(3)}
    assert keys_observed == {"key-1", "key-2", "key-3"}


def test_key_pool_all_cooling_fallback() -> None:
    simulated_time = 1000.0

    def mock_clock() -> float:
        return simulated_time

    k1, k2 = SecretStr("key-1"), SecretStr("key-2")
    pool = GeminiKeyPool([k1, k2], cooldown_seconds=60.0, clock=mock_clock)

    # Put both keys into cooldown with different expiry
    pool.mark_rate_limited(k1, custom_cooldown=30.0)  # expires at 1030
    pool.mark_rate_limited(k2, custom_cooldown=60.0)  # expires at 1060

    assert pool.active_keys_count == 0
    assert pool.cooling_keys_count == 2

    # Should fallback to key-1 (earliest recovery at 1030) without crashing
    selected = pool.get_next_key()
    assert selected.get_secret_value() == "key-1"


def test_key_pool_thread_safety() -> None:
    keys = [SecretStr(f"key-{i}") for i in range(5)]
    pool = GeminiKeyPool(keys, cooldown_seconds=10.0)

    results: list[str] = []

    def worker() -> list[str]:
        return [pool.get_next_key().get_secret_value() for _ in range(50)]

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker) for _ in range(10)]
        for f in concurrent.futures.as_completed(futures):
            results.extend(f.result())

    assert len(results) == 500
    valid_key_names = {f"key-{i}" for i in range(5)}
    assert set(results) == valid_key_names


def test_detector_auto_failover_on_429() -> None:
    k1, k2 = SecretStr("primary-key"), SecretStr("backup-key")
    pool = GeminiKeyPool([k1, k2], cooldown_seconds=60.0)

    def mock_transport(request: httpx.Request) -> httpx.Response:
        key_header = request.headers.get("x-goog-api-key")
        if key_header == "primary-key":
            return httpx.Response(status_code=429, json={"error": "Rate limit exceeded"})
        if key_header == "backup-key":
            return httpx.Response(
                status_code=200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps({
                                            "input_kind": "single_item",
                                            "boxes": [
                                                {
                                                    "box": [0.1, 0.1, 0.9, 0.9],
                                                    "label": "top",
                                                    "confidence": 0.95,
                                                }
                                            ],
                                            "quality_warnings": [],
                                        })
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        return httpx.Response(status_code=500)

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    detector = GeminiDetector(
        key_pool=pool,
        model="gemini-1.5-flash",
        client=client,
        max_retries=2,
    )

    # Valid dummy image (JPEG header)
    dummy_image = b"\xff\xd8\xff\xe0" + b"\x00" * 32

    res = detector.detect(dummy_image)
    assert res.input_kind.value == "single_item"
    assert len(res.boxes) == 1
    # Key 1 was marked cooling
    assert pool.is_cooling(k1) is True
    assert pool.is_cooling(k2) is False


def test_vision_provider_auto_failover_on_429() -> None:
    k1, k2 = SecretStr("primary-key"), SecretStr("backup-key")
    pool = GeminiKeyPool([k1, k2], cooldown_seconds=60.0)

    def mock_transport(request: httpx.Request) -> httpx.Response:
        key_header = request.headers.get("x-goog-api-key")
        if key_header == "primary-key":
            return httpx.Response(status_code=429, json={"error": "Resource exhausted"})
        if key_header == "backup-key":
            return httpx.Response(
                status_code=200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps({
                                            "attributes": {
                                                "category": "top",
                                                "sub_category": "t-shirt",
                                                "primary_color": "white",
                                                "secondary_color": None,
                                                "pattern": "solid",
                                                "material": "cotton",
                                                "style": "casual",
                                                "fit": "regular",
                                                "formality_level": 2,
                                                "comfort_level": 4,
                                                "silhouette_level": 3,
                                                "length": "hip",
                                                "season": ["summer"],
                                                "weather_suitability": ["warm"],
                                                "functional_flags": ["movement"],
                                                "free_text_tags": ["cotton"],
                                            },
                                            "field_confidence": {
                                                "category": 0.95,
                                                "primary_color": 0.95,
                                            },
                                            "quality_warnings": [],
                                        })
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        return httpx.Response(status_code=500)

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    provider = GeminiVisionProvider(
        key_pool=pool,
        model="gemini-1.5-flash",
        client=client,
        max_retries=2,
    )

    dummy_crop = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    res = provider.extract_attributes(dummy_crop)

    assert res.attributes["category"] == "top"
    assert res.attributes["primary_color"] == "white"
    assert pool.is_cooling(k1) is True
    assert pool.is_cooling(k2) is False


def test_detector_failover_on_resource_exhausted_status_503() -> None:
    """Ensure failover is triggered even if Google returns HTTP 503 or 403 with RESOURCE_EXHAUSTED message."""
    k1, k2 = SecretStr("exhausted-key"), SecretStr("fresh-key")
    pool = GeminiKeyPool([k1, k2], cooldown_seconds=60.0)

    def mock_transport(request: httpx.Request) -> httpx.Response:
        key_header = request.headers.get("x-goog-api-key")
        if key_header == "exhausted-key":
            return httpx.Response(
                status_code=503,
                json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded for quota metric"}},
            )
        if key_header == "fresh-key":
            return httpx.Response(
                status_code=200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps({
                                            "input_kind": "single_item",
                                            "boxes": [],
                                            "quality_warnings": [],
                                        })
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        return httpx.Response(status_code=500)

    client = httpx.Client(transport=httpx.MockTransport(mock_transport))
    detector = GeminiDetector(
        key_pool=pool,
        model="gemini-1.5-flash",
        client=client,
        max_retries=2,
    )

    dummy_image = b"\xff\xd8\xff\xe0" + b"\x00" * 32
    res = detector.detect(dummy_image)
    assert res.input_kind.value == "single_item"
    assert pool.is_cooling(k1) is True
    assert pool.is_cooling(k2) is False


def test_settings_sync_when_only_gemini_api_keys_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEYS", "pool-key-1, pool-key-2")

    settings = Settings(_env_file=None)
    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "pool-key-1"
    assert len(settings.gemini_api_keys) == 2
    assert settings.get_primary_gemini_api_key() is not None
    assert settings.get_primary_gemini_api_key().get_secret_value() == "pool-key-1"

