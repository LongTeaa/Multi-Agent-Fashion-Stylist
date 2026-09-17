from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, UnidentifiedImageError

from app.schemas.common import TryOnFailedError
from app.services.moodboard import MoodboardItem, render_moodboard
from app.services.providers import (
    ImageGenerationRequest,
    ImageGenerationResult,
    ImageProviderProtocol,
    ImageReference,
)


@dataclass(frozen=True)
class LookbookRenderResult:
    image_bytes: bytes
    mime_type: str
    render_kind: Literal["generated_lookbook", "moodboard"]
    fallback_used: bool
    provider: str | None
    model: str | None


def _normalize_generated_webp(image_bytes: bytes) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            source.load()
            if source.width <= 0 or source.height <= 0:
                raise ValueError("Generated image has invalid dimensions.")
            normalized = source.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValueError("Image provider returned invalid image bytes.") from error

    buffer = BytesIO()
    normalized.save(buffer, format="WEBP", quality=90, method=6)
    return buffer.getvalue()


def generate_lookbook(
    *,
    provider: ImageProviderProtocol,
    prompt: str,
    reference_images: Iterable[ImageReference],
) -> ImageGenerationResult:
    """Generate a lookbook while respecting provider reference-image capability."""

    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise ValueError("The lookbook prompt must not be empty.")

    references = tuple(reference_images) if provider.supports_reference_images else ()
    return provider.generate(
        ImageGenerationRequest(
            prompt=normalized_prompt,
            reference_images=references,
        )
    )


def render_lookbook_with_fallback(
    *,
    provider: ImageProviderProtocol | None,
    prompt: str,
    reference_images: Iterable[ImageReference],
    moodboard_items: Iterable[MoodboardItem],
    timeout_seconds: float,
) -> LookbookRenderResult:
    """Generate within the provider budget, otherwise return a deterministic moodboard."""

    if timeout_seconds <= 0:
        raise ValueError("Image provider timeout must be positive.")

    provider_name = provider.provider_name if provider is not None else None
    model = provider.model if provider is not None else None
    provider_failed = provider is None

    if provider is not None:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image-provider")
        future = executor.submit(
            generate_lookbook,
            provider=provider,
            prompt=prompt,
            reference_images=tuple(reference_images),
        )
        try:
            generated = future.result(timeout=timeout_seconds)
            normalized_bytes = _normalize_generated_webp(generated.image_bytes)
        except Exception:
            provider_failed = True
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
        else:
            executor.shutdown(wait=True)
            return LookbookRenderResult(
                image_bytes=normalized_bytes,
                mime_type="image/webp",
                render_kind="generated_lookbook",
                fallback_used=False,
                provider=generated.provider,
                model=generated.model,
            )

    if provider_failed:
        try:
            fallback = render_moodboard(tuple(moodboard_items))
        except Exception as error:
            raise TryOnFailedError() from error
        return LookbookRenderResult(
            image_bytes=fallback.image_bytes,
            mime_type=fallback.mime_type,
            render_kind="moodboard",
            fallback_used=True,
            provider=provider_name,
            model=model,
        )

    raise TryOnFailedError()
