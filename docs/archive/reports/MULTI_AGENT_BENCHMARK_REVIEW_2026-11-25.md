# Review of the live multi-agent benchmark (PR #21) — 2026-11-25

PR #21 (`feat/live-multi-agent-evaluation`, merged as `58d5b41`) added the two-layer live
benchmark, a cross-family judge (`openai/gpt-6.1-terra` through OpenRouter), a blind human
calibration with three raters, and changes to the context agent, coordinator, scoring
weights and Gemini context provider. The owner merged it with two known defects so that
they could be fixed in a follow-up branch (`fix/context-provider-followups`) while the
author was unavailable. This report records the review findings, the fixes, and the
caveats that the thesis MUST state when it uses the benchmark numbers. The benchmark
reports themselves (`LIVE_MULTI_AGENT_BENCHMARK_2026-11-23.md`, `..._HOLDOUT_...`,
`HUMAN_VS_JUDGE_CALIBRATION_2026-11-25.md`) are left unchanged.

## 1. Defects fixed after the merge

| ID | Defect | Effect | Fix |
| :--- | :--- | :--- | :--- |
| F-1 | `_coerce_formality_value` read every float in `[0, 1]` as a 0–1 scale, so `1.0` or `"1.0"` became formality 5 | An LLM range `[1.0, 2.0]` (casual) became `[2, 4]` | A pair uses the 0–1 scale only when both values lie in `[0, 1]` and one is fractional; integral floats are levels. Tests in `test_context_agent.py` fail on the previous code (3 of 11 cases) |
| F-2 | The application context provider retried up to `max(2, keys)` times with exponential backoff and slept up to 30 s on HTTP 429 | A chat request could wait about 48 s with one key before the rule fallback | `get_context_llm_provider` makes one attempt (`max_retries=0`); the benchmark runner keeps its own retrying provider. `test_context_provider_chat_policy.py` fails on the previous code (4 of 4) |

F-1 did not affect the 2026-11-23 live run. The reports do not store raw LLM context
payloads, so the author checked the git-ignored response cache
(`data/eval_cache/llm_cache.jsonl`, 51 unique context records for 56 cases) on 2026-11-25:
32 cases returned integer lists, 3 integer `min`/`max` objects, 15 label strings, 1 null,
and 1 (`r25`, dev) the fraction pair `[0.2, 0.4]`. No case returned an integral float such
as `1.0`. The fixed code maps every one of these forms to the same range as before
(`[0.2, 0.4]` still becomes `[2, 3]`), so the benchmark numbers stand. F-2 does not affect
benchmark numbers either, because the runner builds its own provider.

Also done: the coordinator's copy of the Vietnamese color map now uses
`wardrobe_agent.COLOR_VI_MAP` (the two copies were identical).

## 2. Decisions that remain with the owner

- **Scoring weights.** PR #21 changed the comfort profile from weather/comfort 0.55,
  functional 0.20, personal 0.00 to 0.45, 0.15, 0.15, and the active profile from
  weather/comfort 0.45, personal 0.00 to 0.35, 0.10 (`FASHION_KNOWLEDGE_BASE.md`,
  `context_scoring.py`). The profiles came from the advisor's feedback, so the change needs
  the advisor's agreement. Every live benchmark number was measured with the new weights;
  reverting them requires a new live run.
  An offline comparison on 2026-11-25 measured what the change buys (section 2.1).
- **Gemini key rotation.** The benchmark used a pool of seven Gemini keys. Rotating several
  free-tier keys to exceed one project's quota may conflict with the provider's terms. The
  deployed application should use one paid key.

### 2.1 Offline comparison of the weight profiles

`backend/scripts/compare_weight_profiles_offline.py` runs the offline benchmark
(`multi-agent-bench-v3`, 56 representative and 12 stress cases; no live LLM, weather or
judge) once with the current profiles and once with the pre-PR #21 comfort and active
profiles, which mirror the advisor's travel example (comfort + weather 55%, function 20%,
aesthetic 15%, formality 10%, personal 0%). Summary:
`WEIGHT_PROFILE_COMPARISON_2026-11-25.json`.

| System | Profile differentiation (pre-PR #21 → current) | Top-3 core diversity | Every other metric |
| :--- | :--- | :--- | :--- |
| B1 | 2/5 → 5/5 | 0.739 → 0.746 | unchanged |
| M-Full | 2/5 → 5/5 | 0.732 → 0.736 | unchanged |
| M-NoLoop1 | 2/5 → 5/5 | 0.739 → 0.746 | unchanged |
| M-NoLoop2 | 2/5 → 5/5 | 0.732 → 0.736 | unchanged |
| M-NoPersonalization | 0/5 → 0/5 | 0.738 → 0.752 | unchanged |
| B0 | — | — | unchanged |

"Every other metric" is Layer A, functional pass (dev and holdout), context accuracy,
contrastive pairs, recent-wear avoidance and stress pass; for M-Full they stay at 56/56,
48/56, 3/3, 4/4 and 12/12. With personal weight 0, two different preference profiles
received different recommendations in only 2 of the 5 profile-differentiation cases; with
the current weights in all 5, while no constraint, structure or functional check got worse.
M-NoPersonalization stays at 0/5 under both profiles, which confirms that the gain comes
from the personalization weight. The comparison is offline only: the judged quality of the
live run (nDCG@3, pairwise wins) was not measured under the old weights.

## 3. Caveats for reporting the judge calibration

1. **The rubric was tuned on the calibration set.** `judge-rubric-v3` and the weakest-link
   cap were added after a first calibration on the same 20 pointwise samples. The reported
   85% pointwise accuracy is therefore an in-sample figure.
2. **The stratified design explains most of the human–judge correlation.** The 20 samples
   are built as 8 bad, 4 mediocre and 8 good outfits. Recomputed from
   `HUMAN_VS_JUDGE_CALIBRATION_2026-11-25.json`:

   | Statistic | Spearman rho |
   | :--- | :--- |
   | Human mean vs judge, all 20 samples (reported) | 0.895 |
   | Design tier label alone vs human mean | 0.909 |
   | Design tier label alone vs judge | 0.921 |
   | Human vs judge after removing each tier's mean | 0.403 |
   | Within the bad tier (8) / good tier (8) / mediocre tier (4) | 0.11 / 0.44 / 0.95 |

   The judge separates bad from good outfits as humans do, but its ranking within a
   quality tier agrees only weakly with the raters. The thesis SHOULD report the
   within-tier figure next to the overall one. On the "unacceptable" threshold
   (score <= 2), humans flagged 6 samples, the judge 5, and both agreed on 4.
3. **Rater description.** The report states three anonymous blind raters (R1–R3) but not
   their background or independence from the project. The rating tool hides tier labels
   and shuffles samples (`backend/scripts/judge_calibration_human_review.py`), so the
   procedure is blind. The thesis needs one sentence on who the raters are.
4. **Dataset history.** `data/fixtures/multi_agent_benchmark_v1.json` now holds
   `multi-agent-bench-v3` (56 cases); the file name no longer identifies the version.
   The v3 cases were committed on 2026-11-22 (`bf0330b`), before the application fixes of
   2026-11-23, and the holdout split was not edited afterwards (16 new cases, 19 existing
   cases changed, of which 3 holdout; no case changed split).

## 4. Reading the main result

On the judge's quality ranking, the single-prompt Gemini baseline B2 beats the multi-agent
system (nDCG@3 0.912 vs 0.742; M-Full loses 36 of 49 bidirectional pairs). M-Full's
advantages are on the deterministic layer and on cost: 56/56 Layer A against 54/56,
functional pass 52/56 against 49/56 with overlapping 95% intervals, and about 55% fewer
estimated tokens. The thesis SHOULD present the multi-agent design as trading some judged
style quality for grounding, hard-constraint compliance and cost, not as better advice
overall. B2 also sees the whole 27–30 item wardrobe in one prompt, which does not scale to
large wardrobes; that argument is a design claim, not a measured result.

## 5. Verification

```powershell
cd backend
python -m pytest tests/unit/test_context_agent.py tests/unit/test_context_provider_chat_policy.py tests/evaluation/test_multi_agent_benchmark.py -q
python -m pytest -q
```
