from __future__ import annotations

from io import BytesIO
from time import sleep

import pytest
from PIL import Image

from app.models.entities import OutfitSlotRole
from app.schemas.common import TryOnFailedError
from app.services.image_generation import render_lookbook_with_fallback
from app.services.moodboard import MoodboardItem, render_moodboard
from app.services.providers import ImageGenerationRequest, ImageGenerationResult, ImageReference


def _image_bytes(mode: str, color: tuple[int, ...], image_format: str) -> bytes:
    buffer = BytesIO()
    Image.new(mode, (180, 240), color).save(buffer, format=image_format)
    return buffer.getvalue()


def _items() -> tuple[MoodboardItem, ...]:
    return (
        MoodboardItem(
            asset_id="asset-rgb-top",
            slot=OutfitSlotRole.TOP,
            name="Áo polo",
            color="Trắng",
            image_bytes=_image_bytes("RGB", (245, 245, 240), "JPEG"),
        ),
        MoodboardItem(
            asset_id="asset-rgba-bottom",
            slot=OutfitSlotRole.BOTTOM,
            name="Quần chinos",
            color="Xanh navy",
            image_bytes=_image_bytes("RGBA", (25, 35, 65, 170), "PNG"),
        ),
    )


def test_moodboard_supports_rgb_and_alpha_crops_without_transparency_requirement() -> None:
    result = render_moodboard(_items())

    assert result.mime_type == "image/webp"
    assert result.width == 768
    assert result.height == 1024
    assert result.included_asset_ids == ("asset-rgb-top", "asset-rgba-bottom")

    with Image.open(BytesIO(result.image_bytes)) as rendered:
        assert rendered.format == "WEBP"
        assert rendered.mode == "RGB"
        assert rendered.size == (768, 1024)


def test_moodboard_rejects_invalid_item_count_and_malformed_images() -> None:
    with pytest.raises(ValueError, match="2 to 5"):
        render_moodboard(_items()[:1])

    broken = MoodboardItem(
        asset_id="broken",
        slot=OutfitSlotRole.FOOTWEAR,
        name="Giày",
        color="Trắng",
        image_bytes=b"not-an-image",
    )
    with pytest.raises(ValueError, match="valid image"):
        render_moodboard((_items()[0], broken))


class _SlowProvider:
    provider_name = "slow"
    model = "slow-v1"
    supports_reference_images = True

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        del request
        sleep(0.05)
        return ImageGenerationResult(
            image_bytes=b"late",
            mime_type="image/webp",
            provider="slow",
            model="slow-v1",
        )


class _InvalidImageProvider:
    provider_name = "invalid"
    model = "invalid-v1"
    supports_reference_images = False

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        del request
        return ImageGenerationResult(
            image_bytes=b"not-an-image",
            mime_type="image/webp",
            provider=self.provider_name,
            model=self.model,
        )


def test_provider_timeout_returns_successful_moodboard_fallback() -> None:
    references = tuple(
        ImageReference(
            asset_id=item.asset_id,
            image_bytes=item.image_bytes,
            mime_type="image/png" if "rgba" in item.asset_id else "image/jpeg",
        )
        for item in _items()
    )

    result = render_lookbook_with_fallback(
        provider=_SlowProvider(),
        prompt="catalog prompt",
        reference_images=references,
        moodboard_items=_items(),
        timeout_seconds=0.001,
    )

    assert result.render_kind == "moodboard"
    assert result.fallback_used is True
    assert result.provider == "slow"
    assert result.model == "slow-v1"
    assert result.image_bytes


def test_disabled_provider_uses_fallback_and_both_failures_raise_504_error() -> None:
    fallback = render_lookbook_with_fallback(
        provider=None,
        prompt="catalog prompt",
        reference_images=(),
        moodboard_items=_items(),
        timeout_seconds=8,
    )
    assert fallback.render_kind == "moodboard"
    assert fallback.fallback_used is True
    assert fallback.provider is None
    assert fallback.model is None

    invalid_output_fallback = render_lookbook_with_fallback(
        provider=_InvalidImageProvider(),
        prompt="catalog prompt",
        reference_images=(),
        moodboard_items=_items(),
        timeout_seconds=8,
    )
    assert invalid_output_fallback.render_kind == "moodboard"
    assert invalid_output_fallback.fallback_used is True

    with pytest.raises(TryOnFailedError):
        render_lookbook_with_fallback(
            provider=None,
            prompt="catalog prompt",
            reference_images=(),
            moodboard_items=(),
            timeout_seconds=8,
        )
