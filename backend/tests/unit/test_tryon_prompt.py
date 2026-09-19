from __future__ import annotations

from dataclasses import replace

import pytest

from app.models.entities import OutfitSlotRole
from app.schemas.common import ProviderError
from app.services.fakes.image_fakes import FakeImageProvider
from app.services.image_generation import generate_lookbook
from app.services.providers import ImageProviderProtocol, ImageReference
from app.services.tryon_prompt import LookbookPromptItem, build_lookbook_prompt


def _item(
    slot: OutfitSlotRole,
    *,
    sub_category: str,
    primary_color: str,
) -> LookbookPromptItem:
    return LookbookPromptItem(
        slot=slot,
        sub_category=sub_category,
        primary_color=primary_color,
        secondary_color=None,
        pattern="solid",
        material="cotton",
        style="smart_casual",
        fit="regular",
    )


def test_prompt_describes_only_supplied_outfit_items_and_omits_null_defaults() -> None:
    top = _item(OutfitSlotRole.TOP, sub_category="polo", primary_color="white")
    bottom = replace(
        _item(OutfitSlotRole.BOTTOM, sub_category="chinos", primary_color="navy"),
        material="unknown",
        fit="không xác định",
    )

    prompt = build_lookbook_prompt([bottom, top])

    assert "standard adult mannequin" in prompt
    assert "full-length catalog composition" in prompt
    assert "neutral background" in prompt
    assert "top: polo; primary color: white" in prompt
    assert "bottom: chinos; primary color: navy" in prompt
    assert prompt.index("top: polo") < prompt.index("bottom: chinos")
    assert "unknown" not in prompt
    assert "không xác định" not in prompt
    assert "Do not infer or add brand names" in prompt
    assert "gucci" not in prompt.lower()
    assert "accessory:" not in prompt
    assert "8K" not in prompt


@pytest.mark.parametrize(
    "items",
    [
        [_item(OutfitSlotRole.TOP, sub_category="polo", primary_color="white")],
        [
            _item(OutfitSlotRole.TOP, sub_category="polo", primary_color="white"),
            _item(OutfitSlotRole.BOTTOM, sub_category="chinos", primary_color="navy"),
            _item(OutfitSlotRole.FOOTWEAR, sub_category="sneakers", primary_color="white"),
            _item(OutfitSlotRole.OUTERWEAR, sub_category="jacket", primary_color="black"),
            _item(OutfitSlotRole.ACCESSORY, sub_category="belt", primary_color="brown"),
            _item(OutfitSlotRole.DRESS, sub_category="dress", primary_color="red"),
        ],
    ],
)
def test_prompt_requires_two_to_five_items(items: list[LookbookPromptItem]) -> None:
    with pytest.raises(ValueError, match="2 to 5"):
        build_lookbook_prompt(items)


def test_prompt_supports_five_items() -> None:
    items = [
        _item(OutfitSlotRole.TOP, sub_category="polo", primary_color="white"),
        _item(OutfitSlotRole.BOTTOM, sub_category="chinos", primary_color="navy"),
        _item(OutfitSlotRole.FOOTWEAR, sub_category="sneakers", primary_color="white"),
        _item(OutfitSlotRole.OUTERWEAR, sub_category="jacket", primary_color="black"),
        _item(OutfitSlotRole.ACCESSORY, sub_category="belt", primary_color="brown"),
    ]
    prompt = build_lookbook_prompt(items)
    assert "polo" in prompt
    assert "chinos" in prompt
    assert "sneakers" in prompt
    assert "jacket" in prompt
    assert "belt" in prompt


def test_reference_images_are_supplied_only_when_provider_supports_them() -> None:
    references = (
        ImageReference(asset_id="asset-top", image_bytes=b"top", mime_type="image/png"),
        ImageReference(asset_id="asset-bottom", image_bytes=b"bottom", mime_type="image/jpeg"),
    )
    supporting_provider = FakeImageProvider(
        model="fake-lookbook-v2",
        supports_reference_images=True,
    )
    assert isinstance(supporting_provider, ImageProviderProtocol)

    result = generate_lookbook(
        provider=supporting_provider,
        prompt="catalog prompt",
        reference_images=references,
    )

    assert result.image_bytes
    assert result.model == "fake-lookbook-v2"
    assert supporting_provider.last_request is not None
    assert supporting_provider.last_request.reference_images == references

    text_only_provider = FakeImageProvider(
        model="fake-text-only",
        supports_reference_images=False,
    )
    generate_lookbook(
        provider=text_only_provider,
        prompt="catalog prompt",
        reference_images=references,
    )

    assert text_only_provider.last_request is not None
    assert text_only_provider.last_request.reference_images == ()


@pytest.mark.parametrize("scenario", ["timeout", "provider_error"])
def test_fake_image_provider_has_deterministic_failure_modes(scenario: str) -> None:
    provider = FakeImageProvider(model="fake-lookbook-v1", scenario=scenario)

    expected_error = TimeoutError if scenario == "timeout" else ProviderError
    with pytest.raises(expected_error):
        generate_lookbook(
            provider=provider,
            prompt="catalog prompt",
            reference_images=(),
        )
