from __future__ import annotations

import tempfile
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image

from app.schemas.common import ProviderError
from app.services.providers import TryOnProviderProtocol, TryOnRequest, TryOnResult


class FashnTryOnProvider:
    """Virtual try-on provider adapter for fashn-ai/fashn-vton-1.5 Gradio space."""

    provider_name = "fashn"

    def __init__(
        self,
        *,
        space_name: str = "fashn-ai/fashn-vton-1.5",
        hf_token: str | None = None,
        timeout_seconds: int = 90,
    ) -> None:
        self.space_name = space_name
        self.model = space_name
        self.hf_token = hf_token
        self.timeout_seconds = timeout_seconds
        self._client = None

    def _get_client(self):
        if self._client is None:
            from gradio_client import Client
            token = self.hf_token.strip() if self.hf_token else None
            self._client = Client(self.space_name, token=token)
        return self._client

    def try_on(self, request: TryOnRequest) -> TryOnResult:
        from gradio_client import handle_file
        from gradio_client.exceptions import AppError

        client = self._get_client()

        # Write temporary input files
        ext_person = ".jpg" if request.person_mime_type == "image/jpeg" else ".png"
        ext_garment = ".jpg" if request.garment_mime_type == "image/jpeg" else ".png"

        with tempfile.NamedTemporaryFile(suffix=ext_person, delete=False) as f_person, \
             tempfile.NamedTemporaryFile(suffix=ext_garment, delete=False) as f_garment:
            f_person.write(request.person_image_bytes)
            f_person.flush()
            f_garment.write(request.garment_image_bytes)
            f_garment.flush()
            person_path = Path(f_person.name)
            garment_path = Path(f_garment.name)

        try:
            result = client.predict(
                person_image=handle_file(str(person_path)),
                garment_image=handle_file(str(garment_path)),
                category=request.category,
                garment_photo_type=request.garment_photo_type,
                num_timesteps=request.num_timesteps,
                guidance_scale=request.guidance_scale,
                seed=request.seed,
                segmentation_free=request.segmentation_free,
                api_name="/try_on",
            )
            result_path = Path(result)
            if not result_path.exists():
                raise ProviderError(f"Model result file not found: {result}")

            # Read and standardize output as WebP
            with Image.open(result_path) as img:
                out_buffer = BytesIO()
                img.save(out_buffer, format="WEBP")
                webp_bytes = out_buffer.getvalue()

            return TryOnResult(
                image_bytes=webp_bytes,
                mime_type="image/webp",
                provider=self.provider_name,
                model=self.model,
            )
        except AppError as e:
            err_msg = str(e)
            if "ZeroGPU runs limit" in err_msg:
                raise ProviderError("Hạn mức GPU Hugging Face đã hết trong ngày.") from e
            raise ProviderError(f"Lỗi dịch vụ FASHN VTON: {err_msg}") from e
        except TimeoutError as e:
            raise TimeoutError(f"FASHN VTON timed out after {self.timeout_seconds}s") from e
        except Exception as e:
            if isinstance(e, ProviderError):
                raise
            raise ProviderError(f"Virtual Try-On error: {e}") from e
        finally:
            # Clean up temp input files
            if person_path.exists():
                person_path.unlink(missing_ok=True)
            if garment_path.exists():
                garment_path.unlink(missing_ok=True)

