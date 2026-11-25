from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timezone, timedelta
import json
import time
from typing import Any

import httpx
from pydantic import SecretStr

from app.services.deadline import call_with_deadline
from app.services.gemini_key_pool import GeminiKeyPool
from app.services.gemini_provider import _extract_json_from_gemini_response
from app.services.providers import WeatherContextResult
from app.services.weather_providers import EVENT_HOURS, temperature_condition


def build_gemini_generation_config(
    model: str | None,
    *,
    thinking_level: str | None = "minimal",
) -> dict[str, Any]:
    """Build Gemini generationConfig for JSON output with bounded thinking latency on Gemini 3 models."""
    cfg: dict[str, Any] = {"response_mime_type": "application/json"}
    if thinking_level and "gemini-3" in (model or "").lower():
        cfg["thinkingConfig"] = {"thinkingLevel": thinking_level}
    return cfg


def extract_google_retry_delay_seconds(response: httpx.Response) -> float | None:
    """Parse cooldown duration (1s..86400s) from Retry-After header or Google JSON RetryInfo.retryDelay."""
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return min(86400.0, max(1.0, float(raw.strip())))
        except ValueError:
            pass
    try:
        body = response.json()
    except Exception:
        return None
    details = (body.get("error") or {}).get("details")
    if not isinstance(details, list):
        return None
    for entry in details:
        if not isinstance(entry, dict):
            continue
        raw_delay = entry.get("retryDelay")
        if raw_delay is None:
            continue
        text = str(raw_delay).strip()
        if text.endswith("s"):
            text = text[:-1].strip()
        try:
            return min(86400.0, max(1.0, float(text)))
        except ValueError:
            continue
    return None


def post_gemini_generate_content(
    *,
    base_url: str,
    model: str,
    payload: dict[str, Any],
    timeout: float,
    key_pool: GeminiKeyPool,
    http_client: httpx.Client | None = None,
    max_retries: int = 0,
    initial_backoff_seconds: float = 1.0,
    request_delay_seconds: float = 0.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute Gemini generateContent POST with key-pool rotation, daily-quota detection, and bounded retries."""
    url = f"{base_url.rstrip('/')}/models/{model}:generateContent"
    max_attempts = max(1, int(max_retries) + 1)

    def _send(req_payload: dict[str, Any], current_key: SecretStr, attempt_deadline: float) -> httpx.Response:
        """POST within the attempt's wall-clock budget (httpx alone bounds each phase only)."""
        budget = attempt_deadline - time.monotonic()
        headers = {"x-goog-api-key": current_key.get_secret_value()}

        def post() -> httpx.Response:
            if http_client is not None:
                return http_client.post(url, headers=headers, json=req_payload, timeout=budget)
            with httpx.Client(timeout=budget) as client:
                return client.post(url, headers=headers, json=req_payload)

        try:
            return call_with_deadline(post, budget, message="Gemini request exceeded its deadline.")
        except TimeoutError as exc:
            raise httpx.TimeoutException("Gemini request exceeded its deadline.") from exc

    for attempt in range(max_attempts):
        if request_delay_seconds > 0:
            sleep_fn(request_delay_seconds)
        current_key = key_pool.get_next_key()
        attempt_deadline = time.monotonic() + timeout
        try:
            response = _send(payload, current_key, attempt_deadline)
        except httpx.TimeoutException:
            if attempt + 1 < max_attempts:
                sleep_fn(initial_backoff_seconds * (2 ** attempt))
                continue
            raise

        if response.status_code == 400 and "thinkingConfig" in payload.get("generationConfig", {}):
            # Compatibility fallback if a preview model variant rejects thinkingConfig
            fallback_gen = {k: v for k, v in payload["generationConfig"].items() if k != "thinkingConfig"}
            fallback_payload = {**payload, "generationConfig": fallback_gen}
            # Same attempt, same deadline: the compatibility retry cannot extend the wait.
            response = _send(fallback_payload, current_key, attempt_deadline)

        if response.status_code == 429:
            retry_after = extract_google_retry_delay_seconds(response)
            key_pool.mark_rate_limited(current_key, custom_cooldown=retry_after)
            if attempt + 1 < max_attempts:
                if key_pool.active_keys_count > 0:
                    continue
                status = key_pool.get_pool_status()
                min_rem = min((k["cooldown_remaining_seconds"] for k in status["keys"]), default=0.0)
                if min_rem > 120.0:
                    response.raise_for_status()
                wait = min(retry_after if retry_after is not None else initial_backoff_seconds * (2 ** attempt), 30.0)
                sleep_fn(wait)
                continue
            response.raise_for_status()

        if response.status_code in {500, 502, 503, 504} and attempt + 1 < max_attempts:
            sleep_fn(initial_backoff_seconds * (2 ** attempt))
            continue

        response.raise_for_status()
        return response.json()
    raise RuntimeError("Exhausted Gemini retry attempts.")


EXPLANATION_PROMPT_VERSION = "v2"


class GeminiContextProvider:
    """Gemini adapter for structured Vietnamese context extraction."""

    explanation_prompt_version: str = EXPLANATION_PROMPT_VERSION

    def __init__(
        self,
        *,
        api_key: SecretStr | None = None,
        model: str,
        timeout_seconds: float = 15.0,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.Client | None = None,
        key_pool: GeminiKeyPool | None = None,
        max_retries: int = 0,
        initial_backoff_seconds: float = 1.0,
        explanation_timeout_seconds: float | None = None,
        request_delay_seconds: float = 0.0,
        thinking_level: str | None = "minimal",
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if key_pool is not None:
            self.key_pool = key_pool
            self.api_key = key_pool.keys[0]
        elif api_key is not None:
            self.api_key = api_key
            self.key_pool = GeminiKeyPool([api_key])
        else:
            raise ValueError("GeminiContextProvider requires either 'api_key' or 'key_pool'.")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")
        self._client = client
        self.max_retries = max(0, int(max_retries))
        self.initial_backoff_seconds = max(0.0, float(initial_backoff_seconds))
        self.explanation_timeout_seconds = explanation_timeout_seconds
        self.request_delay_seconds = max(0.0, float(request_delay_seconds))
        self.thinking_level = thinking_level
        self._sleep = sleep_fn

    def _post_gemini_json(self, *, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        """Execute a Gemini generateContent POST with optional key-pool rotation and bounded retries."""
        return post_gemini_generate_content(
            base_url=self.base_url,
            model=self.model,
            payload=payload,
            timeout=timeout,
            key_pool=self.key_pool,
            http_client=self._client,
            max_retries=self.max_retries,
            initial_backoff_seconds=self.initial_backoff_seconds,
            request_delay_seconds=self.request_delay_seconds,
            sleep_fn=self._sleep,
        )

    def extract_context(
        self,
        *,
        query: str,
        location: str | None,
        current_date: date,
    ) -> dict[str, Any]:
        prompt = (
            "Extract normalized styling context from this Vietnamese request. Return JSON only with: "
            "occasion, time_of_day, event_date, location_text, environment, weather_condition, "
            "temperature_celsius, target_formality_range, style_hints, vibe_keywords, must_have, "
            "must_avoid, weather_source, needs_clarification, clarification_question, confidence. "
            "Use weather_source='user' only for weather explicitly stated by the user; otherwise 'default'. "
            "Allowed occasion: cafe, daily_work, interview, wedding, party, date, casual. "
            "Allowed time_of_day: morning, afternoon, evening, night. "
            "Allowed environment: indoor, outdoor, mixed, or null. "
            "Allowed weather_condition: hot, warm, cool, cold, rainy. "
            "Do not invent weather, temperature, location, date, or garment requirements. "
            "When no weather is stated use weather_condition='cool', temperature_celsius=null. "
            "event_date is YYYY-MM-DD, or null if no event date is stated. "
            "must_have/must_avoid must quote only garment/color/material phrases actually in the request. "
            "Cooling clothing preferences are not statements of current weather. "
            "Ask a concise Vietnamese clarification if occasion/intent is materially ambiguous. "
            "target_formality_range must be a JSON array of two integers between 1 and 5 (e.g. [3, 4]), never strings or objects. "
            "Always return non-null string values for occasion (use 'casual' if unclear) and time_of_day (use 'morning' if unclear) even when needs_clarification=true. "
            f"Current date: {current_date.isoformat()}. Explicit location: {location!r}. Request: {query}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": build_gemini_generation_config(self.model, thinking_level=self.thinking_level),
        }
        try:
            raw_json = self._post_gemini_json(payload=payload, timeout=self.timeout_seconds)
            return json.loads(_extract_json_from_gemini_response(raw_json))
        except httpx.TimeoutException as exc:
            raise TimeoutError("Context provider timed out.") from exc
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError("Context provider returned an invalid response.") from exc

    def generate_outfit_explanation(
        self,
        *,
        items_description: list[str],
        occasion: str,
        weather_condition: str,
        target_formality_range: list[int],
        composite_score: float,
        applied_preferences: list[str],
        relaxation_notes: list[str],
        conflict_notes: list[str],
    ) -> str:
        """Generate a grounded Vietnamese stylist explanation for one selected outfit."""
        items_str = ", ".join(items_description)
        prefs_str = "; ".join(applied_preferences) if applied_preferences else "không có"
        relax_str = " ".join(relaxation_notes) if relaxation_notes else "không có"
        conflict_str = " ".join(conflict_notes) if conflict_notes else "không có"
        prompt = (
            "Bạn là chuyên gia tư vấn phối đồ (Fashion Stylist). Hãy viết lời giải thích ngắn gọn (2 câu tiếng Việt) "
            "cho bộ trang phục đã chọn dưới đây. Chỉ trả về JSON hợp lệ theo mẫu {\"explanation_vi\": \"...\"}.\n"
            f"- Các món đồ bắt buộc phải giữ nguyên cách viết trong ngoặc vuông: {items_str}\n"
            f"- Dịp: {occasion}, thời tiết: {weather_condition}, khoảng trang trọng mục tiêu: {target_formality_range}\n"
            f"- Điểm phù hợp tổng hợp: {round(composite_score * 100)}%\n"
            f"- Sở thích áp dụng: {prefs_str}\n"
            f"- Ghi chú nới lỏng (nếu có): {relax_str}\n"
            f"- Ghi chú cân bằng xung đột (nếu có): {conflict_str}\n"
            "Quy tắc bắt buộc:\n"
            "1. Phải nhắc đúng và đủ tất cả các cụm [Tên món đồ] đã liệt kê ở trên, giữ nguyên dấu ngoặc vuông [...].\n"
            "2. Tuyệt đối không bịa thêm bất kỳ món đồ, phụ kiện hay chất liệu nào không có trong danh sách.\n"
            "3. Tuyệt đối KHÔNG dùng các cụm từ: 'lý tưởng', 'rất phù hợp', 'thoáng mát', 'mềm mại'.\n"
            "4. Tuyệt đối KHÔNG khẳng định tính năng kỹ thuật của trang phục nếu không được ghi rõ "
            "(KHÔNG dùng các cụm: 'giữ ấm', 'chống lạnh', 'chống rét', 'giữ nhiệt', 'chống thấm', "
            "'chống nước', 'chống mưa', 'chống nắng', 'chống gió', 'thoáng khí', 'thấm hút', 'co giãn', 'dễ vận động'); "
            "không nhắc thêm màu sắc, chất liệu hay món đồ nằm ngoài danh sách bộ đó."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": build_gemini_generation_config(self.model, thinking_level=self.thinking_level),
        }
        req_timeout = (
            float(self.explanation_timeout_seconds)
            if self.explanation_timeout_seconds is not None
            else min(self.timeout_seconds, 6.0)
        )
        try:
            raw_json = self._post_gemini_json(payload=payload, timeout=req_timeout)
            parsed = json.loads(_extract_json_from_gemini_response(raw_json))
            text = parsed.get("explanation_vi", "")
            return str(text).strip() if isinstance(text, str) else ""
        except Exception as exc:
            raise RuntimeError("Failed to generate LLM outfit explanation.") from exc

    def generate_outfit_explanations(
        self,
        *,
        outfits: list[dict[str, Any]],
        occasion: str,
        weather_condition: str,
        target_formality_range: list[int],
        conflict_notes: list[str],
    ) -> list[str]:
        """Generate grounded Vietnamese explanations for up to 3 outfits in a single Gemini call."""
        if not outfits:
            return []
        conflict_str = " ".join(conflict_notes) if conflict_notes else "không có"
        outfit_lines: list[str] = []
        for idx, entry in enumerate(outfits, start=1):
            items_str = ", ".join(entry.get("items_description", []))
            prefs = entry.get("applied_preferences") or []
            prefs_str = "; ".join(prefs) if prefs else "không có"
            relax = entry.get("relaxation_notes") or []
            relax_str = " ".join(relax) if relax else "không có"
            score_pct = round(float(entry.get("composite_score", 0.0)) * 100)
            outfit_lines.append(
                f"Bộ {idx}:\n"
                f"  - Các món đồ bắt buộc giữ nguyên dấu ngoặc vuông: {items_str}\n"
                f"  - Điểm phù hợp tổng hợp: {score_pct}%\n"
                f"  - Sở thích áp dụng: {prefs_str}\n"
                f"  - Ghi chú nới lỏng (nếu có): {relax_str}"
            )
        outfits_block = "\n".join(outfit_lines)
        prompt = (
            "Bạn là chuyên gia tư vấn phối đồ (Fashion Stylist). Hãy viết lời giải thích ngắn gọn (2 câu tiếng Việt mỗi bộ) "
            f"cho đúng {len(outfits)} bộ trang phục dưới đây. "
            'Chỉ trả về JSON hợp lệ theo mẫu {"explanations": ["...", "..."]} với đúng thứ tự và số lượng phần tử bằng số bộ.\n'
            f"- Dịp: {occasion}, thời tiết: {weather_condition}, khoảng trang trọng mục tiêu: {target_formality_range}\n"
            f"- Ghi chú cân bằng xung đột (nếu có): {conflict_str}\n"
            f"{outfits_block}\n"
            "Quy tắc bắt buộc cho TỪNG lời giải thích:\n"
            "1. Phải nhắc đúng và đủ tất cả các cụm [Tên món đồ] của riêng bộ đó, giữ nguyên dấu ngoặc vuông [...].\n"
            "2. Tuyệt đối không bịa thêm bất kỳ món đồ, phụ kiện hay chất liệu nào không có trong danh sách của bộ đó.\n"
            "3. Tuyệt đối KHÔNG dùng các cụm từ: 'lý tưởng', 'rất phù hợp', 'thoáng mát', 'mềm mại'.\n"
            "4. Tuyệt đối KHÔNG khẳng định tính năng kỹ thuật của trang phục nếu không được ghi rõ "
            "(KHÔNG dùng các cụm: 'giữ ấm', 'chống lạnh', 'chống rét', 'giữ nhiệt', 'chống thấm', "
            "'chống nước', 'chống mưa', 'chống nắng', 'chống gió', 'thoáng khí', 'thấm hút', 'co giãn', 'dễ vận động'); "
            "không nhắc thêm màu sắc, chất liệu hay món đồ nằm ngoài danh sách bộ đó."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": build_gemini_generation_config(self.model, thinking_level=self.thinking_level),
        }
        req_timeout = (
            float(self.explanation_timeout_seconds)
            if self.explanation_timeout_seconds is not None
            else min(self.timeout_seconds, 8.0)
        )
        try:
            raw_json = self._post_gemini_json(payload=payload, timeout=req_timeout)
            parsed = json.loads(_extract_json_from_gemini_response(raw_json))
            raw_list = parsed.get("explanations")
            if not isinstance(raw_list, list):
                raise ValueError("Missing 'explanations' list in Gemini batch response.")
            return [str(item).strip() if isinstance(item, str) else "" for item in raw_list]
        except Exception as exc:
            raise RuntimeError("Failed to generate batch LLM outfit explanations.") from exc


class OpenWeatherProvider:
    """OpenWeather forecast adapter normalized to the domain weather taxonomy."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        timeout_seconds: float = 5.0,
        base_url: str = "https://api.openweathermap.org/data/2.5/forecast",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._client = client

    def get_weather(
        self,
        *,
        location: str,
        event_date: date,
        time_of_day: str = "afternoon",
    ) -> WeatherContextResult:
        # The whole lookup must finish within timeout_seconds of wall time.
        return call_with_deadline(
            lambda: self._get_weather_unbounded(location, event_date, time_of_day),
            self.timeout_seconds, message="Weather provider timed out.",
        )

    def _get_weather_unbounded(
        self,
        location: str,
        event_date: date,
        time_of_day: str,
    ) -> WeatherContextResult:
        params = {
            "q": location,
            "appid": self.api_key.get_secret_value(),
            "units": "metric",
            "lang": "vi",
        }
        try:
            if self._client is not None:
                response = self._client.get(
                    self.base_url,
                    params=params,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.get(self.base_url, params=params)
            if response.status_code == 404:
                raise LookupError("Unknown weather location.")
            response.raise_for_status()
            data = response.json()
            local_zone = timezone(timedelta(seconds=int(data["city"]["timezone"])))
            entries = data.get("list", [])
            dated_entries = [
                entry
                for entry in entries
                if datetime.fromtimestamp(entry["dt"], tz=local_zone).date() == event_date
            ]
            if not dated_entries:
                raise LookupError("No forecast is available for the requested date.")
            entry = min(
                dated_entries,
                key=lambda value: abs(
                    datetime.fromtimestamp(value["dt"], tz=local_zone).hour - EVENT_HOURS[time_of_day]
                ),
            )
            temperature = float(entry["main"]["temp"])
            if abs(datetime.fromtimestamp(entry["dt"], tz=local_zone).hour - EVENT_HOURS[time_of_day]) > 3:
                raise LookupError("No forecast near the requested time.")
            condition = temperature_condition(temperature)
            weather_main = str(entry.get("weather", [{}])[0].get("main", "")).lower()
            if weather_main in {"rain", "drizzle", "thunderstorm"}:
                condition = "rainy"
            return WeatherContextResult(
                condition=condition,
                temperature_celsius=temperature,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("Weather provider timed out.") from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("Weather provider returned an invalid response.") from exc
