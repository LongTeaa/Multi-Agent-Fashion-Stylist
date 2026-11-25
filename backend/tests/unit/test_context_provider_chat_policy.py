"""Chat requests make one context-provider attempt and never sleep on 429/5xx."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr

from app.agents.context_agent import CONTEXT_FALLBACK_WARNING, extract_context_with_providers
from app.core.config import Settings
from app.core.dependencies import get_context_llm_provider
from app.services.context_providers import GeminiContextProvider


def _gemini_context_settings(keys: list[str]) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        context_provider="gemini",
        llm_model="gemini-test",
        gemini_api_keys=[SecretStr(k) for k in keys],
        context_timeout_seconds=15,
    )


@pytest.mark.parametrize("keys", [["k1"], ["k1", "k2", "k3"]])
def test_app_context_provider_makes_a_single_attempt(keys: list[str]) -> None:
    with patch("app.core.dependencies.get_settings", return_value=_gemini_context_settings(keys)):
        provider = get_context_llm_provider()

    assert isinstance(provider, GeminiContextProvider)
    assert provider.max_retries == 0
    assert provider.key_pool.total_keys == len(keys)


@pytest.mark.parametrize("status", [429, 503])
def test_chat_falls_back_to_rules_after_one_failed_call_without_sleeping(status: int) -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status,
            json={"error": {"details": [{"retryDelay": "20s"}]}},
            headers={"Retry-After": "20"},
        )

    with patch("app.core.dependencies.get_settings", return_value=_gemini_context_settings(["k1", "k2"])):
        app_provider = get_context_llm_provider()
    assert isinstance(app_provider, GeminiContextProvider)
    provider = GeminiContextProvider(
        key_pool=app_provider.key_pool,
        model=app_provider.model,
        timeout_seconds=app_provider.timeout_seconds,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        max_retries=app_provider.max_retries,
        sleep_fn=sleeps.append,
    )

    context, warnings = extract_context_with_providers(
        "Chiều nay đi cafe với bạn, trời mát, nên mặc gì?",
        current_date=date(2026, 11, 25),
        llm_provider=provider,
    )

    assert calls == 1
    assert sleeps == []
    assert CONTEXT_FALLBACK_WARNING in warnings
    assert context.occasion
