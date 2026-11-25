# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | Phase 2 — Public Deployment is the only active phase (docs/07_implementation/ROADMAP.md, approved 2026-11-20, not started; waiting for the owner's VPS provider, domain and daily quota values). Phase 6 — Live Multi-Agent Benchmark completed 2026-11-25 (PR #21, #22). Phases 1 and 5 completed 2026-11-25 (PR #18, #19); Phases 3 and 4 completed 2026-11-22 (PR #17). |
| Active task | 2026-11-25 (branch fix/provider-wall-clock-timeouts, from main 2099bd6, not pushed): enforce wall-clock deadlines on provider calls. A live chat latency run (branch test/rating-personalization-simulation, `backend/scripts/measure_live_chat_latency.py`) found one Gemini context call of 199 s despite CONTEXT_TIMEOUT_SECONDS=15 and a 9 s weather lookup despite WEATHER_TIMEOUT_SECONDS=5, because httpx timeouts bound each phase only. New `backend/app/services/deadline.py` (`call_with_deadline`, bounded thread pool) now bounds each Gemini attempt (`post_gemini_generate_content`, including the thinkingConfig compatibility resend) and each whole weather lookup (OpenMeteo geocoding + forecast, OpenWeather). Spec: MULTI_AGENT_SPEC.md section 3. Separate branch test/rating-personalization-simulation (not pushed) holds the rating simulation, its sensitivity run and the latency runner. Local `.env` (untracked) uses the Gemini detector with YOLO-World fallback and a paid Tier 1 key. Demo user IDs: female 115a5b13-f981-507f-87be-a3df6a1bf093, male 7df1e5c1-0248-5746-933e-3e069f998dcb. |
| Most recently modified files | backend/app/services/deadline.py; backend/app/services/context_providers.py; backend/app/services/weather_providers.py; backend/tests/unit/test_provider_deadlines.py; docs/02_architecture/MULTI_AGENT_SPEC.md (section 3); CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-25 (branch fix/provider-wall-clock-timeouts): `cd backend; python -m pytest -q` 976 passed; `tests/unit/test_provider_deadlines.py` 6 passed, and 4 of them fail on the previous providers. Frontend unchanged since 2026-11-22: `npx vitest run` 132 passed and `npx tsc --noEmit` clean, from D:\. |
| Next step | (1) Owner: review and merge fix/provider-wall-clock-timeouts, then test/rating-personalization-simulation (CURRENT_STATE.md will need a small merge). (2) Write the live chat latency report (54 successful requests per configuration: explanations off p50 2.1 s / p95 4.2 s, on p50 4.9 s / p95 8.7 s; 6 correct 422 responses from query-user mismatch excluded) and fix the runner's user mapping; optionally rerun a small set to confirm the deadline. (3) Usability test (SUS, 5–10 participants). (4) Start the thesis report from thesis/Mau bao cao KLTN_DS.docx. (5) Phase 2: owner records VPS provider, domain and daily quota values. Older open items: ProviderError details leak internals in other providers; avatar upload reads the whole file before the size check; 403 vs 404 for another user's ingestion batch; A-1; T-1, T-4. |

## Local Environment Notes

- Frontend tests MUST be run from `D:\` (uppercase drive); lowercase `d:\` breaks Vitest module resolution. A reused dev server on :3000 makes the golden Playwright spec fail.
- Local `.env` uses real providers: Gemini vision/context, YOLO-World detector (`backend/models/yolov8s-worldv2.onnx`, git-ignored, from `scripts/download_yolo_world_model.py`), FASHN try-on, local object storage. Media previously in MinIO was copied to `data/storage/<bucket>/<key>`; the MinIO volume was left intact.
- `data/fashion_stylist.db` is at migration 0014 with the 2026-11-18 golden seed and confirmed demo wardrobes: female `115a5b13-f981-507f-87be-a3df6a1bf093` (31 items) and male `7df1e5c1-0248-5746-933e-3e069f998dcb` (27 items). Backups: `data/fashion_stylist.before_0013_*.db`, `data/fashion_stylist.before_0014_*.db`, `data/fashion_stylist.before_reseed_20261118_081930.db`, `data/fashion_stylist.before_demo_wardrobe_20261118_083003.db`. Pass an absolute path to `scripts/seed_data.py --database-url`; a relative `sqlite:///../data/...` fails with `unable to open database file`.
- Known pre-existing lint error: `react-hooks/set-state-in-effect` at `frontend/src/components/tryon/TryOnModal.tsx:223`. `frontend/e2e/real-backend.spec.ts` selectors were updated in the redesign but that spec has not been run.

## Update Rules

- This file MUST be read at the start of each coding session.
- This file MUST be updated when the active phase or task changes.
- Only a command that completed successfully MAY be recorded as the latest passing verification command.
- Detailed product or technical decisions MUST remain in their source-of-truth specifications, not in this file.
- Completed task history belongs in git and `docs/archive/`, not in this file.
