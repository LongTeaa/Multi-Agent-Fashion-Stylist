from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
import json
from typing import Any

import httpx
from pydantic import SecretStr

from app.services.gemini_provider import _extract_json_from_gemini_response
from app.services.providers import WeatherContextResult
from app.services.weather_providers import EVENT_HOURS, temperature_condition


class GeminiContextProvider:
    """Gemini adapter for structured Vietnamese context extraction."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float = 15.0,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url
        self._client = client

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
            f"Current date: {current_date.isoformat()}. Explicit location: {location!r}. Request: {query}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key.get_secret_value()}
        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return json.loads(_extract_json_from_gemini_response(response.json()))
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
            "3. Tuyệt đối KHÔNG dùng các cụm từ: 'lý tưởng', 'rất phù hợp', 'thoáng mát', 'mềm mại'."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key.get_secret_value()}
        req_timeout = min(self.timeout_seconds, 6.0)
        try:
            if self._client is not None:
                response = self._client.post(url, headers=headers, json=payload, timeout=req_timeout)
            else:
                with httpx.Client(timeout=req_timeout) as client:
                    response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            parsed = json.loads(_extract_json_from_gemini_response(response.json()))
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
            "3. Tuyệt đối KHÔNG dùng các cụm từ: 'lý tưởng', 'rất phù hợp', 'thoáng mát', 'mềm mại'."
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key.get_secret_value()}
        req_timeout = min(self.timeout_seconds, 8.0)
        try:
            if self._client is not None:
                response = self._client.post(url, headers=headers, json=payload, timeout=req_timeout)
            else:
                with httpx.Client(timeout=req_timeout) as client:
                    response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            parsed = json.loads(_extract_json_from_gemini_response(response.json()))
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
