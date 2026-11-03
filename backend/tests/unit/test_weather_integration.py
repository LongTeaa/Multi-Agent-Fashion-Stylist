from datetime import date, datetime, timezone
from unittest.mock import patch
from typing import Any

import httpx
from pydantic import SecretStr
import pytest

from app.agents.context_agent import extract_context, extract_context_with_providers
from app.agents.context_scoring import calculate_functional_fit
from app.agents.fashion_agent import evaluate_and_rank_combinations
from app.agents.fashion_scoring import calculate_aesthetic_score, calculate_style_score, calculate_proportion_score
from app.core.config import Settings
from app.core.dependencies import get_weather_provider
from app.models.entities import OutfitSlotRole as Role
from app.services.context_providers import GeminiContextProvider, OpenWeatherProvider
from app.services.fakes.context_fakes import FakeLLMProvider, FakeWeatherProvider
from app.services.weather_providers import OpenMeteoProvider
from app.services.providers import WeatherContextResult
from tests.unit.test_context_scoring import _make_slot

DAY = date(2026, 11, 3)


def meteo_client(*, temperature: object = 18, code: int = 61, failure: str = "") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("controlled", request=request)
        if failure == "http":
            return httpx.Response(503)
        if "geocoding" in request.url.host:
            results = [{"name": "Hà Nội", "country_code": "VN", "latitude": 21, "longitude": 105}]
            return httpx.Response(200, json={"results": [] if failure == "unknown" else results})
        assert request.url.params["timezone"] == "auto"
        return httpx.Response(200, json={"hourly": {
            "time": ["2026-11-03T09:00", "2026-11-03T19:00"] if failure != "date" else [],
            "temperature_2m": [34, temperature], "weather_code": [0, code]}})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openmeteo_uses_local_event_bucket_and_rain_code() -> None:
    with meteo_client() as client:
        provider = OpenMeteoProvider(client=client)
        morning = provider.get_weather(location="Hà Nội", event_date=DAY, time_of_day="morning")
        evening = provider.get_weather(location="Hà Nội", event_date=DAY, time_of_day="evening")
    assert (morning.condition, morning.temperature_celsius) == ("hot", 34)
    assert (evening.condition, evening.temperature_celsius) == ("rainy", 18)


@pytest.mark.parametrize("mode", ["success", "malformed", "rate_limit", "timeout"])
def test_real_gemini_adapter_contract_and_fallback_without_external_calls(mode: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-goog-api-key"] == "test-key"
        assert "key=" not in str(request.url)
        if mode == "rate_limit":
            return httpx.Response(429)
        if mode == "timeout":
            raise httpx.ReadTimeout("controlled", request=request)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text":
            "not json" if mode == "malformed" else '{"occasion":"cafe","time_of_day":"evening","weather_condition":"cool","weather_source":"default"}'}]}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        context, warnings = extract_context_with_providers("Tối nay đi cafe ở Hà Nội", current_date=DAY,
            llm_provider=GeminiContextProvider(api_key=SecretStr("test-key"), model="test-model", client=client),
            weather_provider=FakeWeatherProvider("hot"))
    assert (context.occasion, context.time_of_day, context.weather_source, context.weather_condition) == ("cafe", "evening", "api", "hot")
    assert bool(warnings) == (mode != "success")


@pytest.mark.parametrize("failure,temperature", [("timeout", 18), ("http", 18), ("unknown", 18),
                                                ("date", 18), ("", None), ("", "nan")])
def test_weather_failures_fall_back_without_fabricating_api_source(failure: str, temperature: object) -> None:
    with meteo_client(failure=failure, temperature=temperature) as client:
        context, warnings = extract_context_with_providers("Tối nay đi cafe ở Hà Nội", current_date=DAY,
            weather_provider=OpenMeteoProvider(client=client))
    assert context.weather_source == "default"
    assert context.temperature_celsius is None
    assert warnings


def test_openweather_uses_city_timezone_instead_of_noon_utc() -> None:
    def entry(utc_hour: int, temperature: int) -> dict[str, object]:
        return {"dt": int(datetime(2026, 11, 3, utc_hour, tzinfo=timezone.utc).timestamp()),
                "main": {"temp": temperature}, "weather": [{"main": "Clear"}]}
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
        "city": {"timezone": 25200}, "list": [entry(2, 34), entry(12, 18)]})))
    with client:
        provider = OpenWeatherProvider(api_key=SecretStr("test"), client=client)
        assert provider.get_weather(location="Hanoi", event_date=DAY, time_of_day="morning").condition == "hot"
        assert provider.get_weather(location="Hanoi", event_date=DAY, time_of_day="evening").temperature_celsius == 18


def test_openmeteo_configuration_requires_no_secret() -> None:
    with patch("app.core.dependencies.get_settings", return_value=Settings(_env_file=None, weather_provider="openmeteo")):
        assert isinstance(get_weather_provider(), OpenMeteoProvider)


def test_provider_latin_eth_spelling_of_da_lat_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "geocoding" in request.url.host:
            return httpx.Response(200, json={"results": [{"name": "Ðà Lạt", "country_code": "VN",
                "latitude": 11.94, "longitude": 108.44}]})
        return httpx.Response(200, json={"hourly": {"time": ["2026-11-03T09:00"],
            "temperature_2m": [18], "weather_code": [3]}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenMeteoProvider(client=client).get_weather(location="Đà Lạt", event_date=DAY, time_of_day="morning")
    assert result.condition == "cool"


def test_explicit_facts_override_wrong_llm_and_llm_cannot_claim_api_weather() -> None:
    class WrongLLM(FakeLLMProvider):
        def extract_context(self, **kwargs: Any) -> dict[str, Any]:
            return {**super().extract_context(**kwargs), "occasion": "wedding", "time_of_day": "morning",
                    "event_date": "2099-01-01", "location_text": "Paris", "environment": "indoor",
                    "weather_source": "api", "weather_condition": "hot", "temperature_celsius": 45}
    class Weather(FakeWeatherProvider):
        def get_weather(self, **kwargs: Any) -> WeatherContextResult:
            assert kwargs == {"location": "Hà Nội", "event_date": DAY, "time_of_day": "evening"}
            return super().get_weather(**kwargs)
    context, warnings = extract_context_with_providers("Tối nay đi cafe ngoài trời ở Hà Nội",
        current_date=DAY, llm_provider=WrongLLM(), weather_provider=Weather("rainy"))
    assert not warnings
    assert (context.occasion, context.environment, context.target_formality_range) == ("cafe", "outdoor", [2, 3])
    assert (context.weather_condition, context.weather_source) == ("rainy", "api")
    assert context.weight_profile == "active"


def test_cooling_clothing_preference_does_not_block_weather_lookup() -> None:
    context, warnings = extract_context_with_providers("Tối nay đi cafe ở Hà Nội, ưu tiên đồ thoáng mát",
        current_date=DAY, weather_provider=FakeWeatherProvider("hot"))
    assert not warnings
    assert (context.weather_source, context.weather_condition) == ("api", "hot")


def test_llm_cannot_add_an_unstated_garment_constraint() -> None:
    class WrongLLM(FakeLLMProvider):
        def extract_context(self, **kwargs: Any) -> dict[str, Any]:
            return {**super().extract_context(**kwargs), "must_have": ["áo đen"], "must_avoid": ["quần jeans"]}
    context, _ = extract_context_with_providers("Tối nay đi cafe ở Hà Nội", current_date=DAY, llm_provider=WrongLLM())
    assert context.must_have == [] and context.must_avoid == []


def test_llm_can_extract_a_grounded_city_outside_the_fallback_dictionary() -> None:
    class LocationLLM(FakeLLMProvider):
        def extract_context(self, **kwargs: Any) -> dict[str, Any]:
            return {**super().extract_context(**kwargs), "location_text": "Bắc Ninh"}
    context, _ = extract_context_with_providers("Tối nay đi cafe ở Bắc Ninh", current_date=DAY,
        llm_provider=LocationLLM(), weather_provider=FakeWeatherProvider("hot"))
    assert context.location_text == "Bắc Ninh" and context.weather_source == "api"


@pytest.mark.parametrize("alias,canonical", [("street", "streetwear"), ("athletic", "sporty")])
def test_style_aliases_preserve_proportion_exemptions(alias: str, canonical: str) -> None:
    silhouette = 5 if alias == "street" else 1
    items = [_make_slot("t", Role.TOP, silhouette_level=silhouette),
             _make_slot("b", Role.BOTTOM, silhouette_level=silhouette)]
    assert calculate_proportion_score(items, alias)[0] == calculate_proportion_score(items, canonical)[0]


@pytest.mark.parametrize("value,condition", [(12, "cold"), (20, "cool"), (25, "warm"), (35, "hot")])
def test_numeric_temperature_is_user_weather_and_skips_api(value: int, condition: str) -> None:
    class NotCalled(FakeWeatherProvider):
        def get_weather(self, **kwargs: Any) -> WeatherContextResult:
            pytest.fail("User weather must not be overridden")
    context, warnings = extract_context_with_providers(f"Tối nay đi cafe ở Hà Nội, {value} độ C",
        current_date=DAY, weather_provider=NotCalled())
    assert not warnings
    assert (context.weather_condition, context.temperature_celsius, context.weather_source) == (condition, value, "user")


@pytest.mark.parametrize("phrase,expected", [("ngày kia", "2026-11-05"), ("05/11/2026", "2026-11-05"),
                                            ("2026-11-06", "2026-11-06")])
def test_calendar_dates_and_numeric_hour(phrase: str, expected: str) -> None:
    context = extract_context(f"Đi cafe ở Hà Nội {phrase} lúc 19h", current_date=DAY)
    assert (context.event_date, context.time_of_day) == (expected, "evening")


def test_negated_formal_occasion_is_not_current_intent() -> None:
    context = extract_context("Tối nay không đi tiệc cưới mà đi cafe với bạn", current_date=DAY)
    assert context.occasion == "cafe" and context.weight_profile == "comfort"


def test_weather_suitable_core_survives_shortlist_beyond_five_prettier_cores() -> None:
    cold = [[_make_slot(f"{index}-{role}", role, comfort_level=1, weather=["cold"], material="wool")
             for role in [Role.TOP, Role.BOTTOM, Role.FOOTWEAR]] for index in range(6)]
    hot = [_make_slot(f"hot-{role}", role, color="red" if role == Role.TOP else "white",
                     comfort_level=5, weather=["hot"]) for role in [Role.TOP, Role.BOTTOM, Role.FOOTWEAR]]
    assert calculate_aesthetic_score(cold[0])[0] > calculate_aesthetic_score(hot)[0]
    context = extract_context("Hôm nay đi cafe trời nóng ưu tiên thoải mái", current_date=DAY)
    shortlisted, _ = evaluate_and_rank_combinations([*cold, hot], context, top_k=5)
    assert shortlisted[0].items[0].item_id.startswith("hot-")
    assert shortlisted[0].fashion_score == calculate_aesthetic_score(hot)[0]


def test_capabilities_require_recorded_flags_and_style_aliases_use_same_matrix() -> None:
    jacket = _make_slot("waterproof-name-only", Role.OUTERWEAR, name="Áo khoác chống nước")
    assert calculate_functional_fit([jacket], ["water_resistant"]) == 0
    jacket.functional_flags = ["rain"]
    assert calculate_functional_fit([jacket], ["water_resistant"]) == 0
    a = _make_slot("a", Role.TOP, style="athletic")
    b = _make_slot("b", Role.BOTTOM, style="sporty")
    assert calculate_style_score([a, b]) == 1
