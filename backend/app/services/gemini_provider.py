from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

from app.models.entities import BoundingBox, ConfidenceValue, InputKind
from app.schemas.common import ProviderError
from app.services.providers import (
    BoundingBoxDetection,
    DetectionResult,
    VisionExtractionResult,
)

logger = logging.getLogger(__name__)


def _detect_image_mime_type(image_bytes: bytes) -> str:
    """Return the MIME type encoded by supported image bytes."""
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if (
        len(image_bytes) >= 12
        and image_bytes.startswith(b"RIFF")
        and image_bytes[8:12] == b"WEBP"
    ):
        return "image/webp"
    raise ProviderError("Dữ liệu ảnh gửi đến dịch vụ AI không hợp lệ.")


class GeminiBoxDetection(BaseModel):
    """Pydantic model for validating Gemini bounding box detection output."""

    box: tuple[float, float, float, float]
    label: str
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


class GeminiDetectorOutput(BaseModel):
    """Pydantic model for validating Gemini clothing detector structured JSON."""

    input_kind: InputKind
    boxes: list[GeminiBoxDetection] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)


class GeminiVisionOutput(BaseModel):
    """Pydantic model for validating Gemini fashion attribute extraction structured JSON."""

    attributes: dict[str, Any]
    field_confidence: dict[str, float] = Field(default_factory=dict)
    quality_warnings: list[str] = Field(default_factory=list)


def _extract_json_from_gemini_response(response_payload: dict[str, Any]) -> str:
    """Extract raw JSON text from a Gemini generateContent response structure."""
    candidates = response_payload.get("candidates")
    if not candidates or not isinstance(candidates, list):
        raise ProviderError("Dịch vụ AI trả về phản hồi không có nội dung kết quả.")

    first_candidate = candidates[0]
    content = first_candidate.get("content", {})
    parts = content.get("parts", [])
    if not parts or not isinstance(parts, list):
        raise ProviderError("Dịch vụ AI trả về phần nội dung rỗng.")

    text = parts[0].get("text", "").strip()
    # Strip markdown code fencing if model wrapped it in ```json ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class GeminiDetector:
    """Production adapter invoking Google Gemini multimodal API for garment detection."""

    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float = 30.0,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._client = client

    def detect(self, image_bytes: bytes) -> DetectionResult:
        """Call Gemini to detect clothing items and determine scene classification."""
        url = f"{self.base_url}/models/{self.model}:generateContent"
        params = {"key": self.api_key.get_secret_value()}
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        image_mime_type = _detect_image_mime_type(image_bytes)

        prompt = (
            "Analyze this fashion image. Detect clothing/garment items with bounding boxes in normalized "
            "[x_min, y_min, x_max, y_max] format in [0.0, 1.0]. "
            "Determine the scene input_kind: 'single_item', 'multi_item', 'worn_outfit', 'cluttered', or 'unknown'. "
            "Return a JSON object with keys: 'input_kind', 'boxes' (list of {box, label, confidence}), and 'quality_warnings'."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": image_mime_type,
                                "data": encoded_image,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
            },
        }

        try:
            if self._client is not None:
                resp = self._client.post(
                    url, params=params, json=payload, timeout=self.timeout_seconds
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(url, params=params, json=payload)

            if resp.status_code >= 400:
                logger.error("Gemini detector HTTP error %d: %s", resp.status_code, resp.text)
                raise ProviderError(
                    f"Dịch vụ AI phát hiện trang phục tạm thời không khả dụng: HTTP {resp.status_code}."
                )

            data = resp.json()
            json_text = _extract_json_from_gemini_response(data)
            parsed_json = json.loads(json_text)
            validated = GeminiDetectorOutput.model_validate(parsed_json)

            domain_boxes: list[BoundingBoxDetection] = []
            for b in validated.boxes:
                domain_boxes.append(
                    BoundingBoxDetection(
                        box=b.box,
                        label=b.label,
                        confidence=ConfidenceValue(b.confidence),
                    )
                )

            return DetectionResult(
                input_kind=validated.input_kind,
                boxes=domain_boxes,
                quality_warnings=validated.quality_warnings,
            )

        except httpx.TimeoutException as err:
            logger.warning("Gemini detector request timed out: %s", err)
            raise TimeoutError("AI detector request timed out.") from err
        except ProviderError:
            raise
        except (json.JSONDecodeError, ValidationError) as parse_err:
            logger.error("Failed to parse/validate Gemini detector response: %s", parse_err)
            raise ProviderError("Dữ liệu nhận diện từ dịch vụ AI không hợp lệ.") from parse_err
        except Exception as err:
            logger.error("Unexpected error in Gemini detector: %s", err)
            raise ProviderError("Dịch vụ AI phát hiện trang phục gặp sự cố ngoài dự kiến.") from err


class GeminiVisionProvider:
    """Production adapter invoking Google Gemini multimodal API for attribute extraction."""

    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float = 30.0,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._client = client

    def extract_attributes(self, crop_bytes: bytes) -> VisionExtractionResult:
        """Call Gemini to extract structured fashion attributes and per-field confidence scores."""
        url = f"{self.base_url}/models/{self.model}:generateContent"
        params = {"key": self.api_key.get_secret_value()}
        encoded_crop = base64.b64encode(crop_bytes).decode("ascii")
        crop_mime_type = _detect_image_mime_type(crop_bytes)

        prompt = (
            "Analyze this cropped clothing item. Extract fashion attributes: "
            "category (top, bottom, footwear, outerwear, dress, accessory), sub_category, primary_color, "
            "secondary_color, pattern, material, style, fit, formality_level (1-5), season (list), "
            "weather_suitability (list), functional_flags (list), free_text_tags (list). "
            "Provide field_confidence: dictionary mapping field names to confidence values between 0.0 and 1.0. "
            "Return a JSON object with keys: 'attributes', 'field_confidence', and 'quality_warnings'."
        )

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": crop_mime_type,
                                "data": encoded_crop,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
            },
        }

        try:
            if self._client is not None:
                resp = self._client.post(
                    url, params=params, json=payload, timeout=self.timeout_seconds
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    resp = client.post(url, params=params, json=payload)

            if resp.status_code >= 400:
                logger.error("Gemini vision provider HTTP error %d: %s", resp.status_code, resp.text)
                raise ProviderError(
                    f"Dịch vụ AI trích xuất thuộc tính tạm thời không khả dụng: HTTP {resp.status_code}."
                )

            data = resp.json()
            json_text = _extract_json_from_gemini_response(data)
            parsed_json = json.loads(json_text)
            validated = GeminiVisionOutput.model_validate(parsed_json)

            # Ensure confidence scores are bounded in [0.0, 1.0]
            bounded_conf: dict[str, ConfidenceValue] = {
                k: ConfidenceValue(max(0.0, min(1.0, float(v))))
                for k, v in validated.field_confidence.items()
            }

            return VisionExtractionResult(
                attributes=validated.attributes,
                field_confidence=bounded_conf,
                quality_warnings=validated.quality_warnings,
            )

        except httpx.TimeoutException as err:
            logger.warning("Gemini vision provider request timed out: %s", err)
            raise TimeoutError("AI vision provider timed out.") from err
        except ProviderError:
            raise
        except (json.JSONDecodeError, ValidationError) as parse_err:
            logger.error("Failed to parse/validate Gemini vision response: %s", parse_err)
            raise ProviderError("Dữ liệu thuộc tính trả về từ AI không hợp lệ.") from parse_err
        except Exception as err:
            logger.error("Unexpected error in Gemini vision provider: %s", err)
            raise ProviderError("Dịch vụ AI trích xuất thuộc tính gặp sự cố ngoài dự kiến.") from err
