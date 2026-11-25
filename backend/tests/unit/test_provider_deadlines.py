"""Provider calls are bounded by wall-clock time, not only by httpx's per-phase timeouts.

httpx.MockTransport ignores httpx timeouts, so a handler that sleeps behaves like a
server that keeps the connection alive while trickling bytes: without a wall-clock
deadline the caller would wait for the whole sleep.
"""

from __future__ import annotations

from datetime import date
import json
import time
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.agents.context_agent import CONTEXT_FALLBACK_WARNING, extract_context_with_providers
from app.services.context_providers import GeminiContextProvider, OpenWeatherProvider
from app.services.deadline import call_with_deadline
from app.services.weather_providers import OpenMeteoProvider

SLOW = 0.8
BUDGET = 0.2
# Generous upper bound for the bounded call on a loaded CI machine, still well below SLOW.
BOUNDED = 0.6

CONTEXT_PAYLOAD = {
    "occasion": "cafe", "time_of_day": "afternoon", "weather_condition": "cool",
    "target_formality_range": [2, 3], "weather_source": "user", "needs_clarification": False,
    "confidence": 0.9,
}


def _gemini_body(payload: dict[str, Any]) -> dict[str, Any]:
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}]}


def _slow_client(delays: list[float], body: dict[str, Any]) -> httpx.Client:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        delay = delays[min(calls["n"], len(delays) - 1)]
        calls["n"] += 1
        time.sleep(delay)
        return httpx.Response(200, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_call_with_deadline_returns_fast_results_and_stops_waiting_for_slow_ones() -> None:
    assert call_with_deadline(lambda: 42, 1.0, message="late") == 42

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="late"):
        call_with_deadline(lambda: time.sleep(SLOW), BUDGET, message="late")
    assert time.monotonic() - started < BOUNDED

    with pytest.raises(TimeoutError):
        call_with_deadline(lambda: 1, 0, message="no budget")


def test_gemini_context_call_stops_at_its_timeout() -> None:
    provider = GeminiContextProvider(
        api_key=SecretStr("test-key"), model="gemini-test", timeout_seconds=BUDGET,
        client=_slow_client([SLOW], _gemini_body(CONTEXT_PAYLOAD)),
    )
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        provider.extract_context(query="Đi cafe", location=None, current_date=date(2026, 11, 25))
    assert time.monotonic() - started < BOUNDED


def test_chat_context_falls_back_to_rules_within_the_timeout() -> None:
    provider = GeminiContextProvider(
        api_key=SecretStr("test-key"), model="gemini-test", timeout_seconds=BUDGET,
        client=_slow_client([SLOW], _gemini_body(CONTEXT_PAYLOAD)),
    )
    started = time.monotonic()
    context, warnings = extract_context_with_providers(
        "Chiều nay đi cafe với bạn, trời mát, nên mặc gì?",
        current_date=date(2026, 11, 25), llm_provider=provider,
    )
    assert time.monotonic() - started < BOUNDED
    assert CONTEXT_FALLBACK_WARNING in warnings
    assert context.occasion


def test_each_retry_attempt_gets_its_own_deadline() -> None:
    """Evaluation runners retry; a slow first attempt must not consume the second one."""
    provider = GeminiContextProvider(
        api_key=SecretStr("test-key"), model="gemini-test", timeout_seconds=BUDGET,
        client=_slow_client([SLOW, 0.0], _gemini_body(CONTEXT_PAYLOAD)),
        max_retries=1, initial_backoff_seconds=0.0, sleep_fn=lambda _: None,
    )
    assert provider.extract_context(query="Đi cafe", location=None, current_date=date(2026, 11, 25))["occasion"] == "cafe"


def test_open_meteo_geocoding_plus_forecast_share_one_deadline() -> None:
    """Two requests that each fit the timeout must still not exceed it together."""

    def handler(request: httpx.Request) -> httpx.Response:
        time.sleep(BUDGET * 0.75)
        if "geocoding" in request.url.host:
            return httpx.Response(200, json={"results": [
                {"name": "Hanoi", "latitude": 21.0, "longitude": 105.8, "country_code": "VN", "population": 8}]})
        return httpx.Response(200, json={"hourly": {
            "time": [f"2026-11-26T{h:02d}:00" for h in range(24)],
            "temperature_2m": [22.0] * 24, "weather_code": [0] * 24}})

    provider = OpenMeteoProvider(timeout_seconds=BUDGET, client=httpx.Client(transport=httpx.MockTransport(handler)))
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        provider.get_weather(location="Hà Nội", event_date=date(2026, 11, 26), time_of_day="morning")
    assert time.monotonic() - started < BUDGET * 1.5 + 0.2


def test_open_weather_call_stops_at_its_timeout() -> None:
    provider = OpenWeatherProvider(
        api_key=SecretStr("test-key"), timeout_seconds=BUDGET, client=_slow_client([SLOW], {}),
    )
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        provider.get_weather(location="Hà Nội", event_date=date(2026, 11, 26))
    assert time.monotonic() - started < BOUNDED
