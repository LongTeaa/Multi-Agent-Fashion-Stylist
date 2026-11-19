# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | None active. MVP Phases 1–7 and advisor stages 1–6 are complete (archived in docs/archive/). docs/07_implementation/ROADMAP.md has no approved phase yet. |
| Active task | Refactored LangGraph stylist recommendation workflow on branch `feat/refactor-multi-agent-stylist` (synced with `origin/main` at `38e971f`) into a 5-node cyclic multi-agent system with 2 bounded feedback loops (`fashion <-> wardrobe` targeted relaxation up to 2 rounds, `coordinator critic -> fashion` critique reroute up to 1 round), grounded LLM explanation synthesis with deterministic anti-hallucination fallback, and public `agent_trace` visualization in the Chat UI. Includes `origin/main`'s PR #12 review fixes (SecretStr import, avatar delete cascades try-on renders, LAN-safe client UUIDs, `client_session_id` retention, soft-deleted media exclusion via `services/item_media.py`, Content-Length from stored bytes) and image EXIF/XMP metadata stripping (`a1d5751`). |
| Most recently modified files | `backend/app/agents/{state.py, wardrobe_agent.py, fashion_agent.py, personalization_agent.py, coordinator.py, stylist_graph.py}`, `backend/app/services/{context_providers.py, item_media.py, tryon_service.py, upload_validation.py}`, `backend/app/api/v1/endpoints/{media.py, stylist.py}`, `frontend/src/lib/uuid.ts`, `frontend/src/components/chat/RecommendationView.tsx`, `docs/05_api/API_CONTRACT.md`, `CURRENT_STATE.md`. |
| Latest passing verification command | 2026-11-19: From `backend`: unit/contract/stylist_graph suite (274 passed); `test_media_access.py`, `test_item_media.py`, `test_tryon_api.py`, `test_stylist_chat_api.py`, `test_review_closure.py` (46 passed); `test_provider_selection.py`, `test_upload_validation.py` (59 passed); From `D:\DO_AN\Multi-Agent-Fashion-Stylist\frontend`: `npx vitest run` (129 passed, 17 files) & `npx tsc --noEmit` (clean); `powershell -ExecutionPolicy Bypass -File scripts/verify_documentation.ps1` (passed). |
| Next step | Verify full test suite on merged `feat/refactor-multi-agent-stylist` and open Pull Request to merge into `main`. |

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
