"""Measure end-to-end chat latency with the live Gemini context provider (opt-in, paid).

Sends benchmark queries through the real API (`POST /api/v1/stylist/chat`) against a
temporary copy of a wardrobe database, with the configured providers and no response
cache, and records per request:

* end-to-end time of the chat request (in process, so no browser or LAN time);
* time spent in each context-provider call (context extraction, outfit explanations)
  and in the weather provider, the rest being retrieval, scoring and persistence;
* whether the request fell back to the rule parser or produced a clarification.

Provider keys come from the environment or `.env` and are never written to the output.
The source database is copied and never modified.

Usage (from the repository root):
    python backend/scripts/measure_live_chat_latency.py --user-id <uuid> [--user-id <uuid>] \\
        --queries 30 --repeats 2 --explanations both --out <latency.json>
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
from time import perf_counter
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class _Timed:
    """Wrap a provider and record the duration and outcome of each method call."""

    def __init__(self, inner: Any, log: list[dict[str, Any]], methods: tuple[str, ...]) -> None:
        self._inner = inner
        self._log = log
        self._methods = methods

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name not in self._methods or not callable(attr):
            return attr

        def timed(*args: Any, **kwargs: Any) -> Any:
            started = perf_counter()
            try:
                result = attr(*args, **kwargs)
            except BaseException as exc:
                self._log.append({"call": name, "ms": round((perf_counter() - started) * 1000, 1),
                                  "error": type(exc).__name__})
                raise
            self._log.append({"call": name, "ms": round((perf_counter() - started) * 1000, 1)})
            return result

        return timed


def _timed_dependency(
    factory: Callable[[], Any], log: list[dict[str, Any]], methods: tuple[str, ...]
) -> Callable[[], Any]:
    def dependency() -> Any:
        provider = factory()
        return None if provider is None else _Timed(provider, log, methods)

    return dependency


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo), 1)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = [r["total_ms"] for r in rows]
    llm = [r["llm_ms"] for r in rows]
    weather = [r["weather_ms"] for r in rows]
    local = [r["total_ms"] - r["llm_ms"] - r["weather_ms"] for r in rows]
    return {
        "requests": len(rows),
        "total_ms": {"p50": _percentile(total, 0.5), "p95": _percentile(total, 0.95),
                     "mean": round(statistics.fmean(total), 1) if total else None,
                     "max": max(total) if total else None},
        "llm_ms": {"p50": _percentile(llm, 0.5), "p95": _percentile(llm, 0.95)},
        "weather_ms": {"p50": _percentile(weather, 0.5), "p95": _percentile(weather, 0.95)},
        "local_ms": {"p50": _percentile(local, 0.5), "p95": _percentile(local, 0.95)},
        "llm_share_of_total": round(sum(llm) / sum(total), 3) if sum(total) else None,
        "llm_calls": sum(r["llm_calls"] for r in rows),
        "llm_errors": sum(r["llm_errors"] for r in rows),
        "context_fallbacks": sum(r["context_fallback"] for r in rows),
        "clarifications": sum(r["clarification"] for r in rows),
        "http_errors": sum(r["status_code"] != 200 for r in rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", action="append", required=True,
                        help="Existing user in the source database; repeat to alternate users")
    parser.add_argument("--database", type=Path, default=REPOSITORY_ROOT / "data" / "fashion_stylist.db")
    parser.add_argument("--queries", type=int, default=30)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--explanations", choices=("off", "on", "both"), default="both")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    tmp = Path(tempfile.mkdtemp(prefix="chat-latency-"))
    db_copy = tmp / "chat.db"
    shutil.copyfile(args.database, db_copy)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_copy.as_posix()}"

    from fastapi.testclient import TestClient

    from app.agents.context_agent import CONTEXT_FALLBACK_WARNING
    from app.core import dependencies
    from app.core.config import get_settings
    from app.core.database import get_engine
    from app.main import app

    bench = json.loads((REPOSITORY_ROOT / "data" / "fixtures" / "multi_agent_benchmark_v1.json")
                       .read_text(encoding="utf-8"))
    cases = sorted((c for c in bench["representative_cases"] if c.get("expected_status") == "ok"),
                   key=lambda c: c["id"])[: args.queries]
    configs = {"off": [False], "on": [True], "both": [False, True]}[args.explanations]

    original_context = dependencies.get_context_llm_provider
    original_weather = dependencies.get_weather_provider
    results: dict[str, Any] = {}
    for explanations in configs:
        os.environ["ENABLE_LLM_EXPLANATIONS"] = "true" if explanations else "false"
        get_settings.cache_clear()
        get_engine.cache_clear()
        settings = get_settings()
        if settings.context_provider != "gemini":
            parser.error("CONTEXT_PROVIDER must be gemini for a live latency run")
        log: list[dict[str, Any]] = []
        # Overrides take no parameters: FastAPI would treat any parameter as request input.
        context_dep = _timed_dependency(
            original_context, log, ("extract_context", "generate_outfit_explanation", "generate_outfit_explanations"))
        weather_dep = _timed_dependency(original_weather, log, ("get_weather",))

        app.dependency_overrides[original_context] = context_dep
        app.dependency_overrides[original_weather] = weather_dep
        rows: list[dict[str, Any]] = []
        try:
            client = TestClient(app)
            # One unrecorded warm-up request per configuration, so imports, the first
            # database connection and HTTP connection setup are not charged to case 1.
            client.post("/api/v1/stylist/chat", headers={"X-User-Id": args.user_id[0]},
                        json={"query": cases[0]["query"], "location": cases[0].get("location")})
            for repeat in range(args.repeats):
                for index, case in enumerate(cases):
                    user_id = args.user_id[index % len(args.user_id)]
                    log.clear()
                    started = perf_counter()
                    res = client.post("/api/v1/stylist/chat", headers={"X-User-Id": user_id},
                                      json={"query": case["query"], "location": case.get("location")})
                    total_ms = round((perf_counter() - started) * 1000, 1)
                    data = (res.json().get("data") or {}) if res.status_code == 200 else {}
                    llm_calls = [c for c in log if c["call"] != "get_weather"]
                    rows.append({
                        "case_id": case["id"], "repeat": repeat, "user": f"user{args.user_id.index(user_id) + 1}",
                        "status_code": res.status_code, "total_ms": total_ms,
                        "llm_ms": round(sum(c["ms"] for c in llm_calls), 1),
                        "weather_ms": round(sum(c["ms"] for c in log if c["call"] == "get_weather"), 1),
                        "llm_calls": len(llm_calls),
                        "llm_errors": sum("error" in c for c in llm_calls),
                        "calls": [dict(c) for c in log],
                        "context_fallback": CONTEXT_FALLBACK_WARNING in (data.get("warnings") or []),
                        "clarification": bool(data.get("needs_clarification")),
                        "recommendations": len(data.get("recommendations") or []),
                    })
                    print(f"{'expl' if explanations else 'noexpl'} {case['id']} r{repeat}: "
                          f"{total_ms:.0f} ms, llm {rows[-1]['llm_ms']:.0f} ms x{len(llm_calls)}, "
                          f"weather {rows[-1]['weather_ms']:.0f} ms, status {res.status_code}", flush=True)
        finally:
            app.dependency_overrides.clear()
        results["llm_explanations_on" if explanations else "llm_explanations_off"] = {
            "summary": _summary(rows), "requests": rows,
        }

    output = {
        "method": {
            "endpoint": "POST /api/v1/stylist/chat (in-process TestClient)",
            "context_model": get_settings().llm_model, "weather_provider": get_settings().weather_provider,
            "context_timeout_seconds": get_settings().context_timeout_seconds,
            "queries": len(cases), "repeats": args.repeats, "users": len(args.user_id),
            "database": "temporary copy of the source database", "cache": "none",
        },
        "runs": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    for name, run in results.items():
        print(name, json.dumps(run["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
