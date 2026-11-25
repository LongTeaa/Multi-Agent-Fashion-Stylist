# Live chat latency — 2026-11-25

Thesis criterion 6.1 "Tốc độ phản hồi" needs the time from sending a styling request to
receiving recommendations with the live providers. The earlier figures do not measure it:
the MVP acceptance p95 of 0.41 s (2026-09-17) used fake providers, and the live
multi-agent benchmark's 45 ms p50 for M-Full (`LIVE_MULTI_AGENT_BENCHMARK_2026-11-23.md`)
replayed 163 cached Gemini answers. This report measures the real path once, and records
the provider-timeout defect the measurement exposed.

## 1. Method

- **Runner.** `backend/scripts/measure_live_chat_latency.py` sends benchmark queries
  (`multi_agent_benchmark_v1.json`, representative cases with expected status `ok`, in id
  order) to `POST /api/v1/stylist/chat` in process (FastAPI TestClient) against a
  temporary copy of `data/fashion_stylist.db`, as the two confirmed demo users. Times are
  server side: no browser, LAN or VPS hop.
- **Providers.** Context and explanations `gemini-3.6-flash` (`CONTEXT_TIMEOUT_SECONDS=15`),
  weather Open-Meteo (`WEATHER_TIMEOUT_SECONDS=5`), no response cache. Each provider call
  is wrapped to record its duration and outcome; the remainder is local work (retrieval,
  scoring, both feedback loops, persistence).
- **Configurations.** LLM explanations off (the default, `ENABLE_LLM_EXPLANATIONS=false`,
  one Gemini call per request) and on (the benchmark configuration, a second batched
  explanation call). One unrecorded warm-up request per configuration.
- **Runs.**
  - *Main run*: 30 queries × 2 repeats × 2 configurations = 120 requests, before the fix
    in section 3. Queries alternated between the two users regardless of the benchmark
    wardrobe, so three garment-specific queries (r14, r15, r17) reached the wrong
    wardrobe and correctly returned HTTP 422 `NO_COMPLETE_OUTFIT` (6 requests per
    configuration). They are excluded below, leaving 54 per configuration.
  - *Confirmation run*: 12 queries × 1 repeat, explanations on, after the fix, each query
    sent to the user of its benchmark wardrobe, with error causes recorded.

## 2. Results

### 2.1 Main run (54 successful requests per configuration)

| Configuration | p50 | p90 | p95 | Max | Share in Gemini | Local work p50 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Explanations off | 2.08 s | 3.94 s | 4.23 s | 6.0 s | 77% | 0.06 s |
| Explanations on | 4.90 s | 6.64 s | 8.65 s | 203.8 s | 90% | 0.07 s |

| Call (main run) | Calls | p50 | p95 | Failed |
| :--- | :--- | :--- | :--- | :--- |
| Context extraction, explanations off | 54 | 1.99 s | 2.92 s | 4 |
| Context extraction, explanations on | 54 | 2.06 s | 3.20 s (max 198.9 s) | 4 |
| Batched explanations | 50 | 2.52 s | 3.72 s | 6 |
| Weather lookup, explanations off (8 of 54 requests) | 8 | 1.89 s | 3.39 s | 0 |
| Weather lookup, explanations on (8 of 54 requests) | 8 | 2.62 s | 7.71 s (max 9.0 s) | 3 |

- A weather lookup runs only when the request names a place and time but no weather;
  those 8 requests took 4.2 s (off) and 7.3 s (on) at p50.
- Every failed context call fell back to the rule parser and the request still returned
  recommendations; failed explanation calls fell back to the deterministic template.
  The main run did not record failure causes.
- Against the MVP budget of p95 <= 5 s, the default configuration passes (4.2 s); the
  configuration with LLM explanations does not (8.7 s).

### 2.2 Confirmation run (after the fix)

12 of 12 requests returned recommendations: p50 3.63 s, p95 4.07 s, max 4.07 s, 98% of
the time in Gemini, local work 0.07 s at p50. One context call failed after 0.4 s with
`ConnectError` (a network failure on the measuring machine) and fell back to the rules.
No call was slow, so this run does not exercise the new deadline on the live network;
that is covered by `backend/tests/unit/test_provider_deadlines.py`.

## 3. Defect found: timeouts bounded each phase, not the call

One context call took 198.9 s and one weather lookup 9.0 s, although the configured limits
were 15 s and 5 s. httpx applies its timeout to each connect and each read, so a server
that keeps sending bytes slowly can hold a request open far longer. Fixed on
`fix/provider-wall-clock-timeouts`: `backend/app/services/deadline.py` bounds each Gemini
attempt (including the `thinkingConfig` compatibility resend) and each whole weather
lookup by wall-clock time; tests fail on the previous providers (4 of 6). The rule is in
`../../02_architecture/MULTI_AGENT_SPEC.md` section 3. In the main run this single
request is the 203.8 s maximum; the p95 values do not depend on it.

## 4. What the thesis can claim

- With the default configuration a chat answer takes about 2 s at the median and 4.2 s
  at p95 on the measuring machine, within the 5 s MVP budget.
- Turning on LLM explanations doubles the median (about 4.9 s) and puts p95 above the
  budget (8.7 s); about 90% of the time is spent waiting for Gemini.
- The multi-agent work itself (retrieval, scoring, the two bounded feedback loops,
  persistence) takes about 60–70 ms, so the agent architecture is not the latency cost.
- About 7% of context calls failed on this connection; the rule fallback kept every
  request answerable.

## 5. Limitations

- One machine and home connection in Vietnam on one day; a VPS will have different
  latency to Google and Open-Meteo. Re-measure after deployment (Phase 2).
- The main run predates the deadline fix and the wardrobe-aware user mapping; it is the
  only run with both configurations and two repeats.
- Server-side timing only; browser rendering and network to the client are excluded.
- 30 benchmark queries, two demo wardrobes.

## 6. Reproduce

The runner calls the paid Gemini API and is opt-in. Raw outputs go to the git-ignored
`data/private-chat-latency/`; this run is summarized in
`LIVE_CHAT_LATENCY_2026-11-25.json`.

```powershell
python backend/scripts/measure_live_chat_latency.py --wardrobe-user female_realistic_30=<female demo user id> --wardrobe-user male_realistic_27=<male demo user id> --queries 30 --repeats 2 --explanations both --out data/private-chat-latency/<run>.json
```
