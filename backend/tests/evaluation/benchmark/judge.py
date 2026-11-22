"""Cross-Family LLM-as-a-Judge client, bidirectional comparison, calibration, and JSONL cache."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Literal

import httpx

from app.services.gemini_provider import _extract_json_from_gemini_response
from tests.evaluation.benchmark.metrics import compute_spearman_rho


JUDGE_PROMPT_VERSION = "judge-rubric-v1"


def is_same_family_gemini(model: str) -> bool:
    return "gemini" in (model or "").lower()


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"Judge response did not contain a valid JSON object: {text[:160]}")


def _clamp_score(value: Any, default: float = 3.0) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(1.0, min(5.0, num)), 2)


class JsonlResultCache:
    """Append-only JSONL disk cache keyed by stable SHA-256 content hashes."""

    def __init__(self, cache_path: Path | None) -> None:
        self.cache_path = cache_path
        self._records: dict[str, dict[str, Any]] = {}
        if self.cache_path is not None and self.cache_path.is_file():
            for line in self.cache_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and "key" in obj and "value" in obj:
                        self._records[str(obj["key"])] = obj["value"]
                except json.JSONDecodeError:
                    continue

    def get(self, key: str) -> dict[str, Any] | None:
        return self._records.get(key)

    def put(self, key: str, value: dict[str, Any]) -> None:
        self._records[key] = value
        if self.cache_path is not None:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")


@dataclass
class JudgeConfig:
    provider: Literal["openai_compatible", "anthropic", "gemini"] = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4.1-mini"
    timeout_seconds: float = 25.0

    @classmethod
    def from_env(
        cls,
        *,
        provider: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_key_env: str = "BENCH_JUDGE_API_KEY",
    ) -> JudgeConfig:
        eff_provider = (
            provider
            or os.environ.get("BENCH_JUDGE_PROVIDER")
            or "openai_compatible"
        ).strip().lower()
        provider_defaults: dict[str, tuple[str, str, str]] = {
            "openai_compatible": ("https://api.openai.com/v1", "gpt-4.1-mini", "OPENAI_API_KEY"),
            "anthropic": ("https://api.anthropic.com/v1", "claude-sonnet-4-20250514", "ANTHROPIC_API_KEY"),
            "gemini": ("https://generativelanguage.googleapis.com/v1beta", "gemini-2.5-flash", "GEMINI_API_KEY"),
        }
        if eff_provider not in provider_defaults:
            raise ValueError(f"Unsupported judge provider: '{eff_provider}'")
        default_base, default_model, provider_key_env = provider_defaults[eff_provider]
        eff_base = (
            base_url
            or os.environ.get("BENCH_JUDGE_BASE_URL")
            or default_base
        ).strip().rstrip("/")
        eff_model = (
            model
            or os.environ.get("BENCH_JUDGE_MODEL")
            or default_model
        ).strip()
        eff_key = (
            os.environ.get(api_key_env)
            or os.environ.get("BENCH_JUDGE_API_KEY")
            or os.environ.get(provider_key_env)
            or ""
        ).strip()
        timeout = float(os.environ.get("BENCH_JUDGE_TIMEOUT_SECONDS", "25"))
        return cls(
            provider=eff_provider,  # type: ignore[arg-type]
            base_url=eff_base,
            api_key=eff_key,
            model=eff_model,
            timeout_seconds=timeout,
        )


def _format_items_for_judge(items: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for it in items:
        slot = it.get("slot") or it.get("slot_role") or it.get("category") or "item"
        name = it.get("name") or it.get("sub_category") or "unknown"
        color = it.get("primary_color", "unknown")
        material = it.get("material", "unknown")
        style = it.get("style", "unknown")
        fit = it.get("fit", "unknown")
        formality = it.get("formality_level", "?")
        flags = ",".join(it.get("functional_flags", []) or []) or "none"
        lines.append(
            f"  - [{slot}] {name} (loại={it.get('sub_category', '')}, màu={color}, "
            f"chất_liệu={material}, phong_cách={style}, dáng={fit}, trang_trọng={formality}/5, cờ={flags})"
        )
    return "\n".join(lines) if lines else "  - (không có món nào)"


class CrossFamilyJudgeClient:
    """Blind LLM-as-a-Judge adapter with cross-family bias warnings, bidirectional comparison, and disk cache."""

    def __init__(
        self,
        config: JudgeConfig,
        *,
        cache: JsonlResultCache | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.cache = cache or JsonlResultCache(None)
        self._client = http_client
        self.same_family_bias = is_same_family_gemini(config.model) or config.provider == "gemini"
        self.api_calls = 0
        self.cache_hits = 0

    def _post_json_prompt(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        self.api_calls += 1
        client_cm = (
            httpx.Client(timeout=self.config.timeout_seconds)
            if self._client is None
            else None
        )
        client = self._client or client_cm
        assert client is not None
        try:
            if self.config.provider == "openai_compatible":
                url = f"{self.config.base_url}/chat/completions"
                headers = {"Content-Type": "application/json"}
                if self.config.api_key:
                    headers["Authorization"] = f"Bearer {self.config.api_key}"
                payload = {
                    "model": self.config.model,
                    "temperature": 0.0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                resp = client.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
                if resp.status_code == 400 and "response_format" in payload:
                    # Compatibility retry for local OpenAI-compatible servers that reject response_format
                    payload_no_rf = {k: v for k, v in payload.items() if k != "response_format"}
                    resp = client.post(url, headers=headers, json=payload_no_rf, timeout=self.config.timeout_seconds)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return _extract_json_object(str(content))

            if self.config.provider == "anthropic":
                url = f"{self.config.base_url}/messages"
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self.config.api_key,
                    "anthropic-version": "2023-06-01",
                }
                payload = {
                    "model": self.config.model,
                    "max_tokens": 512,
                    "temperature": 0.0,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                }
                resp = client.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
                resp.raise_for_status()
                blocks = resp.json().get("content", [])
                text = " ".join(b.get("text", "") for b in blocks if isinstance(b, dict))
                return _extract_json_object(text)

            # Explicit gemini fallback (will carry SAME_FAMILY_JUDGE_BIAS flag)
            url = f"{self.config.base_url}/models/{self.config.model}:generateContent"
            headers = {"x-goog-api-key": self.config.api_key}
            payload = {
                "contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                "generationConfig": {"response_mime_type": "application/json", "temperature": 0.0},
            }
            resp = client.post(url, headers=headers, json=payload, timeout=self.config.timeout_seconds)
            resp.raise_for_status()
            return json.loads(_extract_json_from_gemini_response(resp.json()))
        finally:
            if client_cm is not None:
                client_cm.close()

    def score_outfit_pointwise(
        self,
        *,
        query: str,
        weather_condition: str,
        profile_summary: str,
        items: list[dict[str, Any]],
        explanation_vi: str,
    ) -> dict[str, Any]:
        sig_items = sorted(str(it.get("raw_id") or it.get("item_id") or it.get("name")) for it in items)
        key_payload = json.dumps(
            {
                "kind": "pointwise",
                "ver": JUDGE_PROMPT_VERSION,
                "model": self.config.model,
                "q": query,
                "w": weather_condition,
                "p": profile_summary,
                "items": sig_items,
                "exp": explanation_vi,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cache_key = hashlib.sha256(key_payload.encode("utf-8")).hexdigest()
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            return cached

        system_prompt = (
            "Bạn là giám khảo chuyên môn thời trang độc lập. Hãy chấm điểm một gợi ý phối đồ dựa trên dữ kiện khách quan "
            "theo thang 1 đến 5 (1=Không chấp nhận được/sai nghiêm trọng, 2=Kém/lệch hoàn cảnh hoặc thời tiết nặng, "
            "3=Chấp nhận được nhưng chưa tối ưu, 4=Tốt/gọn gàng hợp lý, 5=Rất tốt/mặc ngay không cần chỉnh). "
            "Không được thiên vị câu văn hoa mỹ nếu món đồ thực tế sai hoàn cảnh, sai thời tiết, hoặc lời giải thích bịa món đồ. "
            "Chỉ trả về JSON."
        )
        user_prompt = (
            f"Yêu cầu người dùng: {query}\n"
            f"Thời tiết/bối cảnh ghi nhận: {weather_condition or 'không rõ'}\n"
            f"Hồ sơ sở thích: {profile_summary or 'không có'}\n"
            f"Các món đồ trong bộ:\n{_format_items_for_judge(items)}\n"
            f"Lời giải thích đi kèm: {explanation_vi}\n\n"
            "Hãy chấm điểm số nguyên hoặc thập phân từ 1.0 đến 5.0 cho 4 tiêu chí:\n"
            "1. occasion_formality (mức độ hợp hoàn cảnh & độ trang trọng)\n"
            "2. weather_comfort_function (độ hợp thời tiết, thoải mái, an toàn vận động/chống mưa)\n"
            "3. aesthetic_harmony (hài hòa màu sắc, tỷ lệ phom dáng, phong cách)\n"
            "4. explanation_usefulness (lời giải thích trung thực với các món thực tế, rõ ràng, hữu ích)\n"
            'Trả về đúng JSON: {"occasion_formality": number, "weather_comfort_function": number, '
            '"aesthetic_harmony": number, "explanation_usefulness": number, "rationale_vi": "..."}'
        )

        parsed = self._post_json_prompt(system_prompt, user_prompt)
        occ = _clamp_score(parsed.get("occasion_formality"))
        wea = _clamp_score(parsed.get("weather_comfort_function"))
        aes = _clamp_score(parsed.get("aesthetic_harmony"))
        exp = _clamp_score(parsed.get("explanation_usefulness"))
        fashion_score = round((occ + wea + aes) / 3.0, 4)

        result = {
            "occasion_formality": occ,
            "weather_comfort_function": wea,
            "aesthetic_harmony": aes,
            "explanation_usefulness": exp,
            "fashion_quality_score": fashion_score,
            "rationale_vi": str(parsed.get("rationale_vi", "")).strip(),
        }
        self.cache.put(cache_key, result)
        return result

    def _compare_single_direction(
        self,
        *,
        query: str,
        weather_condition: str,
        profile_summary: str,
        opt1_items: list[dict[str, Any]],
        opt1_exp: str,
        opt2_items: list[dict[str, Any]],
        opt2_exp: str,
        order_tag: str,
    ) -> str:
        key_payload = json.dumps(
            {
                "kind": "pairwise_dir",
                "ver": JUDGE_PROMPT_VERSION,
                "model": self.config.model,
                "order": order_tag,
                "q": query,
                "w": weather_condition,
                "p": profile_summary,
                "o1": sorted(str(i.get("raw_id") or i.get("item_id") or i.get("name")) for i in opt1_items),
                "e1": opt1_exp,
                "o2": sorted(str(i.get("raw_id") or i.get("item_id") or i.get("name")) for i in opt2_items),
                "e2": opt2_exp,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        cache_key = hashlib.sha256(key_payload.encode("utf-8")).hexdigest()
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.cache_hits += 1
            return str(cached.get("winner", "tie"))

        system_prompt = (
            "Bạn là giám khảo thời trang độc lập. Hãy so sánh hai bộ trang phục ẩn danh cho cùng một yêu cầu. "
            "Ưu tiên: (1) đúng ràng buộc & an toàn thời tiết/hoàn cảnh, (2) hài hòa màu sắc/tỷ lệ/phong cách, "
            "(3) lời giải thích trung thực không bịa món đồ. Chỉ trả về JSON."
        )
        user_prompt = (
            f"Yêu cầu người dùng: {query}\n"
            f"Thời tiết: {weather_condition or 'không rõ'} | Sở thích: {profile_summary or 'không có'}\n\n"
            f"--- Phương án 1 ---\n{_format_items_for_judge(opt1_items)}\nGiải thích: {opt1_exp}\n\n"
            f"--- Phương án 2 ---\n{_format_items_for_judge(opt2_items)}\nGiải thích: {opt2_exp}\n\n"
            'Chọn phương án tốt hơn ("1", "2", hoặc "tie"). Trả về JSON: {"winner": "1"|"2"|"tie", "reason_vi": "..."}'
        )
        parsed = self._post_json_prompt(system_prompt, user_prompt)
        raw_w = str(parsed.get("winner", "tie")).strip().lower()
        winner = raw_w if raw_w in {"1", "2", "tie"} else "tie"
        self.cache.put(cache_key, {"winner": winner, "reason_vi": str(parsed.get("reason_vi", "")).strip()})
        return winner

    def compare_pair_bidirectional(
        self,
        *,
        query: str,
        weather_condition: str,
        profile_summary: str,
        a_items: list[dict[str, Any]],
        a_exp: str,
        b_items: list[dict[str, Any]],
        b_exp: str,
    ) -> dict[str, Any]:
        """Run both (A, B) and (B, A) to cancel position bias and measure consistency."""
        sig_a = sorted(str(i.get("raw_id") or i.get("item_id") or i.get("name")) for i in a_items)
        sig_b = sorted(str(i.get("raw_id") or i.get("item_id") or i.get("name")) for i in b_items)
        if sig_a == sig_b and a_exp.strip() == b_exp.strip():
            return {"winner": "tie", "consistent": True, "forward": "tie", "reverse": "tie"}

        w_fwd = self._compare_single_direction(
            query=query,
            weather_condition=weather_condition,
            profile_summary=profile_summary,
            opt1_items=a_items,
            opt1_exp=a_exp,
            opt2_items=b_items,
            opt2_exp=b_exp,
            order_tag="fwd",
        )
        w_rev = self._compare_single_direction(
            query=query,
            weather_condition=weather_condition,
            profile_summary=profile_summary,
            opt1_items=b_items,
            opt1_exp=b_exp,
            opt2_items=a_items,
            opt2_exp=a_exp,
            order_tag="rev",
        )

        # In reverse direction, Option 1 = B and Option 2 = A
        if w_fwd == "1" and w_rev == "2":
            return {"winner": "A", "consistent": True, "forward": w_fwd, "reverse": w_rev}
        if w_fwd == "2" and w_rev == "1":
            return {"winner": "B", "consistent": True, "forward": w_fwd, "reverse": w_rev}
        if w_fwd == "tie" and w_rev == "tie":
            return {"winner": "tie", "consistent": True, "forward": w_fwd, "reverse": w_rev}
        return {"winner": "tie", "consistent": False, "forward": w_fwd, "reverse": w_rev}


def run_judge_calibration(
    judge: CrossFamilyJudgeClient,
    calibration_data: dict[str, Any],
) -> dict[str, Any]:
    """Run pointwise + bidirectional pairwise calibration over judge_calibration_v1.json."""
    samples_by_id: dict[str, dict[str, Any]] = {}
    pointwise_hits = 0
    pointwise_details: list[dict[str, Any]] = []
    human_scores: list[float] = []
    judge_scores_for_human: list[float] = []

    for sample in calibration_data.get("pointwise_samples", []):
        sid = str(sample["id"])
        samples_by_id[sid] = sample
        scored = judge.score_outfit_pointwise(
            query=str(sample["query"]),
            weather_condition=str(sample.get("weather_condition", "")),
            profile_summary=str(sample.get("profile_summary", "")),
            items=list(sample["items"]),
            explanation_vi=str(sample["explanation_vi"]),
        )
        f_score = float(scored["fashion_quality_score"])
        label = str(sample["label"])
        if label == "good":
            passed = f_score >= 3.5
        elif label == "mediocre":
            passed = 2.5 <= f_score <= 3.75
        else:
            passed = f_score <= 2.5
        if passed:
            pointwise_hits += 1
        if sample.get("human_score") is not None:
            human_scores.append(float(sample["human_score"]))
            judge_scores_for_human.append(f_score)
        pointwise_details.append(
            {
                "id": sid,
                "label": label,
                "fashion_quality_score": f_score,
                "explanation_usefulness": scored["explanation_usefulness"],
                "passed": passed,
            }
        )

    pairwise_hits = 0
    consistent_pairs = 0
    pairwise_list = calibration_data.get("pairwise_samples", [])
    for pair in pairwise_list:
        good_s = samples_by_id[str(pair["good_id"])]
        bad_s = samples_by_id[str(pair["bad_id"])]
        comp = judge.compare_pair_bidirectional(
            query=str(pair.get("query") or good_s["query"]),
            weather_condition=str(good_s.get("weather_condition", "")),
            profile_summary=str(good_s.get("profile_summary", "")),
            a_items=list(good_s["items"]),
            a_exp=str(good_s["explanation_vi"]),
            b_items=list(bad_s["items"]),
            b_exp=str(bad_s["explanation_vi"]),
        )
        if comp["consistent"]:
            consistent_pairs += 1
        if comp["winner"] == "A":
            pairwise_hits += 1

    n_pw = len(pointwise_details)
    n_pair = len(pairwise_list)
    return {
        "dataset_version": calibration_data.get("dataset_version"),
        "judge_model": judge.config.model,
        "judge_provider": judge.config.provider,
        "same_family_judge_bias": judge.same_family_bias,
        "pointwise_accuracy": round(pointwise_hits / n_pw, 4) if n_pw else 0.0,
        "pointwise_hits": f"{pointwise_hits}/{n_pw}",
        "pairwise_accuracy": round(pairwise_hits / n_pair, 4) if n_pair else 0.0,
        "pairwise_hits": f"{pairwise_hits}/{n_pair}",
        "position_consistency_rate": round(consistent_pairs / n_pair, 4) if n_pair else 0.0,
        "human_vs_judge_spearman": compute_spearman_rho(human_scores, judge_scores_for_human),
        "details": pointwise_details,
    }
