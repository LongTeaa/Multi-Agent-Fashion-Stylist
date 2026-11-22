from __future__ import annotations

import base64
from io import BytesIO
import json

import httpx
from PIL import Image
import pytest

from app.schemas.common import ProviderError
from app.services.flux_vto_provider import (
    FLUX_VTO_MODEL_ID,
    FluxVtoTryOnProvider,
    build_prompt,
    describe_garment,
)
from app.services.providers import OutfitGarment, OutfitTryOnProviderProtocol, OutfitTryOnRequest, TryOnRequest

SECRET = "fal-unit-test-secret"
CDN = "https://cdn.example.test"


def _image(size: tuple[int, int], color: tuple[int, int, int], fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def _garment(category: str, color: tuple[int, int, int], **attrs: str) -> OutfitGarment:
    return OutfitGarment(image_bytes=_image((200, 300), color), mime_type="image/png", category=category, **attrs)  # type: ignore[arg-type]


def _decode(uri: str) -> Image.Image:
    assert uri.startswith("data:image/jpeg;base64,")
    return Image.open(BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGB")


class FakeFal:
    def __init__(self, response: httpx.Response | None = None, cdn_body: bytes | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.response = response
        self.cdn_body = cdn_body if cdn_body is not None else _image((736, 1024), (10, 200, 10), fmt="JPEG")

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "cdn.example.test":
            return httpx.Response(200, content=self.cdn_body)
        return self.response or httpx.Response(200, json={"images": [{"url": f"{CDN}/out.jpg"}], "seed": 1})

    def payload(self) -> dict[str, str]:
        (request,) = [r for r in self.requests if r.url.host == "fal.run"]
        return json.loads(request.content)


def _provider(fake: FakeFal) -> FluxVtoTryOnProvider:
    return FluxVtoTryOnProvider(api_key=SECRET, timeout_seconds=5, transport=httpx.MockTransport(fake))


def _request(*garments: OutfitGarment) -> OutfitTryOnRequest:
    return OutfitTryOnRequest(person_image_bytes=_image((896, 1200), (200, 200, 200)), person_mime_type="image/png",
                              garments=garments)


def test_outfit_is_one_call_with_upper_left_composite_and_attribute_prompt() -> None:
    fake = FakeFal()
    provider = _provider(fake)
    assert isinstance(provider, OutfitTryOnProviderProtocol)
    bottom = _garment("bottoms", (0, 0, 255), sub_category="chinos", primary_color="navy")
    top = _garment("tops", (255, 0, 0), sub_category="polo", primary_color="white", pattern="solid")

    result = provider.try_on_outfit(_request(bottom, top))  # given out of order on purpose

    model_calls = [r for r in fake.requests if r.url.host == "fal.run"]
    assert len(model_calls) == 1 and model_calls[0].url.path == f"/{FLUX_VTO_MODEL_ID}"
    payload = fake.payload()
    assert "the white polo (left) on the upper body" in payload["prompt"]
    assert "the navy chinos (right) on the lower body" in payload["prompt"]
    composite = _decode(payload["garment_image_url"])
    assert composite.width * composite.height <= 520_000
    left = composite.getpixel((composite.width // 4, composite.height // 2))
    right = composite.getpixel((composite.width * 3 // 4, composite.height // 2))
    assert left[0] > 200 and right[2] > 200  # red top on the left, blue bottom on the right
    person = _decode(payload["human_image_url"])
    assert person.width * person.height <= 1_000_000
    assert payload["output_format"] == "jpeg"

    assert result.mime_type == "image/webp" and result.provider == "flux_vto" and result.model == FLUX_VTO_MODEL_ID
    assert Image.open(BytesIO(result.image_bytes)).format == "WEBP"
    for request in fake.requests:  # the key goes to fal only, never to the image CDN
        assert ("authorization" in request.headers) == (request.url.host == "fal.run")


def test_one_piece_is_rendered_alone() -> None:
    fake = FakeFal()
    dress = _garment("one-pieces", (0, 120, 0), sub_category="midi_dress", primary_color="unknown")
    _provider(fake).try_on_outfit(_request(_garment("tops", (255, 0, 0)), dress))
    prompt = fake.payload()["prompt"]
    assert prompt.startswith("Dress the person in the midi dress shown in the reference image.")
    assert "(left)" not in prompt


def test_prompt_uses_recorded_attributes_only() -> None:
    plain = OutfitGarment(image_bytes=b"", mime_type="image/png", category="bottoms")
    assert describe_garment(plain) == "bottom"
    striped = OutfitGarment(image_bytes=b"", mime_type="image/png", category="tops", sub_category="button_down_shirt",
                            primary_color="light_blue", pattern="striped")
    assert describe_garment(striped) == "light blue striped button down shirt"
    with pytest.raises(ValueError):
        build_prompt([])


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, text=f"rate limited for key {SECRET}"),
        httpx.Response(500, text="internal"),
        httpx.Response(200, json={"images": []}),
        httpx.Response(200, text="not json"),
    ],
)
def test_provider_failures_raise_a_generic_provider_error(response: httpx.Response) -> None:
    with pytest.raises(ProviderError) as raised:
        _provider(FakeFal(response=response)).try_on_outfit(_request(_garment("tops", (255, 0, 0))))
    assert SECRET not in str(raised.value) and "internal" not in str(raised.value)


def test_non_image_result_is_a_provider_error() -> None:
    with pytest.raises(ProviderError):
        _provider(FakeFal(cdn_body=b"<html>gone</html>")).try_on_outfit(_request(_garment("tops", (255, 0, 0))))


def test_timeout_is_reported_as_timeout_error() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    provider = FluxVtoTryOnProvider(api_key=SECRET, timeout_seconds=5, transport=httpx.MockTransport(slow))
    with pytest.raises(TimeoutError):
        provider.try_on_outfit(_request(_garment("tops", (255, 0, 0))))


def test_single_garment_protocol_path_and_key_validation() -> None:
    fake = FakeFal()
    result = _provider(fake).try_on(
        TryOnRequest(person_image_bytes=_image((80, 120), (1, 1, 1)), person_mime_type="image/png",
                     garment_image_bytes=_image((60, 60), (255, 0, 0)), garment_mime_type="image/png", category="bottoms")
    )
    assert result.mime_type == "image/webp"
    assert "the bottom shown in the reference image" in fake.payload()["prompt"]
    for bad in ("", "   "):
        with pytest.raises(ValueError):
            FluxVtoTryOnProvider(api_key=bad)


def test_dependency_requires_fal_key_for_flux(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.core.dependencies import get_tryon_provider

    monkeypatch.setenv("TRYON_PROVIDER", "flux")
    monkeypatch.setenv("FAL_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="FAL_KEY"):
            get_tryon_provider()
        monkeypatch.setenv("FAL_KEY", SECRET)
        get_settings.cache_clear()
        provider = get_tryon_provider()
        assert isinstance(provider, FluxVtoTryOnProvider) and provider.model == FLUX_VTO_MODEL_ID
    finally:
        get_settings.cache_clear()
