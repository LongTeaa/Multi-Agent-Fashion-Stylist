from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import Any

import httpx
from pydantic import SecretStr

from app.services.gemini_provider import _extract_json_from_gemini_response
from app.services.providers import WeatherContextResult


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
            f"Current date: {current_date.isoformat()}. Explicit location: {location!r}. Request: {query}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        params = {"key": self.api_key.get_secret_value()}
        try:
            if self._client is not None:
                response = self._client.post(
                    url,
                    params=params,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(url, params=params, json=payload)
            response.raise_for_status()
            return json.loads(_extract_json_from_gemini_response(response.json()))
        except httpx.TimeoutException as exc:
            raise TimeoutError("Context provider timed out.") from exc
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RuntimeError("Context provider returned an invalid response.") from exc


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
            entries = response.json().get("list", [])
            dated_entries = [
                entry
                for entry in entries
                if datetime.fromtimestamp(entry["dt"], tz=timezone.utc).date() == event_date
            ]
            if not dated_entries:
                raise LookupError("No forecast is available for the requested date.")
            entry = min(
                dated_entries,
                key=lambda value: abs(
                    datetime.fromtimestamp(value["dt"], tz=timezone.utc).hour - 12
                ),
            )
            temperature = float(entry["main"]["temp"])
            weather_main = str(entry.get("weather", [{}])[0].get("main", "")).lower()
            if weather_main in {"rain", "drizzle", "thunderstorm"}:
                condition = "rainy"
            elif temperature < 15:
                condition = "cold"
            elif temperature < 22:
                condition = "cool"
            elif temperature < 28:
                condition = "warm"
            else:
                condition = "hot"
            return WeatherContextResult(
                condition=condition,
                temperature_celsius=temperature,
            )
        except httpx.TimeoutException as exc:
            raise TimeoutError("Weather provider timed out.") from exc
        except LookupError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Weather provider returned an invalid response.") from exc
