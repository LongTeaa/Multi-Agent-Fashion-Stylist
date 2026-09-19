from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from io import BytesIO
from PIL import Image

from app.models.entities import OutfitSlotRole
from app.services.image_generation import (
    _LOOKBOOK_EXECUTOR,
    get_image_circuit_breaker,
    render_lookbook_with_fallback,
    reset_image_circuit_breaker,
)
from app.services.moodboard import MoodboardItem
from app.services.providers import ImageGenerationRequest, ImageGenerationResult, ImageProviderProtocol


def _dummy_moodboard_items() -> tuple[MoodboardItem, ...]:
    buf1, buf2 = BytesIO(), BytesIO()
    Image.new("RGB", (100, 100), (200, 200, 200)).save(buf1, format="JPEG")
    Image.new("RGB", (100, 100), (50, 50, 50)).save(buf2, format="JPEG")
    return (
        MoodboardItem(
            asset_id="asset-1",
            slot=OutfitSlotRole.TOP,
            name="Top",
            color="White",
            image_bytes=buf1.getvalue(),
        ),
        MoodboardItem(
            asset_id="asset-2",
            slot=OutfitSlotRole.BOTTOM,
            name="Bottom",
            color="Black",
            image_bytes=buf2.getvalue(),
        ),
    )


class HangingImageProvider:
    """Mock provider that simulates hanging or slow network I/O."""

    provider_name = "hanging-provider"
    model = "mock-hang-v1"
    supports_reference_images = False

    def __init__(self, hang_seconds: float = 0.5):
        self.hang_seconds = hang_seconds
        self.calls = 0

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.calls += 1
        time.sleep(self.hang_seconds)
        return ImageGenerationResult(
            image_bytes=b"dummy",
            mime_type="image/webp",
            provider=self.provider_name,
            model=self.model,
        )


@pytest.fixture(autouse=True)
def clean_circuit_breaker():
    reset_image_circuit_breaker()
    yield
    reset_image_circuit_breaker()


def test_hanging_provider_trips_circuit_breaker_and_bypasses_hanging_calls():
    """Verify that repeated timeouts trip the circuit breaker and immediately fallback to moodboard."""
    provider = HangingImageProvider(hang_seconds=0.2)
    cb = get_image_circuit_breaker()
    cb.cooldown_seconds = 1.0  # cooldown longer than render_moodboard duration
    cb.failure_threshold = 2
    items = _dummy_moodboard_items()

    # 1. First failure (timeout)
    res1 = render_lookbook_with_fallback(
        provider=provider,
        prompt="A fashionable outfit",
        reference_images=(),
        moodboard_items=items,
        timeout_seconds=0.03,
    )
    assert res1.fallback_used is True
    assert res1.render_kind == "moodboard"
    assert cb.failure_count == 1
    assert cb.state == "CLOSED"

    # 2. Second failure -> trips circuit to OPEN
    res2 = render_lookbook_with_fallback(
        provider=provider,
        prompt="A fashionable outfit",
        reference_images=(),
        moodboard_items=items,
        timeout_seconds=0.03,
    )
    assert res2.fallback_used is True
    assert cb.failure_count == 2
    assert cb.state == "OPEN"

    # 3. Third call: circuit breaker is OPEN, provider is bypassed immediately
    calls_before = provider.calls
    start_t = time.monotonic()
    res3 = render_lookbook_with_fallback(
        provider=provider,
        prompt="A fashionable outfit",
        reference_images=(),
        moodboard_items=items,
        timeout_seconds=0.03,
    )
    duration = time.monotonic() - start_t
    assert res3.fallback_used is True
    assert provider.calls == calls_before  # Not called!
    assert duration < 0.18  # Bypassed provider wait!

    # 4. After cooldown: transitions to HALF_OPEN
    time.sleep(1.05)
    assert cb.is_available() is True
    assert cb.state == "HALF_OPEN"


def test_lookbook_executor_is_bounded():
    """Verify the process-wide lookbook executor is bounded to max 4 workers."""
    assert _LOOKBOOK_EXECUTOR._max_workers == 4
