# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | None active. MVP Phases 1–7 and advisor stages 1–6 are complete (archived in docs/archive/). docs/07_implementation/ROADMAP.md has no approved phase yet. |
| Active task | 2026-11-18 (c): Review quick fixes A3, B1, C4 on branch fix/formal-ranking-seed (uncommitted). A3: FormalityFit takes the weaker of the average and the weakest major item; sparse categories (< 2 candidates) add items one formality level outside the range, marked per item; formal requests now rank shirt + trousers + Oxford first. B1: golden seed carries realistic comfort/silhouette/length/functional flags and the button-down shirt is formality 4. C4: evaluate_real_ingestion.py replay matched the old extract_attributes signature (no spatial_context), so confirmation failed; fixed, plus --detector {gemini,yolo_world} for live runs. Retrieval Precision@5 fell 0.845 -> 0.79 (metadata), Recall@10 unchanged; report fixture and ALIGNMENT_BACKLOG T-1 updated. The local data/fashion_stylist.db was NOT reseeded (re-running the seed resets golden wear counters). Earlier (a) docs reorganization 9a251db and (b) try-on consent/timeout fa7949d are on main. |
| Most recently modified files | (c) backend/app/agents/fashion_scoring.py; backend/app/services/retrieval_service.py; backend/app/core/seed.py; backend/scripts/evaluate_real_ingestion.py; backend/tests/unit/{test_fashion_scoring.py,test_retrieval.py}; backend/tests/integration/{test_seed_data.py,test_formal_occasion_ranking.py (new),test_real_ingestion_replay.py (new)}; data/fixtures/retrieval_evaluation_v1_report.json; docs/04_data/DATA_SCHEMA.md (section 5); docs/03_domain/FASHION_KNOWLEDGE_BASE.md (3.3); docs/03_domain/INGESTION_AND_RETRIEVAL_SPEC.md (section 6); docs/07_implementation/ALIGNMENT_BACKLOG.md. |
| Latest passing verification command | 2026-11-18 (c): targeted backend pytest (scoring, retrieval, seed, golden, formal ranking, replay; all passed), tests/evaluation (7 passed), scripts/evaluate_real_ingestion.py offline replay passed and --live --detector yolo_world completed 7/7 cases; scripts/verify_documentation.ps1 passed. Full backend suite: see Next step. |
| Next step | Confirm the full backend suite passes, then commit (c) as focused commits and merge when the user asks. Remaining review items: owner decisions in docs/07_implementation/ALIGNMENT_BACKLOG.md; benchmark foundation (B2, E2) before the multi-agent upgrade. |

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
