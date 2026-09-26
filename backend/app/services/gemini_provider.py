from __future__ import annotations

import base64
import json
import logging
import time
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

TRANSIENT_HTTP_STATUS_CODES = {429, 503}


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
        max_retries: int = 2,
        initial_backoff_seconds: float = 1.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._client = client
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds

    def detect(self, image_bytes: bytes) -> DetectionResult:
        """Call Gemini to detect clothing items and determine scene classification."""
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key.get_secret_value()}
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        image_mime_type = _detect_image_mime_type(image_bytes)

        prompt = (
            "Analyze this fashion image. Detect each distinct clothing/garment/accessory item with precise bounding boxes in "
            "normalized [x_min, y_min, x_max, y_max] format within [0.0, 1.0]. "
            "For worn outfits or layered clothing, separate each layer into individual garments (e.g. outerwear, inner top, "
            "bottom, shoes/footwear) instead of grouping the entire outfit into a single full-body or full-image box. "
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

        for attempt in range(self.max_retries + 1):
            try:
                if self._client is not None:
                    resp = self._client.post(
                        url, headers=headers, json=payload, timeout=self.timeout_seconds
                    )
                else:
                    with httpx.Client(timeout=self.timeout_seconds) as client:
                        resp = client.post(url, headers=headers, json=payload)

                if resp.status_code in TRANSIENT_HTTP_STATUS_CODES:
                    if attempt < self.max_retries:
                        backoff = self.initial_backoff_seconds * (2 ** attempt)
                        logger.warning(
                            "Gemini detector HTTP %d on attempt %d/%d; retrying in %.2fs...",
                            resp.status_code,
                            attempt + 1,
                            self.max_retries + 1,
                            backoff,
                        )
                        time.sleep(backoff)
                        continue
                    logger.error(
                        "Gemini detector HTTP error %d after %d attempts: %s",
                        resp.status_code,
                        self.max_retries + 1,
                        resp.text,
                    )
                    raise ProviderError(
                        f"Dịch vụ AI phát hiện trang phục tạm thời không khả dụng: HTTP {resp.status_code}."
                    )

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
            except httpx.TransportError as err:
                if attempt < self.max_retries:
                    backoff = self.initial_backoff_seconds * (2 ** attempt)
                    logger.warning(
                        "Gemini detector transport error (%s) on attempt %d/%d; retrying in %.2fs...",
                        err,
                        attempt + 1,
                        self.max_retries + 1,
                        backoff,
                    )
                    time.sleep(backoff)
                    continue
                logger.error("Gemini detector network error after %d attempts: %s", self.max_retries + 1, err)
                raise ProviderError(f"Không thể kết nối đến dịch vụ AI: {err}") from err
            except ProviderError:
                raise
            except (json.JSONDecodeError, ValidationError) as parse_err:
                logger.error("Failed to parse/validate Gemini detector response: %s", parse_err)
                raise ProviderError("Dữ liệu nhận diện từ dịch vụ AI không hợp lệ.") from parse_err
            except Exception as err:
                logger.error("Unexpected error in Gemini detector: %s", err)
                raise ProviderError("Dịch vụ AI phát hiện trang phục gặp sự cố ngoài dự kiến.") from err

        raise ProviderError("Dịch vụ AI phát hiện trang phục không phản hồi sau các lần thử lại.")


class GeminiVisionProvider:
    """Production adapter invoking Google Gemini multimodal API for attribute extraction."""

    def __init__(
        self,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float = 30.0,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.Client | None = None,
        max_retries: int = 2,
        initial_backoff_seconds: float = 1.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._client = client
        self.max_retries = max_retries
        self.initial_backoff_seconds = initial_backoff_seconds

    def extract_attributes(self, crop_bytes: bytes) -> VisionExtractionResult:
        """Call Gemini to extract structured fashion attributes and per-field confidence scores."""
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key.get_secret_value()}
        encoded_crop = base64.b64encode(crop_bytes).decode("ascii")
        crop_mime_type = _detect_image_mime_type(crop_bytes)

        prompt = (
            "Analyze this cropped clothing item in high detail for a digital fashion stylist wardrobe. "
            "Extract fashion domain attributes strictly conforming to these specifications:\n"
            "- category: one of [top, bottom, footwear, outerwear, dress, accessory]\n"
            "- sub_category: specific item type (e.g., t-shirt, shirt, polo, hoodie, jeans, trousers, shorts, sneakers, loafers, boots, blazer, coat, jacket)\n"
            "- primary_color: dominant color name\n"
            "- secondary_color: secondary color name or null\n"
            "- pattern: pattern type (e.g., solid, striped, plaid, floral, graphic)\n"
            "- material: fabric composition (e.g., cotton, linen, wool, denim, silk, polyester, leather)\n"
            "- style: aesthetic style (e.g., casual, smart_casual, formal, streetwear, athletic, minimalist)\n"
            "- fit: silhouette fit descriptor (e.g., tight, slim, regular, relaxed, oversized)\n"
            "- formality_level: integer from 1 to 5 (1=very casual/loungewear, 3=smart casual, 5=strictly formal/black tie)\n"
            "- comfort_level: integer from 1 to 5 evaluating fabric texture, breathability, softness, stretch and movement freedom:\n"
            "  * 1-2: Stiff, rigid, heavy, unbreathable, restrictive or tight (e.g., rigid raw denim, patent leather, stiff formal corsetry)\n"
            "  * 3: Moderate comfort, standard everyday weave (e.g., classic chino, standard poplin shirt)\n"
            "  * 4-5: Highly comfortable, soft, stretchable, breathable (e.g., soft combed cotton jersey, breathable linen, elastic knitwear, relaxed loungewear)\n"
            "- silhouette_level: integer from 1 to 5 quantifying cut volume and garment outline:\n"
            "  * 1: Extra slim / skin-tight / bodycon\n"
            "  * 2: Slim fit / fitted\n"
            "  * 3: Standard regular fit / straight cut\n"
            "  * 4: Relaxed / loose fit / wide leg\n"
            "  * 5: Oversized / baggy / exaggerated silhouette\n"
            "- length: garment length classification strictly one of: 'cropped' (waist/chest crop, culottes, mini/shorts), 'waist' (hits right at the belt line), 'hip' (standard hip/seat coverage), 'long' (extended, knee/ankle coverage, floor-length)\n"
            "- season: list of suitable seasons from [spring, summer, fall, winter, all_year]\n"
            "- weather_suitability: list of weather types from [hot, warm, mild, cool, cold, rainy, sunny]\n"
            "- functional_flags: list of applicable functional tags from [movement, outdoor, sun, rain, work, sport, protection, water_resistant, heavy, light]\n"
            "- free_text_tags: list of short descriptive tags\n\n"
            "Provide field_confidence: dictionary mapping field names to confidence scores between 0.0 and 1.0.\n"
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

        for attempt in range(self.max_retries + 1):
            try:
                if self._client is not None:
                    resp = self._client.post(
                        url, headers=headers, json=payload, timeout=self.timeout_seconds
                    )
                else:
                    with httpx.Client(timeout=self.timeout_seconds) as client:
                        resp = client.post(url, headers=headers, json=payload)

                if resp.status_code in TRANSIENT_HTTP_STATUS_CODES:
                    if attempt < self.max_retries:
                        backoff = self.initial_backoff_seconds * (2 ** attempt)
                        logger.warning(
                            "Gemini vision provider HTTP %d on attempt %d/%d; retrying in %.2fs...",
                            resp.status_code,
                            attempt + 1,
                            self.max_retries + 1,
                            backoff,
                        )
                        time.sleep(backoff)
                        continue
                    logger.error(
                        "Gemini vision provider HTTP error %d after %d attempts: %s",
                        resp.status_code,
                        self.max_retries + 1,
                        resp.text,
                    )
                    raise ProviderError(
                        f"Dịch vụ AI trích xuất thuộc tính tạm thời không khả dụng: HTTP {resp.status_code}."
                    )

                if resp.status_code >= 400:
                    logger.error("Gemini vision provider HTTP error %d: %s", resp.status_code, resp.text)
                    raise ProviderError(
                        f"Dịch vụ AI trích xuất thuộc tính tạm thời không khả dụng: HTTP {resp.status_code}."
                    )

                data = resp.json()
                json_text = _extract_json_from_gemini_response(data)
                parsed_json = json.loads(json_text)
                validated = GeminiVisionOutput.model_validate(parsed_json)

                # Normalize domain-specific attributes
                attrs = dict(validated.attributes)
                try:
                    c_val = int(attrs.get("comfort_level", 3))
                    attrs["comfort_level"] = max(1, min(5, c_val))
                except (ValueError, TypeError):
                    attrs["comfort_level"] = 3

                try:
                    s_val = int(attrs.get("silhouette_level", 3))
                    attrs["silhouette_level"] = max(1, min(5, s_val))
                except (ValueError, TypeError):
                    attrs["silhouette_level"] = 3

                from app.models.entities import VALID_LENGTH_VALUES
                raw_len = str(attrs.get("length", "hip")).strip().lower()
                attrs["length"] = raw_len if raw_len in VALID_LENGTH_VALUES else "hip"

                if "functional_flags" in attrs and isinstance(attrs["functional_flags"], list):
                    attrs["functional_flags"] = [
                        str(f).strip().lower() for f in attrs["functional_flags"] if str(f).strip()
                    ]
                else:
                    attrs["functional_flags"] = []

                # Ensure confidence scores are bounded in [0.0, 1.0]
                bounded_conf: dict[str, ConfidenceValue] = {
                    k: ConfidenceValue(max(0.0, min(1.0, float(v))))
                    for k, v in validated.field_confidence.items()
                }
                for field_key in ("comfort_level", "silhouette_level", "length"):
                    if field_key not in bounded_conf:
                        bounded_conf[field_key] = ConfidenceValue(0.85)

                return VisionExtractionResult(
                    attributes=attrs,
                    field_confidence=bounded_conf,
                    quality_warnings=validated.quality_warnings,
                )

            except httpx.TimeoutException as err:
                logger.warning("Gemini vision provider request timed out: %s", err)
                raise TimeoutError("AI vision provider timed out.") from err
            except httpx.TransportError as err:
                if attempt < self.max_retries:
                    backoff = self.initial_backoff_seconds * (2 ** attempt)
                    logger.warning(
                        "Gemini vision provider transport error (%s) on attempt %d/%d; retrying in %.2fs...",
                        err,
                        attempt + 1,
                        self.max_retries + 1,
                        backoff,
                    )
                    time.sleep(backoff)
                    continue
                logger.error("Gemini vision provider network error after %d attempts: %s", self.max_retries + 1, err)
                raise ProviderError(f"Không thể kết nối đến dịch vụ AI: {err}") from err
            except ProviderError:
                raise
            except (json.JSONDecodeError, ValidationError) as parse_err:
                logger.error("Failed to parse/validate Gemini vision response: %s", parse_err)
                raise ProviderError("Dữ liệu thuộc tính trả về từ AI không hợp lệ.") from parse_err
            except Exception as err:
                logger.error("Unexpected error in Gemini vision provider: %s", err)
                raise ProviderError("Dịch vụ AI trích xuất thuộc tính gặp sự cố ngoài dự kiến.") from err

        raise ProviderError("Dịch vụ AI trích xuất thuộc tính không phản hồi sau các lần thử lại.")
