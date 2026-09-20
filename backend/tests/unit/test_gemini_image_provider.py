from __future__ import annotations

import base64
import json
from datetime import date
from io import BytesIO

import httpx
import pytest
from PIL import Image
from pydantic import SecretStr

from app.core.config import Settings, validate_image_provider_configuration
from app.core.dependencies import get_image_provider
from app.services.gemini_image_provider import GeminiImageProvider
from app.services.context_providers import GeminiContextProvider
from app.services.providers import ImageGenerationRequest, ImageReference


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 32), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_gemini_image_provider_sends_references_and_reads_image() -> None:
    image_bytes = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-key"
        assert "key=" not in str(request.url)
        payload = json.loads(request.content)
        parts = payload["contents"][0]["parts"]
        assert parts[0] == {"text": "Outfit lookbook"}
        assert parts[1]["inline_data"]["mime_type"] == "image/png"
        assert base64.b64decode(parts[1]["inline_data"]["data"]) == image_bytes
        assert payload["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Here is the lookbook"},
                                {
                                    "inlineData": {
                                        "mimeType": "image/png",
                                        "data": base64.b64encode(image_bytes).decode("ascii"),
                                    }
                                },
                            ]
                        }
                    }
                ]
            },
        )

    provider = GeminiImageProvider(
        api_key=SecretStr("test-key"),
        model="gemini-image-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(
        ImageGenerationRequest(
            prompt="Outfit lookbook",
            reference_images=(ImageReference("asset-1", image_bytes, "image/png"),),
        )
    )
    assert result.image_bytes == image_bytes
    assert result.mime_type == "image/png"
    assert result.provider == "gemini"
    assert result.model == "gemini-image-test"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"error": "quota"}),
        httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "no image"}]}}]}),
        httpx.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": "not base64"}}]}}]}),
    ],
)
def test_gemini_image_provider_rejects_unusable_response(response: httpx.Response) -> None:
    provider = GeminiImageProvider(
        api_key=SecretStr("test-key"),
        model="gemini-image-test",
        client=httpx.Client(transport=httpx.MockTransport(lambda _: response)),
    )
    with pytest.raises(RuntimeError):
        provider.generate(ImageGenerationRequest(prompt="Outfit lookbook"))


def test_gemini_image_provider_requires_key_and_is_selected() -> None:
    from unittest.mock import patch

    missing_key = Settings(
        _env_file=None, image_provider="gemini", image_model="gemini-image-test"
    )
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        validate_image_provider_configuration(missing_key)

    settings = Settings(
        _env_file=None,
        image_provider="gemini",
        image_model="gemini-image-test",
        gemini_api_key=SecretStr("test-key"),
    )
    with patch("app.core.dependencies.get_settings", return_value=settings):
        provider = get_image_provider()
    assert isinstance(provider, GeminiImageProvider)
    assert provider.model == "gemini-image-test"


def test_gemini_context_provider_sends_key_in_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-key"
        assert "key=" not in str(request.url)
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "{}"}]}}]},
        )

    provider = GeminiContextProvider(
        api_key=SecretStr("test-key"),
        model="gemini-context-test",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.extract_context(
        query="Đi làm", location=None, current_date=date(2026, 9, 20)
    ) == {}
