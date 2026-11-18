# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | None active. MVP Phases 1–7 and advisor stages 1–6 are complete (archived in docs/archive/). docs/07_implementation/ROADMAP.md has no approved phase yet. |
| Active task | 2026-11-19: Fixes from the whole-project review, on branch fix/review-findings. Committed: (1) avatar deletion removes the try-on renders made from it (a799b8b); (2) missing `SecretStr` import in dependencies.py (a95f157); (3) client UUIDs from frontend/src/lib/uuid.ts work outside a secure context (178dcd1). Uncommitted: (4) execute_stylist_recommendation now keeps the request's client_session_id in the fresh graph state, so the Context Agent copies it into StylistContext and the persisted context_snapshot (it was always null). Demo user IDs: female 115a5b13-f981-507f-87be-a3df6a1bf093, male 7df1e5c1-0248-5746-933e-3e069f998dcb. |
| Most recently modified files | (4) backend/app/agents/stylist_graph.py; backend/app/agents/state.py (docstring); backend/tests/integration/test_stylist_graph.py; CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-19: backend `python -m pytest -q` (803 passed, after (4)); frontend `npx vitest run` (128 passed, 17 files) and `npx tsc --noEmit` from D:\ (after (3)); `scripts/verify_documentation.ps1`. Every new or extended test fails without its fix. |
| Next step | Commit (4). Remaining review items, lowest priority last: wardrobe_service._primary_media_id ignores soft-deleted media; media endpoint Content-Length taken from the DB; ProviderError details leak internals; avatar upload reads the whole file before the size check; inconsistent EXIF handling in upload_validation.py; owner decision on A-1. Known UI nits on demo data: footwear/accessory cards show a length label; rain and water_resistant both render as 'Chống mưa'. |

## Local Environment Notes

- Frontend tests MUST be run from `D:\` (uppercase drive); lowercase `d:\` breaks Vitest module resolution. A reused dev server on :3000 makes the golden Playwright spec fail.
- Local `.env` uses real providers: Gemini vision/context, YOLO-World detector (`backend/models/yolov8s-worldv2.onnx`, git-ignored, from `scripts/download_yolo_world_model.py`), FASHN try-on, local object storage. Media previously in MinIO was copied to `data/storage/<bucket>/<key>`; the MinIO volume was left intact.
- `data/fashion_stylist.db` is at migration 0014 with the 2026-11-18 golden seed. Backups: `data/fashion_stylist.before_0013_*.db`, `data/fashion_stylist.before_0014_*.db`, `data/fashion_stylist.before_reseed_20261118_081930.db`. Pass an absolute path to `scripts/seed_data.py --database-url`; a relative `sqlite:///../data/...` fails with `unable to open database file`.
- Known pre-existing lint error: `react-hooks/set-state-in-effect` at `frontend/src/components/tryon/TryOnModal.tsx:223`. `frontend/e2e/real-backend.spec.ts` selectors were updated in the redesign but that spec has not been run.

## Update Rules

- This file MUST be read at the start of each coding session.
- This file MUST be updated when the active phase or task changes.
- Only a command that completed successfully MAY be recorded as the latest passing verification command.
- Detailed product or technical decisions MUST remain in their source-of-truth specifications, not in this file.
- Completed task history belongs in git and `docs/archive/`, not in this file.
