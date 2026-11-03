"""Opt-in live Weather/Context acceptance against an isolated seeded wardrobe."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from alembic import command
from alembic.config import Config
from sqlmodel import Session

from app.agents.stylist_graph import execute_stylist_recommendation
from app.agents.context_agent import CONTEXT_FALLBACK_WARNING
from app.core.config import get_settings
from app.core.database import create_database_engine
from app.core.dependencies import get_context_llm_provider, get_weather_provider
from app.core.seed import GOLDEN_USER_ID, seed_golden_wardrobe
from app.models.entities import OutfitRecommendation, WardrobeItem
from app.services.outfit_persistence import COORDINATOR_RULE_VERSION
from app.services.providers import ContextLLMProviderProtocol, WeatherContextResult, WeatherProviderProtocol


def record_failure(failures: list[dict[str, object]], provider: str, error: Exception) -> None:
    chain: list[dict[str, object]] = []
    cause: BaseException | None = error
    while cause is not None:
        response = getattr(cause, "response", None)
        chain.append({"type": type(cause).__name__, "http_status": getattr(response, "status_code", None)})
        cause = cause.__cause__
    failures.append({"provider": provider, "chain": chain})


class ContextProbe:
    def __init__(self, provider: ContextLLMProviderProtocol, failures: list[dict[str, object]]) -> None:
        self.provider, self.failures = provider, failures

    def extract_context(self, *, query: str, location: str | None, current_date: date) -> dict[str, Any]:
        try:
            return self.provider.extract_context(query=query, location=location, current_date=current_date)
        except Exception as error:
            record_failure(self.failures, "context", error)
            raise


class WeatherProbe:
    def __init__(self, provider: WeatherProviderProtocol, failures: list[dict[str, object]]) -> None:
        self.provider, self.failures = provider, failures

    def get_weather(self, *, location: str, event_date: date, time_of_day: str = "afternoon") -> WeatherContextResult:
        try:
            return self.provider.get_weather(location=location, event_date=event_date, time_of_day=time_of_day)
        except Exception as error:
            record_failure(self.failures, "weather", error)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-weather", action="store_true")
    parser.add_argument("--live-context", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if not args.live_weather and not args.live_context:
        parser.error("Explicit --live-weather or --live-context is required")
    settings = get_settings()
    weather = get_weather_provider() if args.live_weather else None
    llm = get_context_llm_provider() if args.live_context else None
    if args.live_weather and settings.weather_provider not in {"openmeteo", "openweather"}:
        parser.error("Select a real WEATHER_PROVIDER first")
    if args.live_context and settings.context_provider != "gemini":
        parser.error("Select CONTEXT_PROVIDER=gemini first")
    failures: list[dict[str, object]] = []
    weather = WeatherProbe(weather, failures) if weather is not None else None
    llm = ContextProbe(llm, failures) if llm is not None else None
    queries = ["Tối nay đi cafe ngoài trời ở Hà Nội",
               "Sáng mai đi làm ở Đà Lạt",
               "Ngày mai phỏng vấn trong nhà ở Hà Nội, cần lịch sự",
               "Tối nay đi cafe ở Hà Nội, trời nóng 35 độ, không mặc màu đen",
               "Mặc gì?"]
    report: dict[str, object] = {"dataset": "weather-context-smoke-v1", "rule_version": COORDINATOR_RULE_VERSION,
        "context_weather_policy": "context-weather-v1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "weather_provider": settings.weather_provider if args.live_weather else "disabled",
        "context_provider": settings.context_provider if args.live_context else "rules",
        "context_model": settings.llm_model if args.live_context else None,
        "cases": []}
    cases: list[dict[str, object]] = []
    original_database = os.environ.get("DATABASE_URL")
    try:
        with TemporaryDirectory(prefix="weather-context-acceptance-") as folder:
            url = f"sqlite:///{Path(folder).as_posix()}/acceptance.db"
            os.environ["DATABASE_URL"] = url
            get_settings.cache_clear()
            command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
            engine = create_database_engine(url)
            try:
                seed_golden_wardrobe(engine)
                for index, query in enumerate(queries):
                    failures.clear()
                    started = perf_counter()
                    with Session(engine) as session:
                        state = execute_stylist_recommendation({"user_id": GOLDEN_USER_ID, "request_id": f"weather-smoke-{index}",
                            "user_query": query}, session=session, llm_provider=llm, weather_provider=weather)
                        context = state.get("context")
                        outfits = state.get("ranked_outfits", [])
                        assert context is not None
                        expected_occasion = ["cafe", "daily_work", "interview", "cafe", "casual"][index]
                        assert context.occasion == expected_occasion
                        assert context.needs_clarification == (index == 4)
                        assert (not outfits) if context.needs_clarification else (1 <= len(outfits) <= 3 and state.get("grounding_validated"))
                        grounded = True
                        for outfit in outfits:
                            assert session.get(OutfitRecommendation, outfit.outfit_id) is not None
                            for item in outfit.items:
                                row = session.get(WardrobeItem, item.item_id)
                                grounded &= bool(row and row.user_id == GOLDEN_USER_ID and row.is_active and row.is_user_confirmed)
                                if index == 3:
                                    assert item.primary_color != "black"
                        case = {"query": query, "context": context.model_dump(mode="json") if context else None,
                            "context_used": "gemini" if llm and CONTEXT_FALLBACK_WARNING not in state.get("warnings", []) else "rules_fallback" if llm else "rules",
                            "provider_failures": list(failures),
                            "warnings": state.get("warnings", []), "errors": state.get("errors", []),
                            "grounded": grounded, "recommendations": [{"rank": outfit.rank,
                                "score": outfit.composite_score, "items": [item.name for item in outfit.items],
                                "explanation": outfit.explanation_vi} for outfit in outfits],
                            "elapsed_seconds": round(perf_counter() - started, 3)}
                        cases.append(case)
                        print(json.dumps({"case": index + 1, "weather_source": context.weather_source if context else None,
                            "outfits": len(outfits), "warnings": case["warnings"], "errors": case["errors"]}), flush=True)
            finally:
                engine.dispose()
    finally:
        if original_database is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database
        get_settings.cache_clear()
    report["cases"] = cases
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assert all(case["grounded"] and not case["errors"] for case in cases)


if __name__ == "__main__":
    main()
