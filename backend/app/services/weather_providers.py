"""Local-time forecast enrichment; no wardrobe or user identifiers leave the app."""
from datetime import date, datetime
import math
import re
import unicodedata
from time import monotonic
from typing import Literal

import httpx

from app.services.providers import WeatherContextResult

EVENT_HOURS = {"morning": 9, "afternoon": 15, "evening": 19, "night": 22}


def temperature_condition(temperature: float) -> Literal["hot", "warm", "cool", "cold"]:
    if not math.isfinite(temperature) or not -90 <= temperature <= 60:
        raise ValueError("Invalid forecast temperature")
    return "cold" if temperature < 15 else "cool" if temperature < 22 else "warm" if temperature < 28 else "hot"


def location_key(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold().replace("đ", "d").replace("ð", "d"))
    return re.sub(r"[^a-z0-9]", "", value)


class OpenMeteoProvider:
    """Geocode a city and select a forecast in its local event-date/time bucket."""

    def __init__(self, *, timeout_seconds: float = 5, client: httpx.Client | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self._client = client

    def get_weather(self, *, location: str, event_date: date,
                    time_of_day: str = "afternoon") -> WeatherContextResult:
        if self._client is not None:
            return self._fetch(self._client, location, event_date, time_of_day)
        with httpx.Client(timeout=self.timeout_seconds) as client:
            return self._fetch(client, location, event_date, time_of_day)

    def _fetch(self, client: httpx.Client, location: str, event_date: date,
               time_of_day: str) -> WeatherContextResult:
        deadline = monotonic() + self.timeout_seconds
        def remaining() -> float:
            budget = deadline - monotonic()
            if budget <= 0:
                raise TimeoutError("Weather provider timed out.")
            return budget
        aliases = {"hanoi": "Hanoi", "dalat": "Da Lat", "tphcm": "Ho Chi Minh City",
                   "saigon": "Ho Chi Minh City", "thanhphohochiminh": "Ho Chi Minh City",
                   "sapa": "Sa Pa"}
        query = aliases.get(location_key(location), location.strip())
        try:
            response = client.get("https://geocoding-api.open-meteo.com/v1/search",
                params={"name": query, "count": 5, "language": "vi"}, timeout=remaining())
            response.raise_for_status()
            matches = response.json().get("results", [])
            exact = [match for match in matches if location_key(aliases.get(location_key(match["name"]), match["name"])) in {
                location_key(query), location_key(location)}]
            # Known Vietnamese cities should not resolve to an overseas namesake.
            from app.agents.context_agent import COMMON_LOCATIONS
            if location_key(location) in {location_key(name) for name in COMMON_LOCATIONS}:
                exact = [match for match in exact if match.get("country_code") == "VN"]
                exact.sort(key=lambda match: match.get("population", 0), reverse=True)
            elif len({(match.get("country_code"), match.get("admin1")) for match in exact}) > 1:
                raise LookupError("Ambiguous weather location; specify the city and region.")
            if not exact:
                raise LookupError("Unknown weather location.")
            place = exact[0]
            response = client.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": place["latitude"], "longitude": place["longitude"],
                "timezone": "auto", "hourly": "temperature_2m,weather_code",
                "start_date": event_date.isoformat(), "end_date": event_date.isoformat(),
            }, timeout=remaining())
            response.raise_for_status()
            hourly = response.json()["hourly"]
            target_hour = EVENT_HOURS[time_of_day]
            candidates = [(index, datetime.fromisoformat(value)) for index, value in enumerate(hourly["time"])
                          if datetime.fromisoformat(value).date() == event_date]
            if not candidates:
                raise LookupError("No forecast for the requested date.")
            index, timestamp = min(candidates, key=lambda pair: abs(pair[1].hour - target_hour))
            if abs(timestamp.hour - target_hour) > 3:
                raise LookupError("No forecast near the requested time.")
            temperature = float(hourly["temperature_2m"][index])
            condition = temperature_condition(temperature)
            code = int(hourly["weather_code"][index])
            if code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}:
                condition = "rainy"
            elif code in {71, 73, 75, 77, 85, 86}:
                condition = "cold"
            return WeatherContextResult(condition=condition, temperature_celsius=temperature)
        except httpx.TimeoutException as exc:
            raise TimeoutError("Weather provider timed out.") from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("Weather provider returned an invalid response.") from exc
