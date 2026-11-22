"""FLUX VTO try-on adapter served by fal.ai (`fal-ai/flux-pro/v1/vto`).

The model takes one person image, one garment reference image and a prompt, so
an outfit's garments are placed side by side, upper body on the left, in one
composite image and the whole outfit is rendered with a single call. The
2026-11-20 provider spike (docs/archive/reports/TRYON_PROVIDER_SPIKE_2026-11-22.md)
selected this model over FASHN Try-On v1.6.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from io import BytesIO
import logging
import math

import httpx
from PIL import Image

from app.schemas.common import ProviderError
from app.services.providers import OutfitGarment, OutfitTryOnRequest, TryOnRequest, TryOnResult

logger = logging.getLogger(__name__)

FAL_BASE_URL = "https://fal.run"
FLUX_VTO_MODEL_ID = "fal-ai/flux-pro/v1/vto"
PERSON_MAX_PIXELS = 1_000_000  # the model page recommends under 1 MP for the person
COMPOSITE_MAX_PIXELS = 520_000  # and about 0.5 MP for the garment reference
COMPOSITE_PADDING = 24
_SERVICE_UNAVAILABLE = "Dịch vụ mặc thử tạm thời không khả dụng."


def _flatten_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return image.convert("RGB")


def _scale_to_pixels(image: Image.Image, max_pixels: int) -> Image.Image:
    width, height = image.size
    if width * height <= max_pixels:
        return image
    factor = math.sqrt(max_pixels / (width * height))
    size = (max(1, int(width * factor)), max(1, int(height * factor)))
    while size[0] * size[1] > max_pixels:
        size = (size[0] - 1, size[1] - 1)
    return image.resize(size, Image.Resampling.LANCZOS)


def _jpeg(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def fit_person_image(image_bytes: bytes, max_pixels: int = PERSON_MAX_PIXELS) -> bytes:
    """Flatten transparency onto white and downscale to at most `max_pixels` (JPEG)."""
    with Image.open(BytesIO(image_bytes)) as source:
        image = _flatten_rgb(source)
    return _jpeg(_scale_to_pixels(image, max_pixels))


def build_garment_composite(images: Sequence[bytes], max_pixels: int = COMPOSITE_MAX_PIXELS) -> bytes:
    """Place garment crops left to right on a white canvas at a common height (JPEG)."""
    if not images:
        raise ValueError("A composite needs at least one garment image.")
    flattened: list[Image.Image] = []
    for data in images:
        with Image.open(BytesIO(data)) as source:
            flattened.append(_flatten_rgb(source))
    height = max(image.height for image in flattened)
    scaled = [
        image
        if image.height == height
        else image.resize((max(1, round(image.width * height / image.height)), height), Image.Resampling.LANCZOS)
        for image in flattened
    ]
    width = sum(image.width for image in scaled) + COMPOSITE_PADDING * (len(scaled) + 1)
    canvas = Image.new("RGB", (width, height + 2 * COMPOSITE_PADDING), (255, 255, 255))
    x = COMPOSITE_PADDING
    for image in scaled:
        canvas.paste(image, (x, COMPOSITE_PADDING))
        x += image.width + COMPOSITE_PADDING
    return _jpeg(_scale_to_pixels(canvas, max_pixels))


def describe_garment(garment: OutfitGarment) -> str:
    """English description from recorded attributes only; unknown or plain values are omitted."""
    words: list[str] = []
    if garment.primary_color and garment.primary_color.lower() != "unknown":
        words.append(garment.primary_color.replace("_", " ").lower())
    if garment.pattern and garment.pattern.lower() not in {"solid", "unknown", "plain"}:
        words.append(garment.pattern.replace("_", " ").lower())
    fallback = {"tops": "top", "bottoms": "bottom", "one-pieces": "dress"}[garment.category]
    words.append((garment.sub_category or fallback).replace("_", " ").lower())
    return " ".join(words)


def build_prompt(garments: Sequence[OutfitGarment]) -> str:
    """Name each garment in the composite's left-to-right order; add nothing else."""
    if not garments:
        raise ValueError("A try-on needs at least one garment.")
    if len(garments) == 1:
        wear = f"Dress the person in the {describe_garment(garments[0])} shown in the reference image."
    else:
        upper, lower = garments[0], garments[1]
        wear = (
            "Dress the person in the garments shown in the reference image: "
            f"the {describe_garment(upper)} (left) on the upper body and "
            f"the {describe_garment(lower)} (right) on the lower body."
        )
    return (
        f"{wear} Keep the person's face, hair, pose, body shape, footwear and background unchanged. "
        "A natural front-facing full-body studio photo."
    )


def _data_uri(image_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")


def _order_garments(garments: Sequence[OutfitGarment]) -> list[OutfitGarment]:
    """Upper body first, then lower body; a one-piece is rendered alone."""
    one_piece = [garment for garment in garments if garment.category == "one-pieces"]
    if one_piece:
        return one_piece[:1]
    return sorted(garments, key=lambda garment: 0 if garment.category == "tops" else 1)


class FluxVtoTryOnProvider:
    """Try-on through fal.ai's synchronous `https://fal.run/<model>` endpoint."""

    provider_name = "flux_vto"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = FLUX_VTO_MODEL_ID,
        base_url: str = FAL_BASE_URL,
        timeout_seconds: float = 90.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("FAL_KEY is required for the FLUX VTO try-on provider.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        self.model = model
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx.Timeout(timeout_seconds)
        self._transport = transport

    def try_on_outfit(self, request: OutfitTryOnRequest) -> TryOnResult:
        garments = _order_garments(request.garments)
        if not garments:
            raise ValueError("A try-on needs at least one garment.")
        payload = {
            "prompt": build_prompt(garments),
            "human_image_url": _data_uri(fit_person_image(request.person_image_bytes)),
            "garment_image_url": _data_uri(build_garment_composite([g.image_bytes for g in garments])),
            "output_format": "jpeg",
        }
        image_bytes = self._render(payload)
        buffer = BytesIO()
        try:
            with Image.open(BytesIO(image_bytes)) as rendered:
                rendered.convert("RGB").save(buffer, format="WEBP", quality=90)
        except OSError as exc:
            logger.warning("FLUX VTO returned bytes that are not an image")
            raise ProviderError(_SERVICE_UNAVAILABLE) from exc
        return TryOnResult(
            image_bytes=buffer.getvalue(),
            mime_type="image/webp",
            provider=self.provider_name,
            model=self.model,
        )

    def try_on(self, request: TryOnRequest) -> TryOnResult:
        """Single-garment compatibility path for callers of `TryOnProviderProtocol`."""
        garment = OutfitGarment(
            image_bytes=request.garment_image_bytes,
            mime_type=request.garment_mime_type,
            category=request.category,
        )
        return self.try_on_outfit(
            OutfitTryOnRequest(
                person_image_bytes=request.person_image_bytes,
                person_mime_type=request.person_mime_type,
                garments=(garment,),
            )
        )

    def _render(self, payload: dict[str, str]) -> bytes:
        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
                headers={"Authorization": f"Key {self._api_key}"},
            ) as client:
                response = client.post(f"/{self.model}", json=payload)
            if response.status_code >= 400:
                logger.warning("FLUX VTO request failed with HTTP %s", response.status_code)
                raise ProviderError(_SERVICE_UNAVAILABLE)
            images = response.json().get("images")
            url = images[0]["url"] if isinstance(images, list) and images and isinstance(images[0], dict) else None
            if not url:
                logger.warning("FLUX VTO response contained no image")
                raise ProviderError(_SERVICE_UNAVAILABLE)
            if str(url).startswith("data:"):
                return base64.b64decode(str(url).split(",", 1)[1])
            # The result lives on a CDN: download it without the fal credentials.
            with httpx.Client(timeout=self._timeout, transport=self._transport) as cdn:
                image = cdn.get(str(url))
            image.raise_for_status()
            return image.content
        except httpx.TimeoutException as exc:
            raise TimeoutError("FLUX VTO timed out.") from exc
        except httpx.HTTPError as exc:
            logger.warning("FLUX VTO transport error: %s", type(exc).__name__)
            raise ProviderError(_SERVICE_UNAVAILABLE) from exc
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("FLUX VTO returned an unreadable response: %s", type(exc).__name__)
            raise ProviderError(_SERVICE_UNAVAILABLE) from exc
