# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | None active. MVP Phases 1–7 and advisor stages 1–6 are complete (archived in docs/archive/). docs/07_implementation/ROADMAP.md has no approved phase yet. |
| Active task | 2026-11-18 (b): Try-on privacy and timeout quick fixes from docs/archive/reports/PROJECT_REVIEW_2026-11-18.md (D1, D2), committed on branch docs/reorganize-documentation (not pushed). Avatar upload now requires form field consent=true (422 VALIDATION_ERROR otherwise, nothing stored); consent checkbox unchecked by default with copy disclosing external processing; FASHN adapter submits the job and waits job.result(timeout=TRYON_TIMEOUT_SECONDS), cancelling it on expiry so the moodboard fallback runs. POST /tryons is still synchronous (async 202 not implemented). 2026-11-18 (a): Documentation reorganization, committed separately on the same branch as 9a251db. Completed roadmaps, dated reviews, audits, spike report, JSON evidence, and screenshots moved to docs/archive/; new ROADMAP.md skeleton and ALIGNMENT_BACKLOG.md; SYSTEM_ARCHITECTURE.md updated to current providers (detector, FASHN try-on, Open-Meteo); knowledge-base test reference fixed. No code, schema, or API change. |
| Most recently modified files | (b) backend/app/api/v1/endpoints/tryons.py; backend/app/services/fashn_tryon_provider.py; backend/tests/unit/test_fashn_tryon_provider.py (new); backend/tests/integration/test_tryon_api.py; frontend/src/components/tryon/TryOnModal.tsx; frontend/src/lib/api.ts; frontend/src/components/TryOnModal.test.tsx; docs/05_api/API_CONTRACT.md (8.4); docs/06_features/VIRTUAL_TRYON_SPEC.md. (a) AGENTS.md; README.md; CURRENT_STATE.md; docs/README.md; docs/02_architecture/SYSTEM_ARCHITECTURE.md; docs/03_domain/FASHION_KNOWLEDGE_BASE.md; docs/07_implementation/{ROADMAP.md,ALIGNMENT_BACKLOG.md,TEST_STRATEGY.md,VIBE_CODING_GUIDE.md}; docs/archive/**; scripts/verify_documentation.ps1. |
| Latest passing verification command | 2026-11-18 (b): backend pytest tests/unit/test_fashn_tryon_provider.py tests/integration/test_tryon_api.py tests/contract (70 passed); frontend from D:\ npx vitest run (16 files, 124 passed), npx tsc --noEmit (clean); eslint only the pre-existing TryOnModal set-state-in-effect error; powershell -File scripts/verify_documentation.ps1 passed. Last code verification: backend pytest tests/unit tests/contract tests/integration (772 passed) and tests/evaluation (7 passed) with fake providers, 2026-11-18; frontend from D:\ npx vitest run (16 files, 123 passed), 2026-11-17. |
| Next step | Push the branch and open a PR when the user asks; then the remaining quick fixes from the review (C4 evaluation script, A3/B1 seed and formal ranking). User decides the owner-decision items in docs/07_implementation/ALIGNMENT_BACKLOG.md; approves the first upgrade phase and adds it to ROADMAP.md. |

## Local Environment Notes

- Frontend tests MUST be run from `D:\` (uppercase drive); lowercase `d:\` breaks Vitest module resolution. A reused dev server on :3000 makes the golden Playwright spec fail.
- Local `.env` uses real providers: Gemini vision/context, YOLO-World detector (`backend/models/yolov8s-worldv2.onnx`, git-ignored, from `scripts/download_yolo_world_model.py`), FASHN try-on, local object storage. Media previously in MinIO was copied to `data/storage/<bucket>/<key>`; the MinIO volume was left intact.
- `data/fashion_stylist.db` is at migration 0014. Backups: `data/fashion_stylist.before_0013_*.db`, `data/fashion_stylist.before_0014_*.db`.
- Known pre-existing lint error: `react-hooks/set-state-in-effect` at `frontend/src/components/tryon/TryOnModal.tsx:233`. `frontend/e2e/real-backend.spec.ts` selectors were updated in the redesign but that spec has not been run.

## Update Rules

- This file MUST be read at the start of each coding session.
- This file MUST be updated when the active phase or task changes.
- Only a command that completed successfully MAY be recorded as the latest passing verification command.
- Detailed product or technical decisions MUST remain in their source-of-truth specifications, not in this file.
- Completed task history belongs in git and `docs/archive/`, not in this file.
