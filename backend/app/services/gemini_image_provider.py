"""Gemini reference-conditioned lookbook generation adapter."""

from __future__ import annotations

import base64
import binascii
from typing import Any

import httpx
from pydantic import SecretStr

from app.services.providers import ImageGenerationRequest, ImageGenerationResult


class GeminiImageProvider:
    provider_name = "gemini"
    supports_reference_images = True

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float = 8.0,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._client = client

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        parts: list[dict[str, Any]] = [{"text": request.prompt}]
        parts.extend(
            {
                "inline_data": {
                    "mime_type": reference.mime_type,
                    "data": base64.b64encode(reference.image_bytes).decode("ascii"),
                }
            }
            for reference in request.reference_images
        )
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key.get_secret_value()}

        try:
            if self._client is not None:
                response = self._client.post(
                    url, headers=headers, json=payload, timeout=self.timeout_seconds
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            candidates = response.json()["candidates"]
            for candidate in candidates:
                for part in candidate.get("content", {}).get("parts", []):
                    if part.get("thought"):
                        continue
                    image = part.get("inlineData") or part.get("inline_data")
                    if not image:
                        continue
                    mime_type = image.get("mimeType") or image.get("mime_type")
                    if mime_type not in ("image/jpeg", "image/png", "image/webp"):
                        continue
                    image_bytes = base64.b64decode(image["data"], validate=True)
                    if image_bytes:
                        return ImageGenerationResult(
                            image_bytes=image_bytes,
                            mime_type=mime_type,
                            provider=self.provider_name,
                            model=self.model,
                        )
        except (httpx.HTTPError, ValueError, KeyError, TypeError, binascii.Error) as error:
            raise RuntimeError("Gemini image provider failed.") from error

        raise RuntimeError("Gemini image provider returned no image.")
