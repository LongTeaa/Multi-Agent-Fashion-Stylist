# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | Phase 2 — Public Deployment is the only active phase (docs/07_implementation/ROADMAP.md, approved 2026-11-20, not started; waiting for the owner's VPS provider, domain and daily quota values). Phase 6 — Live Multi-Agent Benchmark completed 2026-11-25 (PR #21, #22). Phases 1 and 5 completed 2026-11-25 (PR #18, #19); Phases 3 and 4 completed 2026-11-22 (PR #17). |
| Active task | 2026-11-26: whole-project review before the thesis report and public deployment (no code change), recorded in `docs/archive/reports/PROJECT_REVIEW_2026-11-26.md`: deployment blockers P1-1 to P1-4 (client-chosen `X-User-Id` on a public repo with published demo user IDs; no Dockerfile or production compose; `alembic` only in dev extras; `.env` and local storage paths tied to the repository layout), hardening items P2-1 to P2-7, and an evidence map against the 8-chapter report template. Not committed yet. Local `.env` (untracked) uses the Gemini detector with YOLO-World fallback and a paid Tier 1 key. Demo user IDs: female 115a5b13-f981-507f-87be-a3df6a1bf093, male 7df1e5c1-0248-5746-933e-3e069f998dcb. |
| Most recently modified files | docs/archive/reports/PROJECT_REVIEW_2026-11-26.md; docs/archive/README.md; docs/07_implementation/ALIGNMENT_BACKLOG.md (T-1, T-2 facts only); CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-26 on main 34dbe2e: `cd backend; python -m pytest -q` 976 passed; from D:\ `npx vitest run` 132 passed in 18 files, `npx tsc --noEmit` clean, `npx next build` succeeded; `scripts/verify_documentation.ps1` passed. `npx eslint .` still fails on the known `TryOnModal.tsx:227` error. |
| Next step | Follow `docs/archive/reports/PROJECT_REVIEW_2026-11-26.md` section 7: (1) owner decides T-1 to T-4, the VPS provider, domain and daily quotas, and schedules the SUS session (5–10 participants); (2) a small hardening PR: ProviderError details in `stylist.py`, docs and cleanup-metrics exposure, the ESLint error, the retired-model fallback; (3) Phase 2 (session auth and quotas first, then container and proxy setup, backup/restore, smoke test); (4) in parallel, write report chapters 1–5 and collect references for the theory chapter; (5) after deploy: SUS, VPS latency, new screenshots, chapters 6–7. Older open items: 403 vs 404 for another user's ingestion batch; A-1. |

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
