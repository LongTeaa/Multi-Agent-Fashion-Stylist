from __future__ import annotations

from datetime import date
from typing import Any

from app.services.providers import WeatherContextResult


class FakeLLMProvider:
    """Deterministic context-provider fake covering the required failure modes."""

    def __init__(self, scenario: str = "valid") -> None:
        self.scenario = scenario

    def extract_context(
        self,
        *,
        query: str,
        location: str | None,
        current_date: date,
    ) -> dict[str, Any]:
        if self.scenario == "valid" and query.strip().casefold().rstrip("?") == "mặc gì":
            return FakeLLMProvider("low_confidence").extract_context(
                query=query,
                location=location,
                current_date=current_date,
            )
        if self.scenario == "timeout":
            raise TimeoutError("Context provider timed out.")
        if self.scenario == "provider_error":
            raise RuntimeError("Context provider failed.")
        if self.scenario == "malformed":
            return {"occasion": 123, "target_formality_range": [9]}
        if self.scenario == "low_confidence":
            return {
                "occasion": "casual",
                "time_of_day": "morning",
                "event_date": None,
                "location_text": location,
                "environment": None,
                "weather_condition": "warm",
                "target_formality_range": [2, 3],
                "weather_source": "default",
                "needs_clarification": True,
                "clarification_question": "Bạn dự định mặc trang phục này đi đâu và vào thời gian nào?",
                "confidence": 0.3,
            }
        return {
            "occasion": "cafe",
            "time_of_day": "evening",
            "event_date": current_date.isoformat(),
            "location_text": location,
            "environment": "outdoor",
            "weather_condition": "cool",
            "temperature_celsius": None,
            "target_formality_range": [2, 3],
            "style_hints": ["smart_casual"],
            "vibe_keywords": [],
            "must_have": [],
            "must_avoid": [],
            "weather_source": "default",
            "needs_clarification": False,
            "clarification_question": None,
            "confidence": 0.95,
        }


class FakeWeatherProvider:
    """Deterministic weather fake used by offline tests."""

    def __init__(self, scenario: str = "success") -> None:
        self.scenario = scenario

    def get_weather(
        self,
        *,
        location: str,
        event_date: date,
    ) -> WeatherContextResult:
        del location, event_date
        if self.scenario == "timeout":
            raise TimeoutError("Weather provider timed out.")
        if self.scenario == "unknown_location":
            raise LookupError("Unknown location.")
        if self.scenario == "provider_error":
            raise RuntimeError("Weather provider failed.")
        return WeatherContextResult(condition="cold", temperature_celsius=18.0)
