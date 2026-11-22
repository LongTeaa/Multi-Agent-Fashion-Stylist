"""FLUX VTO try-on adapter served by fal.ai (`fal-ai/flux-pro/v1/vto`).

The model takes one person image, one garment reference image and a prompt, so
an outfit's garments are placed side by side, upper body on the left, in one
composite image and the whole outfit is rendered with a single call. When the
outfit also carries an inner top under outerwear, footwear or headwear (garments
with a `role`), they are laid out as a grid and named in one prompt following
Black Forest Labs' multi-garment guidance. The
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
    fallback = {"tops": "top", "bottoms": "bottom", "one-pieces": "dress", "footwear": "shoes", "headwear": "hat"}[
        garment.category
    ]
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


EXTENDED_ROLE_ORDER = ("outer", "upper", "one_piece", "lower", "footwear", "headwear")


def uses_extended_layout(garments: Sequence[OutfitGarment]) -> bool:
    """True when the outfit needs more than one upper or lower garment slot."""
    roles = {garment.role for garment in garments}
    return bool(roles & {"footwear", "headwear"}) or {"outer", "upper"} <= roles or {"outer", "one_piece"} <= roles


def order_extended(garments: Sequence[OutfitGarment]) -> list[OutfitGarment]:
    """One garment per role, in a fixed order: outer layer, inner layer, lower body, shoes, headwear."""
    by_role: dict[str, OutfitGarment] = {}
    for garment in garments:
        if garment.role is not None and garment.role not in by_role:
            by_role[garment.role] = garment
    if "one_piece" in by_role:
        by_role.pop("upper", None)
        by_role.pop("lower", None)
    return [by_role[role] for role in EXTENDED_ROLE_ORDER if role in by_role]


def build_garment_grid(images: Sequence[bytes], max_pixels: int = COMPOSITE_MAX_PIXELS) -> bytes:
    """Equal cells on a white canvas: one row for up to two items, 2x2 for 3-4, 3x2 for 5-6 (JPEG)."""
    if not images:
        raise ValueError("A composite needs at least one garment image.")
    if len(images) > 6:
        raise ValueError("At most six garments fit the grid.")
    columns = len(images) if len(images) <= 2 else (2 if len(images) <= 4 else 3)
    rows = math.ceil(len(images) / columns)
    cell = 512
    canvas = Image.new(
        "RGB",
        (columns * cell + (columns + 1) * COMPOSITE_PADDING, rows * cell + (rows + 1) * COMPOSITE_PADDING),
        (255, 255, 255),
    )
    for index, data in enumerate(images):
        with Image.open(BytesIO(data)) as source:
            image = _flatten_rgb(source)
        image.thumbnail((cell, cell), Image.Resampling.LANCZOS)
        column, row = index % columns, index // columns
        x = COMPOSITE_PADDING + column * (cell + COMPOSITE_PADDING) + (cell - image.width) // 2
        y = COMPOSITE_PADDING + row * (cell + COMPOSITE_PADDING) + (cell - image.height) // 2
        canvas.paste(image, (x, y))
    return _jpeg(_scale_to_pixels(canvas, max_pixels))


def build_extended_prompt(garments: Sequence[OutfitGarment]) -> str:
    """BFL formula: 'The person of image 1, maintaining exactly their face and pose, wearing ... of image 2.'"""
    ordered = order_extended(garments)
    if not ordered:
        raise ValueError("A try-on needs at least one garment.")
    by_role = {garment.role: garment for garment in ordered}
    parts: list[str] = []
    outer = by_role.get("outer")
    inner = by_role.get("upper") or by_role.get("one_piece")
    if outer is not None and inner is not None:
        parts.append(f"the {describe_garment(inner)} worn under the {describe_garment(outer)}")
    elif outer is not None or inner is not None:
        parts.append(f"the {describe_garment(outer or inner)}")  # type: ignore[arg-type]
    for role in ("lower", "footwear", "headwear"):
        if role in by_role:
            parts.append(f"the {describe_garment(by_role[role])}")
    wearing = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    keep = "" if "footwear" in by_role else " Keep the person's footwear unchanged."
    return (
        f"The person of image 1, maintaining exactly their face and pose, wearing {wearing} of image 2."
        f"{keep} Keep the background unchanged. A natural front-facing full-body studio photo."
    )


def _data_uri(image_bytes: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")


def _order_garments(garments: Sequence[OutfitGarment]) -> list[OutfitGarment]:
    """Upper body first, then lower body; a one-piece is rendered alone."""
    one_piece = [garment for garment in garments if garment.category == "one-pieces"]
    if one_piece:
        return one_piece[:1]
    body = [garment for garment in garments if garment.category in ("tops", "bottoms")]
    return sorted(body, key=lambda garment: 0 if garment.category == "tops" else 1)


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
        if uses_extended_layout(request.garments):
            garments = order_extended(request.garments)
            prompt = build_extended_prompt(garments)
            composite = build_garment_grid([g.image_bytes for g in garments])
        else:
            garments = _order_garments(request.garments)
            if not garments:
                raise ValueError("A try-on needs at least one garment.")
            prompt = build_prompt(garments)
            composite = build_garment_composite([g.image_bytes for g in garments])
        payload = {
            "prompt": prompt,
            "human_image_url": _data_uri(fit_person_image(request.person_image_bytes)),
            "garment_image_url": _data_uri(composite),
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
