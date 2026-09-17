from __future__ import annotations

from io import BytesIO
from typing import Literal

from PIL import Image

from app.schemas.common import ProviderError
from app.services.providers import ImageGenerationRequest, ImageGenerationResult

FakeImageScenario = Literal["success", "timeout", "provider_error"]


class FakeImageProvider:
    """Deterministic image provider for offline tests and local demonstrations."""

    provider_name = "fake"

    def __init__(
        self,
        *,
        model: str,
        scenario: FakeImageScenario = "success",
        supports_reference_images: bool = True,
    ) -> None:
        self.model = model
        self.scenario = scenario
        self._supports_reference_images = supports_reference_images
        self.last_request: ImageGenerationRequest | None = None

    @property
    def supports_reference_images(self) -> bool:
        return self._supports_reference_images

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        self.last_request = request
        if self.scenario == "timeout":
            raise TimeoutError("Image provider timed out.")
        if self.scenario == "provider_error":
            raise ProviderError("Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau.")

        buffer = BytesIO()
        Image.new("RGB", (768, 1024), "#eeeae2").save(buffer, format="WEBP")
        return ImageGenerationResult(
            image_bytes=buffer.getvalue(),
            mime_type="image/webp",
            provider=self.provider_name,
            model=self.model,
        )
