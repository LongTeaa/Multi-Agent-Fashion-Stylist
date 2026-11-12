from __future__ import annotations

from io import BytesIO
from typing import Literal

from PIL import Image

from app.schemas.common import ProviderError
from app.services.providers import TryOnProviderProtocol, TryOnRequest, TryOnResult

FakeTryOnScenario = Literal["success", "timeout", "quota_exceeded", "provider_error"]


class FakeTryOnProvider:
    """Deterministic try-on provider for offline tests and local demonstrations."""

    provider_name = "fake"

    def __init__(
        self,
        *,
        model: str = "fake-vton-1.0",
        scenario: FakeTryOnScenario = "success",
    ) -> None:
        self.model = model
        self.scenario = scenario
        self.history: list[TryOnRequest] = []

    def try_on(self, request: TryOnRequest) -> TryOnResult:
        self.history.append(request)
        if self.scenario == "timeout":
            raise TimeoutError("Try-on provider timed out.")
        if self.scenario == "quota_exceeded":
            raise ProviderError("You have exceeded your ZeroGPU runs limit.")
        if self.scenario == "provider_error":
            raise ProviderError("Dịch vụ mặc thử AI tạm thời không khả dụng.")

        buffer = BytesIO()
        Image.new("RGB", (576, 864), "#d8e2dc").save(buffer, format="WEBP")
        return TryOnResult(
            image_bytes=buffer.getvalue(),
            mime_type="image/webp",
            provider=self.provider_name,
            model=self.model,
        )

