"""System adapters (Random, Rule-DAG, Single-Prompt LLM, Multi-Agent Full & Ablations) and DB seeding."""
from __future__ import annotations

from collections.abc import Callable
import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import random
import time
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx
from pydantic import SecretStr
from sqlmodel import Session, select

from app.agents.context_agent import CONTEXT_FALLBACK_WARNING
from app.agents.coordinator import generate_grounded_explanation_vi
from app.agents.fashion_agent import generate_outfit_combinations
from app.agents.outfit_diversity import core_signature
from app.agents.state import (
    EvaluatedOutfit,
    OutfitItemSlot,
    RankedOutfit,
    StylistContext,
    StylistGraphState,
)
from app.agents.stylist_graph import execute_stylist_recommendation
from app.agents.wardrobe_agent import format_localized_item_name
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    User,
    UserPreference,
    WardrobeCategory,
    WardrobeItem,
    WearLog,
)
from app.services.context_providers import (
    build_gemini_generation_config,
    post_gemini_generate_content,
)
from app.services.gemini_key_pool import GeminiKeyPool
from app.services.gemini_provider import _extract_json_from_gemini_response
from app.services.retrieval_document_service import refresh_retrieval_document
from tests.evaluation.benchmark.judge import JsonlResultCache


class AbortedLiveRunError(BaseException):
    """Raised when consecutive provider failures exceed the configured threshold.

    Inherits from BaseException so production fallback ``except Exception:`` handlers
    (e.g. in context_agent or coordinator batch explanations) never swallow an abort.
    """


class TelemetryLLMProbe:
    """Wraps a ContextLLMProvider to record calls, token estimates, and failures."""

    def __init__(
        self,
        provider: Any,
        *,
        max_consecutive_failures: int = 3,
    ) -> None:
        self.provider = provider
        self.max_consecutive_failures = max_consecutive_failures
        self.consecutive_failures = 0
        self.reset_case_counters()

    def reset_case_counters(self) -> None:
        self.context_calls = 0
        self.explanation_batch_calls = 0
        self.explanation_single_calls = 0
        self.estimated_tokens = 0
        self.failures: list[dict[str, Any]] = []

    def snapshot(self) -> dict[str, Any]:
        return {
            "llm_calls": self.context_calls + self.explanation_batch_calls + self.explanation_single_calls,
            "context_calls": self.context_calls,
            "explanation_batch_calls": self.explanation_batch_calls,
            "explanation_single_calls": self.explanation_single_calls,
            "estimated_tokens": self.estimated_tokens,
            "failures": list(self.failures),
        }

    def _record_failure(self, stage: str, exc: Exception) -> None:
        self.consecutive_failures += 1
        status_code = None
        cause: BaseException | None = exc
        while cause is not None:
            resp = getattr(cause, "response", None)
            if resp is not None:
                status_code = getattr(resp, "status_code", None)
                break
            cause = cause.__cause__
        self.failures.append(
            {
                "stage": stage,
                "error_type": type(exc).__name__,
                "http_status": status_code,
            }
        )
        if self.consecutive_failures >= self.max_consecutive_failures:
            raise AbortedLiveRunError(
                f"Aborted live run after {self.consecutive_failures} consecutive provider failures ({type(exc).__name__})."
            ) from exc

    def extract_context(
        self,
        *,
        query: str,
        location: str | None,
        current_date: date,
    ) -> dict[str, Any]:
        self.context_calls += 1
        self.estimated_tokens += max(80, len(query) // 3 + 220)
        try:
            payload = self.provider.extract_context(
                query=query,
                location=location,
                current_date=current_date,
            )
            self.consecutive_failures = 0
            self.estimated_tokens += max(60, len(json.dumps(payload, default=str)) // 4)
            return payload
        except AbortedLiveRunError:
            raise
        except Exception as exc:
            self._record_failure("extract_context", exc)
            raise

    def generate_outfit_explanations(
        self,
        *,
        outfits: list[dict[str, Any]],
        occasion: str,
        weather_condition: str,
        target_formality_range: list[int],
        conflict_notes: list[str],
    ) -> list[str]:
        if not hasattr(self.provider, "generate_outfit_explanations"):
            raise AttributeError("Underlying provider lacks generate_outfit_explanations")
        self.explanation_batch_calls += 1
        self.estimated_tokens += 180 + 90 * len(outfits)
        try:
            texts = self.provider.generate_outfit_explanations(
                outfits=outfits,
                occasion=occasion,
                weather_condition=weather_condition,
                target_formality_range=target_formality_range,
                conflict_notes=conflict_notes,
            )
            self.consecutive_failures = 0
            self.estimated_tokens += sum(len(t) for t in texts) // 4
            return texts
        except AbortedLiveRunError:
            raise
        except Exception as exc:
            self._record_failure("generate_outfit_explanations", exc)
            raise

    def generate_outfit_explanation(self, **kwargs: Any) -> str:
        self.explanation_single_calls += 1
        self.estimated_tokens += 180
        try:
            text = self.provider.generate_outfit_explanation(**kwargs)
            self.consecutive_failures = 0
            self.estimated_tokens += len(str(text)) // 4
            return str(text)
        except AbortedLiveRunError:
            raise
        except Exception as exc:
            self._record_failure("generate_outfit_explanation", exc)
            raise


class CachedLLMWrapper:
    """Append-only JSONL disk cache wrapper around a ContextLLMProvider for reproducible benchmark resumes."""

    def __init__(
        self,
        provider: Any,
        *,
        cache: JsonlResultCache,
        provider_name: str = "gemini",
        model_name: str = "unknown",
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.provider_name = provider_name
        self.model_name = model_name
        self.cache_hits = 0
        self.live_calls = 0

    def _make_key(self, kind: str, payload: dict[str, Any]) -> str:
        raw = json.dumps(
            {
                "kind": kind,
                "provider": self.provider_name,
                "model": self.model_name,
                "payload": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def extract_context(
        self,
        *,
        query: str,
        location: str | None,
        current_date: date,
    ) -> dict[str, Any]:
        key = self._make_key(
            "extract_context",
            {
                "query": query,
                "location": location,
                "current_date": current_date.isoformat(),
            },
        )
        cached = self.cache.get(key)
        if cached is not None and isinstance(cached.get("result"), dict):
            self.cache_hits += 1
            return copy.deepcopy(cached["result"])
        self.live_calls += 1
        result = self.provider.extract_context(
            query=query,
            location=location,
            current_date=current_date,
        )
        if isinstance(result, dict):
            self.cache.put(key, {"result": result})
        return copy.deepcopy(result)

    def generate_outfit_explanations(
        self,
        *,
        outfits: list[dict[str, Any]],
        occasion: str,
        weather_condition: str,
        target_formality_range: list[int],
        conflict_notes: list[str],
    ) -> list[str]:
        if not hasattr(self.provider, "generate_outfit_explanations"):
            raise AttributeError("Underlying provider lacks generate_outfit_explanations")
        key = self._make_key(
            "generate_outfit_explanations",
            {
                "outfits": outfits,
                "occasion": occasion,
                "weather_condition": weather_condition,
                "target_formality_range": list(target_formality_range),
                "conflict_notes": list(conflict_notes),
            },
        )
        cached = self.cache.get(key)
        if cached is not None and isinstance(cached.get("result"), list):
            self.cache_hits += 1
            return [str(x) for x in cached["result"]]
        self.live_calls += 1
        texts = self.provider.generate_outfit_explanations(
            outfits=outfits,
            occasion=occasion,
            weather_condition=weather_condition,
            target_formality_range=target_formality_range,
            conflict_notes=conflict_notes,
        )
        if isinstance(texts, list):
            self.cache.put(key, {"result": list(texts)})
        return list(texts)

    def generate_outfit_explanation(self, **kwargs: Any) -> str:
        key = self._make_key("generate_outfit_explanation", kwargs)
        cached = self.cache.get(key)
        if cached is not None and isinstance(cached.get("result"), str):
            self.cache_hits += 1
            return str(cached["result"])
        self.live_calls += 1
        text = self.provider.generate_outfit_explanation(**kwargs)
        self.cache.put(key, {"result": str(text)})
        return str(text)


def _deterministic_noise_item(spec: dict[str, Any], idx: int) -> dict[str, Any]:
    """Apply realistic ingestion-style label noise (~15% unknown material/fit, ~10% style drift)."""
    noisy = dict(spec)
    if idx % 7 == 0:
        noisy["material"] = "unknown"
    if idx % 6 == 0:
        noisy["fit"] = "unknown"
    if idx % 10 == 0:
        cur_style = str(noisy.get("style", "casual"))
        noisy["style"] = "casual" if cur_style == "smart_casual" else "smart_casual"
    return noisy


def seed_case_user(
    session: Session,
    *,
    run_user_id: str,
    wardrobe_specs: list[dict[str, Any]],
    profile_spec: dict[str, Any] | None,
    wear_history: list[dict[str, Any]],
    fixed_now: datetime,
    noise_mode: bool = False,
) -> dict[str, str]:
    """Seed one completely isolated user with wardrobe, preferences, retrieval docs, and wear logs.

    Returns a mapping from benchmark item suffix (or item_id) -> real DB WardrobeItem.id.
    Note: We preserve exact spec['id'] prefixed safely by run_user_id only if needed? No!
    Keeping WardrobeItem.id globally unique per run_user_id avoids cross-user PK collision while
    mapping back cleanly via raw item id (`spec_id`). Wait: to keep assertions readable, we store
    `raw_id = spec['id']` in a unique id `{run_user_id}__{spec['id']}`? Careful: WardrobeItem.id
    has `max_length=36`! So we generate a deterministic 36-char UUID5 per `(run_user_id, spec['id'])`
    and return `{raw_id: db_uuid}` and reverse `{db_uuid: raw_id}`!
    """
    from uuid import NAMESPACE_URL, uuid5

    user_prefix = hashlib.sha256(run_user_id.encode("utf-8")).hexdigest()[:8]

    def _db_item_uuid(raw_id: str) -> str:
        # Order-preserving unique ID (<= 36 chars): guarantees identical tie-breaking order
        # across distinct benchmark run_user_ids for profile sensitivity & noise comparisons.
        candidate = f"{user_prefix}-{raw_id}"
        if len(candidate) <= 36:
            return candidate
        return f"{user_prefix}-{raw_id[:20]}-{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:6]}"

    session.add(User(id=run_user_id, email=f"{run_user_id[:20]}@bench.local"))
    session.flush()

    if profile_spec:
        session.add(
            UserPreference(
                user_id=run_user_id,
                styles=list(profile_spec.get("styles", [])),
                color_palettes=list(profile_spec.get("color_palettes", [])),
                priorities=list(profile_spec.get("priorities", [])),
                avoid_colors=list(profile_spec.get("avoid_colors", [])),
                avoid_styles=list(profile_spec.get("avoid_styles", [])),
                fit_preferences=list(profile_spec.get("fit_preferences", [])),
                ratings_count=int(profile_spec.get("ratings_count", 0)),
                learned_feature_weights=dict(
                    profile_spec.get("learned_feature_weights") or {"version": 1, "weights": {}}
                ),
            )
        )
        session.flush()

    raw_to_db: dict[str, str] = {}
    db_to_item: dict[str, WardrobeItem] = {}

    for idx, raw_spec in enumerate(wardrobe_specs):
        spec = _deterministic_noise_item(raw_spec, idx) if noise_mode else raw_spec
        raw_id = str(spec["id"])
        db_id = _db_item_uuid(raw_id)
        raw_to_db[raw_id] = db_id

        offset_h = spec.get("last_worn_offset_hours")
        last_worn = (
            fixed_now - timedelta(hours=float(offset_h))
            if offset_h is not None
            else None
        )

        item = WardrobeItem(
            id=db_id,
            user_id=run_user_id,
            category=WardrobeCategory(str(spec["category"])),
            sub_category=str(spec["sub_category"]),
            primary_color=str(spec["primary_color"]),
            secondary_color=spec.get("secondary_color"),
            pattern=str(spec.get("pattern", "solid")),
            material=str(spec.get("material", "cotton")),
            style=str(spec.get("style", "casual")),
            fit=str(spec.get("fit", "regular")),
            formality_level=int(spec.get("formality_level", 3)),
            comfort_level=int(spec.get("comfort_level", 3)),
            silhouette_level=int(spec.get("silhouette_level", 3)),
            length=str(spec.get("length", "hip")),
            season=list(spec.get("season", [])),
            weather_suitability=list(spec.get("weather_suitability", ["warm", "cool"])),
            functional_flags=list(spec.get("functional_flags", [])),
            free_text_tags=list(spec.get("free_text_tags", [])),
            is_active=True,
            is_user_confirmed=True,
            times_worn=int(spec.get("times_worn", 1 if last_worn else 0)),
            last_worn_at=last_worn,
            created_at=fixed_now - timedelta(days=7),
            updated_at=fixed_now - timedelta(days=1),
        )
        session.add(item)
        session.flush()
        db_to_item[db_id] = item

        media_id = str(uuid5(NAMESPACE_URL, f"bench-media:{run_user_id}:{raw_id}"))
        session.add(
            MediaAsset(
                id=media_id,
                user_id=run_user_id,
                kind=MediaKind.ORIGINAL,
                bucket="wardrobe-private",
                object_key=f"bench/{run_user_id}/{raw_id}.jpg",
                mime_type="image/jpeg",
                width=512,
                height=512,
                size_bytes=4096,
                sha256="b" * 64,
                created_at=fixed_now - timedelta(days=7),
            )
        )
        session.flush()
        session.add(
            ItemMedia(
                user_id=run_user_id,
                wardrobe_item_id=db_id,
                media_asset_id=media_id,
                role=ItemMediaRole.PRIMARY,
                created_at=fixed_now - timedelta(days=7),
            )
        )
        refresh_retrieval_document(session, item)

    # Optional WearLog / historical OutfitRecommendation setup for 72h exact outfit repetition tests
    for w_idx, wh in enumerate(wear_history):
        rec_id = str(uuid5(NAMESPACE_URL, f"bench-hist-rec:{run_user_id}:{w_idx}"))
        worn_time = fixed_now - timedelta(hours=float(wh.get("worn_hours_ago", 24)))
        rec = OutfitRecommendation(
            id=rec_id,
            user_id=run_user_id,
            request_id=f"hist-{w_idx}",
            user_query="Lịch sử mặc trước đó",
            context_snapshot={"occasion": "casual"},
            rank=1,
            fashion_score=0.8,
            personalization_score=0.5,
            composite_score=0.75,
            explanation_vi="Bộ đồ đã mặc trước đó.",
            rule_version="history-seed",
            created_at=worn_time - timedelta(hours=1),
        )
        session.add(rec)
        session.flush()

        for raw_iid in wh.get("item_ids", []):
            db_iid = raw_to_db[str(raw_iid)]
            wi = db_to_item[db_iid]
            wi.last_worn_at = worn_time
            wi.times_worn = (wi.times_worn or 0) + 1
            session.add(
                OutfitItem(
                    outfit_id=rec_id,
                    user_id=run_user_id,
                    wardrobe_item_id=db_iid,
                    slot_role=OutfitSlotRole(wi.category.value),
                )
            )
        session.add(
            WearLog(
                id=str(uuid5(NAMESPACE_URL, f"bench-wearlog:{run_user_id}:{w_idx}")),
                user_id=run_user_id,
                outfit_id=rec_id,
                worn_at=worn_time,
                source="confirm_worn",
            )
        )

    session.commit()
    return raw_to_db


def _serialize_slot_dict(item: OutfitItemSlot, db_to_raw: dict[str, str]) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "raw_id": db_to_raw.get(item.item_id, item.item_id),
        "slot": item.slot_role.value,
        "name": item.name,
        "sub_category": item.sub_category,
        "primary_color": item.primary_color,
        "material": item.material,
        "style": item.style,
        "fit": item.fit,
        "formality_level": item.formality_level,
        "comfort_level": item.comfort_level,
        "functional_flags": list(item.functional_flags),
    }


@dataclass(frozen=True)
class SystemConfig:
    system_id: str
    kind: str  # "random" | "multi_agent" | "single_prompt"
    enable_agent_loops: bool = True
    enable_relaxation_loop: bool | None = None
    enable_critique_loop: bool | None = None
    disable_personalization: bool = False


SYSTEM_REGISTRY: dict[str, SystemConfig] = {
    "B0": SystemConfig(system_id="B0", kind="random"),
    "B1": SystemConfig(
        system_id="B1",
        kind="multi_agent",
        enable_agent_loops=False,
    ),
    "B2": SystemConfig(system_id="B2", kind="single_prompt"),
    "M-Full": SystemConfig(
        system_id="M-Full",
        kind="multi_agent",
        enable_agent_loops=True,
        enable_relaxation_loop=True,
        enable_critique_loop=True,
        disable_personalization=False,
    ),
    "M-NoLoop1": SystemConfig(
        system_id="M-NoLoop1",
        kind="multi_agent",
        enable_agent_loops=True,
        enable_relaxation_loop=False,
        enable_critique_loop=True,
    ),
    "M-NoLoop2": SystemConfig(
        system_id="M-NoLoop2",
        kind="multi_agent",
        enable_agent_loops=True,
        enable_relaxation_loop=True,
        enable_critique_loop=False,
    ),
    "M-NoLoops": SystemConfig(
        system_id="M-NoLoops",
        kind="multi_agent",
        enable_agent_loops=False,
    ),
    "M-NoPersonalization": SystemConfig(
        system_id="M-NoPersonalization",
        kind="multi_agent",
        enable_agent_loops=True,
        enable_relaxation_loop=True,
        enable_critique_loop=True,
        disable_personalization=True,
    ),
}


def run_random_valid_baseline(
    *,
    session: Session,
    run_user_id: str,
    case: dict[str, Any],
    db_to_raw: dict[str, str],
    seed_base: int = 20261119,
) -> dict[str, Any]:
    """B0 Random Valid Baseline: uniformly picks up to 3 core-distinct valid combinations."""
    started = perf_counter()
    items = session.exec(
        select(WardrobeItem).where(
            WardrobeItem.user_id == run_user_id,
            WardrobeItem.is_active.is_(True),
            WardrobeItem.is_user_confirmed.is_(True),
            WardrobeItem.deleted_at.is_(None),
        )
    ).all()

    if not items:
        return {
            "system_id": "B0",
            "case_id": case["id"],
            "status": "error",
            "error_code": "WARDROBE_EMPTY",
            "outfits": [],
            "recommendation_ids": [],
            "relaxation_round": 0,
            "critique_round": 0,
            "active_relaxations": [],
            "conflict_notes": [],
            "agent_trace": [],
            "warnings": [],
            "context": None,
            "context_used": "none",
            "llm_calls": 0,
            "estimated_tokens": 0,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "provider_failures": [],
        }

    cat_to_slot = {
        WardrobeCategory.TOP: "tops",
        WardrobeCategory.BOTTOM: "bottoms",
        WardrobeCategory.DRESS: "dresses",
        WardrobeCategory.FOOTWEAR: "footwear",
        WardrobeCategory.OUTERWEAR: "outerwear",
        WardrobeCategory.ACCESSORY: "accessories",
    }
    pool: dict[str, list[OutfitItemSlot]] = {v: [] for v in cat_to_slot.values()}
    for it in items:
        slot = OutfitItemSlot(
            item_id=it.id,
            slot_role=OutfitSlotRole(it.category.value),
            name=format_localized_item_name(it),
            sub_category=it.sub_category,
            primary_color=it.primary_color,
            secondary_color=it.secondary_color,
            style=it.style,
            category=it.category,
            formality_level=it.formality_level,
            comfort_level=it.comfort_level,
            silhouette_level=it.silhouette_level,
            length=it.length,
            weather_suitability=list(it.weather_suitability),
            pattern=it.pattern,
            material=it.material,
            fit=it.fit,
            functional_flags=list(it.functional_flags),
        )
        pool[cat_to_slot[it.category]].append(slot)

    combos = generate_outfit_combinations(pool)
    if not combos:
        return {
            "system_id": "B0",
            "case_id": case["id"],
            "status": "error",
            "error_code": "NO_COMPLETE_OUTFIT",
            "outfits": [],
            "recommendation_ids": [],
            "relaxation_round": 0,
            "critique_round": 0,
            "active_relaxations": [],
            "conflict_notes": [],
            "agent_trace": [],
            "warnings": [],
            "context": None,
            "context_used": "none",
            "llm_calls": 0,
            "estimated_tokens": 0,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "provider_failures": [],
        }

    digest = int(hashlib.sha256(str(case["id"]).encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed_base + digest)
    shuffled = list(combos)
    rng.shuffle(shuffled)

    chosen: list[list[OutfitItemSlot]] = []
    seen_cores: set[frozenset[str]] = set()
    for combo in shuffled:
        sig = core_signature(combo)
        if sig in seen_cores:
            continue
        seen_cores.add(sig)
        chosen.append(combo)
        if len(chosen) >= 3:
            break

    outfits: list[dict[str, Any]] = []
    for idx, combo in enumerate(chosen, start=1):
        names = [f"[{s.name}]" for s in combo]
        outfits.append(
            {
                "rank": idx,
                "composite_score": None,
                "items": [_serialize_slot_dict(s, db_to_raw) for s in combo],
                "explanation_vi": f"Lựa chọn ngẫu nhiên hợp lệ gồm {', '.join(names)}.",
                "explanation_source": "random_baseline",
                "applied_preferences": [],
            }
        )

    return {
        "system_id": "B0",
        "case_id": case["id"],
        "status": "ok",
        "error_code": None,
        "outfits": outfits,
        "recommendation_ids": [],
        "relaxation_round": 0,
        "critique_round": 0,
        "active_relaxations": [],
        "conflict_notes": [],
        "agent_trace": [],
        "warnings": [],
        "context": None,
        "context_used": "none",
        "llm_calls": 0,
        "estimated_tokens": 0,
        "latency_ms": round((perf_counter() - started) * 1000, 2),
        "provider_failures": [],
    }


def run_single_prompt_gemini_baseline(
    *,
    session: Session,
    run_user_id: str,
    case: dict[str, Any],
    db_to_raw: dict[str, str],
    api_key: str,
    model: str,
    base_url: str = "https://generativelanguage.googleapis.com/v1beta",
    timeout_seconds: float = 45.0,
    http_client: httpx.Client | None = None,
    key_pool: GeminiKeyPool | None = None,
    max_retries: int = 0,
    initial_backoff_seconds: float = 1.0,
    request_delay_seconds: float = 0.0,
    thinking_level: str | None = "minimal",
    cache: JsonlResultCache | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """B2 Single-Prompt Gemini Baseline: sends wardrobe, profile & wear history in ONE LLM call."""
    started = perf_counter()
    items = session.exec(
        select(WardrobeItem).where(
            WardrobeItem.user_id == run_user_id,
            WardrobeItem.is_active.is_(True),
            WardrobeItem.is_user_confirmed.is_(True),
            WardrobeItem.deleted_at.is_(None),
        )
    ).all()

    if not items:
        return {
            "system_id": "B2",
            "case_id": case["id"],
            "status": "error",
            "error_code": "WARDROBE_EMPTY",
            "outfits": [],
            "recommendation_ids": [],
            "relaxation_round": 0,
            "critique_round": 0,
            "active_relaxations": [],
            "conflict_notes": [],
            "agent_trace": [],
            "warnings": [],
            "context": None,
            "context_used": "none",
            "llm_calls": 0,
            "estimated_tokens": 0,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "provider_failures": [],
            "llm_cache_hit": False,
        }

    # Note: Expose short readable raw IDs to LLM and map back cleanly so LLM isn't confused by UUIDs.
    raw_to_item: dict[str, WardrobeItem] = {}
    wardrobe_lines: list[str] = []
    for it in items:
        raw_id = db_to_raw.get(it.id, it.id)
        raw_to_item[raw_id] = it
        loc_name = format_localized_item_name(it)
        flags = ",".join(it.functional_flags) if it.functional_flags else "none"
        weather = ",".join(it.weather_suitability)
        wardrobe_lines.append(
            f"- id={raw_id} | name={loc_name} | category={it.category.value} | sub={it.sub_category} "
            f"| color={it.primary_color} | material={it.material} | style={it.style} | fit={it.fit} "
            f"| formality={it.formality_level}/5 | weather={weather} | flags={flags} "
            f"| recently_worn={'yes' if it.last_worn_at is not None else 'no'}"
        )

    prefs = session.get(UserPreference, run_user_id)
    pref_text = (
        f"styles={prefs.styles}, palettes={prefs.color_palettes}, priorities={prefs.priorities}, "
        f"avoid_colors={prefs.avoid_colors}, avoid_styles={prefs.avoid_styles}, fit={prefs.fit_preferences}"
        if prefs
        else "Chưa thiết lập sở thích."
    )

    prompt = (
        "Bạn là chuyên gia tư vấn phối đồ thời trang. Dưới đây là TỦ ĐỒ HIỆN CÓ, SỞ THÍCH CÁ NHÂN và CÂU HỎI của người dùng.\n"
        f"Yêu cầu người dùng: {case['query']}\n"
        f"Địa điểm (nếu có): {case.get('location') or 'không rõ'}\n"
        f"Hồ sơ sở thích: {pref_text}\n"
        "Danh sách món đồ trong tủ:\n"
        + "\n".join(wardrobe_lines)
        + "\n\nQuy tắc bắt buộc:\n"
        "1. Nếu câu hỏi quá mơ hồ thiếu dịp/hoàn cảnh (ví dụ chỉ hỏi 'Mặc gì?' hoặc chỉ nêu tên thành phố), trả status='clarification' và 1 clarification_question ngắn bằng tiếng Việt.\n"
        "2. Nếu không thể tạo bộ hoàn chỉnh thỏa ràng buộc cứng, trả status='error', error_code='NO_COMPLETE_OUTFIT'.\n"
        "3. Nếu đủ thông tin, chọn tối đa 3 bộ tốt nhất (xếp rank 1..3), mỗi bộ CHỈ gồm: (1 top + 1 bottom + 1 footwear) HOẶC (1 dress + 1 footwear), có thể thêm tối đa 1 outerwear và 1 accessory.\n"
        "4. Chỉ sử dụng các id có thật trong danh sách trên. Viết explanation_vi (2 câu tiếng Việt) nhắc đúng [Tên món] trong ngoặc vuông và không bịa thêm món ngoài bộ đồ.\n"
        'Chỉ trả về JSON hợp lệ theo mẫu: {"status": "ok"|"clarification"|"error", "error_code": null|string, "clarification_question": null|string, "outfits": [{"rank": 1, "item_ids": ["..."], "explanation_vi": "..."}]}.'
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": build_gemini_generation_config(model, thinking_level=thinking_level),
    }
    est_tokens = len(prompt) // 4

    llm_cache_hit = False
    raw_text: str | None = None
    cache_key: str | None = None
    if cache is not None:
        key_payload = json.dumps(
            {
                "kind": "single_prompt_b2",
                "model": model,
                "thinking_level": thinking_level,
                "prompt": prompt,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cache_key = hashlib.sha256(key_payload.encode("utf-8")).hexdigest()
        cached = cache.get(cache_key)
        if cached is not None and isinstance(cached.get("raw_text"), str):
            raw_text = str(cached["raw_text"])
            llm_cache_hit = True

    effective_pool = key_pool or GeminiKeyPool([SecretStr(api_key or "empty-placeholder")])

    try:
        if raw_text is None:
            resp_json = post_gemini_generate_content(
                base_url=base_url,
                model=model,
                payload=payload,
                timeout=timeout_seconds,
                key_pool=effective_pool,
                http_client=http_client,
                max_retries=max_retries,
                initial_backoff_seconds=initial_backoff_seconds,
                request_delay_seconds=request_delay_seconds,
                sleep_fn=sleep_fn,
            )
            raw_text = _extract_json_from_gemini_response(resp_json)
            parsed = json.loads(raw_text)
            if cache is not None and cache_key is not None:
                cache.put(cache_key, {"raw_text": raw_text})
        else:
            parsed = json.loads(raw_text)
        est_tokens += len(raw_text) // 4
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        return {
            "system_id": "B2",
            "case_id": case["id"],
            "status": "error",
            "error_code": "PROVIDER_ERROR",
            "outfits": [],
            "recommendation_ids": [],
            "relaxation_round": 0,
            "critique_round": 0,
            "active_relaxations": [],
            "conflict_notes": [],
            "agent_trace": [],
            "warnings": [],
            "context": None,
            "context_used": "none",
            "llm_calls": 1,
            "estimated_tokens": est_tokens,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "provider_failures": [{"stage": "single_prompt", "error_type": type(exc).__name__, "http_status": status_code}],
            "llm_cache_hit": llm_cache_hit,
        }

    status = str(parsed.get("status", "ok")).lower()
    if status == "clarification":
        return {
            "system_id": "B2",
            "case_id": case["id"],
            "status": "clarification",
            "error_code": None,
            "outfits": [],
            "recommendation_ids": [],
            "relaxation_round": 0,
            "critique_round": 0,
            "active_relaxations": [],
            "conflict_notes": [],
            "agent_trace": [],
            "warnings": [],
            "context": {"needs_clarification": True},
            "context_used": "single_prompt_llm",
            "llm_calls": 1,
            "estimated_tokens": est_tokens,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "provider_failures": [],
            "llm_cache_hit": llm_cache_hit,
        }

    raw_outfits = parsed.get("outfits") or []
    if status == "error" or not raw_outfits:
        return {
            "system_id": "B2",
            "case_id": case["id"],
            "status": "error",
            "error_code": str(parsed.get("error_code") or "NO_COMPLETE_OUTFIT"),
            "outfits": [],
            "recommendation_ids": [],
            "relaxation_round": 0,
            "critique_round": 0,
            "active_relaxations": [],
            "conflict_notes": [],
            "agent_trace": [],
            "warnings": [],
            "context": {"needs_clarification": False},
            "context_used": "single_prompt_llm",
            "llm_calls": 1,
            "estimated_tokens": est_tokens,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "provider_failures": [],
            "llm_cache_hit": llm_cache_hit,
        }

    normalized_outfits: list[dict[str, Any]] = []
    for idx, entry in enumerate(raw_outfits[:3], start=1):
        entry_items: list[dict[str, Any]] = []
        for raw_iid in entry.get("item_ids", []):
            raw_str = str(raw_iid).strip()
            db_item = raw_to_item.get(raw_str)
            if db_item is None:
                # Preserve fabricated ID verbatim so Layer A measures hallucination rate accurately
                entry_items.append(
                    {
                        "item_id": raw_str,
                        "raw_id": raw_str,
                        "slot": "unknown",
                        "name": f"[UNKNOWN:{raw_str}]",
                        "missing_in_db": True,
                    }
                )
            else:
                entry_items.append(
                    {
                        "item_id": db_item.id,
                        "raw_id": raw_str,
                        "slot": db_item.category.value,
                        "name": format_localized_item_name(db_item),
                        "sub_category": db_item.sub_category,
                        "primary_color": db_item.primary_color,
                        "material": db_item.material,
                        "style": db_item.style,
                        "fit": db_item.fit,
                        "formality_level": db_item.formality_level,
                        "comfort_level": db_item.comfort_level,
                        "functional_flags": list(db_item.functional_flags),
                    }
                )
        normalized_outfits.append(
            {
                "rank": int(entry.get("rank") or idx),
                "composite_score": None,
                "items": entry_items,
                "explanation_vi": str(entry.get("explanation_vi", "")).strip(),
                "explanation_source": "single_prompt_llm",
                "applied_preferences": [],
            }
        )

    return {
        "system_id": "B2",
        "case_id": case["id"],
        "status": "ok",
        "error_code": None,
        "outfits": normalized_outfits,
        "recommendation_ids": [],
        "relaxation_round": 0,
        "critique_round": 0,
        "active_relaxations": [],
        "conflict_notes": [],
        "agent_trace": [],
        "warnings": [],
        "context": {"needs_clarification": False},
        "context_used": "single_prompt_llm",
        "llm_calls": 1,
        "estimated_tokens": est_tokens,
        "latency_ms": round((perf_counter() - started) * 1000, 2),
        "provider_failures": [],
        "llm_cache_hit": llm_cache_hit,
    }


def run_multi_agent_system(
    *,
    session: Session,
    config: SystemConfig,
    run_user_id: str,
    request_id: str,
    case: dict[str, Any],
    db_to_raw: dict[str, str],
    fixed_now: datetime,
    llm_probe: TelemetryLLMProbe | None = None,
    weather_provider: Any = None,
) -> dict[str, Any]:
    """Execute execute_stylist_recommendation under one SystemConfig and collect full telemetry."""
    if llm_probe is not None:
        llm_probe.reset_case_counters()

    initial_state: StylistGraphState = {
        "request_id": request_id,
        "user_id": run_user_id,
        "user_query": str(case["query"]),
        "location": case.get("location"),
        "reference_time": fixed_now,
        "enable_agent_loops": config.enable_agent_loops,
        "enable_relaxation_loop": config.enable_relaxation_loop,
        "enable_critique_loop": config.enable_critique_loop,
        "enable_llm_explanations": llm_probe is not None,
        "disable_personalization": config.disable_personalization,
    }

    started = perf_counter()
    final_state = execute_stylist_recommendation(
        initial_state,
        session=session,
        clock=lambda: fixed_now,
        llm_provider=llm_probe,
        weather_provider=weather_provider,
    )
    elapsed_ms = round((perf_counter() - started) * 1000, 2)

    errors = list(final_state.get("errors", []))
    warnings = list(final_state.get("warnings", []))
    ctx: StylistContext | None = final_state.get("context")
    active_relaxations = list(final_state.get("active_relaxations", []))
    conflict_notes = list(final_state.get("conflict_notes", []))

    if errors:
        status = "error"
        error_code = str(errors[0])
    elif ctx is not None and ctx.needs_clarification:
        status = "clarification"
        error_code = None
    else:
        status = "ok"
        error_code = None

    # Identify exact explanation source per outfit (detect silent LLM fallback)
    outfits_out: list[dict[str, Any]] = []
    for outfit in final_state.get("ranked_outfits", []):
        if llm_probe is None:
            exp_src = "deterministic_offline"
        elif ctx is not None:
            det_text = generate_grounded_explanation_vi(
                outfit,
                ctx,
                active_relaxations=active_relaxations,
                conflict_notes=conflict_notes,
                llm_provider=None,
            )
            if outfit.explanation_vi.strip() == det_text.strip():
                exp_src = "deterministic_fallback"
            elif llm_probe.explanation_batch_calls > 0:
                exp_src = "gemini_batch"
            else:
                exp_src = "gemini_single"
        else:
            exp_src = "deterministic_fallback"

        outfits_out.append(
            {
                "rank": outfit.rank,
                "composite_score": outfit.composite_score,
                "fashion_score": outfit.fashion_score,
                "personalization_score": outfit.personalization_score,
                "items": [_serialize_slot_dict(s, db_to_raw) for s in outfit.items],
                "explanation_vi": outfit.explanation_vi,
                "explanation_source": exp_src,
                "applied_preferences": list(outfit.applied_preferences),
            }
        )

    probe_stats = (
        llm_probe.snapshot()
        if llm_probe is not None
        else {
            "llm_calls": 0,
            "context_calls": 0,
            "explanation_batch_calls": 0,
            "explanation_single_calls": 0,
            "estimated_tokens": 0,
            "failures": [],
        }
    )

    if llm_probe is None:
        context_used = "rules"
    elif CONTEXT_FALLBACK_WARNING in warnings:
        context_used = "rules_fallback"
    else:
        context_used = "gemini"

    return {
        "system_id": config.system_id,
        "case_id": case["id"],
        "status": status,
        "error_code": error_code,
        "outfits": outfits_out,
        "recommendation_ids": list(final_state.get("recommendation_ids", [])),
        "relaxation_round": int(final_state.get("relaxation_round", 0)),
        "critique_round": int(final_state.get("critique_round", 0)),
        "active_relaxations": [
            s.model_dump(mode="json") if hasattr(s, "model_dump") else dict(s)
            for s in active_relaxations
        ],
        "conflict_notes": [
            c.model_dump(mode="json") if hasattr(c, "model_dump") else dict(c)
            for c in conflict_notes
        ],
        "agent_trace": [
            t.model_dump(mode="json") if hasattr(t, "model_dump") else dict(t)
            for t in final_state.get("agent_trace", [])
        ],
        "warnings": warnings,
        "context": ctx.model_dump(mode="json") if ctx is not None else None,
        "context_used": context_used,
        "llm_calls": probe_stats["llm_calls"],
        "estimated_tokens": probe_stats["estimated_tokens"],
        "latency_ms": elapsed_ms,
        "provider_failures": probe_stats["failures"],
    }
