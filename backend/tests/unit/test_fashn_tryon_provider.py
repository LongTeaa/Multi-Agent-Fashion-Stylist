from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from gradio_client.exceptions import AppError
from PIL import Image

from app.schemas.common import ProviderError
from app.services.fashn_tryon_provider import FashnTryOnProvider
from app.services.providers import TryOnRequest


def _png_bytes(color: str = "white") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 12), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _request() -> TryOnRequest:
    return TryOnRequest(
        person_image_bytes=_png_bytes("white"),
        person_mime_type="image/png",
        garment_image_bytes=_png_bytes("blue"),
        garment_mime_type="image/png",
        category="tops",
    )


class _FakeJob:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.timeouts: list[float | None] = []
        self.cancelled = False

    def result(self, timeout: float | None = None) -> Any:
        self.timeouts.append(timeout)
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome

    def cancel(self) -> bool:
        self.cancelled = True
        return True


class _FakeClient:
    def __init__(self, job: _FakeJob) -> None:
        self.job = job
        self.submitted: list[dict[str, Any]] = []

    def submit(self, **kwargs: Any) -> _FakeJob:
        self.submitted.append(kwargs)
        return self.job


def _provider(job: _FakeJob, timeout_seconds: int = 7) -> tuple[FashnTryOnProvider, _FakeClient]:
    client = _FakeClient(job)
    provider = FashnTryOnProvider(timeout_seconds=timeout_seconds, client_factory=lambda: client)
    return provider, client


def test_waits_for_the_job_with_the_configured_timeout(tmp_path: Path) -> None:
    result_file = tmp_path / "result.png"
    result_file.write_bytes(_png_bytes("red"))
    job = _FakeJob(str(result_file))
    provider, client = _provider(job, timeout_seconds=7)

    result = provider.try_on(_request())

    assert job.timeouts == [7]
    assert client.submitted[0]["api_name"] == "/try_on"
    assert client.submitted[0]["category"] == "tops"
    assert result.mime_type == "image/webp"
    assert result.provider == "fashn"
    with Image.open(BytesIO(result.image_bytes)) as image:
        assert image.format == "WEBP"


def test_cancels_the_remote_job_and_raises_timeout_when_the_budget_expires() -> None:
    job = _FakeJob(TimeoutError())
    provider, _ = _provider(job, timeout_seconds=3)

    with pytest.raises(TimeoutError, match="3s"):
        provider.try_on(_request())

    assert job.cancelled is True


def test_maps_zero_gpu_quota_exhaustion_to_provider_error() -> None:
    job = _FakeJob(AppError("You have exceeded your ZeroGPU runs limit."))
    provider, _ = _provider(job)

    with pytest.raises(ProviderError):
        provider.try_on(_request())

    assert job.cancelled is False


def test_client_connection_failure_is_a_provider_error() -> None:
    def failing_factory() -> Any:
        raise ConnectionError("space unreachable")

    provider = FashnTryOnProvider(timeout_seconds=5, client_factory=failing_factory)

    with pytest.raises(ProviderError):
        provider.try_on(_request())


def test_rejects_a_non_positive_timeout() -> None:
    with pytest.raises(ValueError):
        FashnTryOnProvider(timeout_seconds=0)
