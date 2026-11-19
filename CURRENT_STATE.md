# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | Phase 1 — Live-Provider Ingestion Evaluation (docs/07_implementation/ROADMAP.md, approved 2026-11-19) on `main`, plus parallel multi-agent stylist refactor & two-layer advisory benchmark on `feat/refactor-multi-agent-stylist`. |
| Active task | 2026-11-19: Merged `origin/main` (`741288e`, PR #13 live-ingestion evaluation + garment taxonomy aliases) into `feat/refactor-multi-agent-stylist`. Branch contains: (1) refactored 5-node cyclic LangGraph stylist workflow (`fashion <-> wardrobe` relaxation <= 2 rounds, `coordinator critic -> fashion` reroute <= 1 round), batched grounded LLM explanation synthesis with anti-hallucination fallback, and public `agent_trace` UI; (2) Two-Layer Multi-Agent Advisory Benchmark (`backend/tests/evaluation/benchmark/`, `backend/scripts/evaluate_multi_agent_chatbot.py`, `data/fixtures/{stylist_benchmark_wardrobes_v1,multi_agent_benchmark_v1,judge_calibration_v1}.json`) plus parser/bottleneck fixes; (3) `origin/main` Phase 1 live-ingestion evaluation (`YOLO-World` + taxonomy aliases in `garment_taxonomy.py` now also resolved by `wardrobe_agent`). |
| Most recently modified files | `CURRENT_STATE.md`, `docs/07_implementation/TEST_STRATEGY.md`, `backend/app/agents/{state.py, context_agent.py, wardrobe_agent.py, fashion_agent.py, personalization_agent.py, coordinator.py, stylist_graph.py}`, `backend/app/services/{context_providers.py, garment_taxonomy.py, vision_evaluation.py}`, `backend/scripts/{evaluate_multi_agent_chatbot.py, evaluate_live_ingestion.py}`, `backend/tests/evaluation/benchmark/*`, `backend/tests/evaluation/test_multi_agent_benchmark.py`, `backend/tests/unit/{test_garment_taxonomy.py, test_live_ingestion_evaluation.py}`, `data/fixtures/{stylist_benchmark_wardrobes_v1,multi_agent_benchmark_v1,judge_calibration_v1,live_ingestion_*}.json`. |
| Latest passing verification command | 2026-11-19 (post-merge with `origin/main` `741288e`): `pytest tests/unit/{test_garment_taxonomy,test_vision_evaluation,test_live_ingestion_evaluation,test_context_agent,test_wardrobe_agent,test_grounding,test_personalization,test_fashion_scoring}.py tests/integration/test_stylist_graph.py tests/evaluation/{test_retrieval_metrics,test_multi_agent_benchmark}.py -q` (249 passed); both ROADMAP `--score` commands (`live_ingestion_attributes_v1_yolo_world.json`: category 56/58, garment type 53/58; `live_ingestion_localization_v3_yolo_world.json`: 17/47 regions); `powershell -ExecutionPolicy Bypass -File scripts/verify_documentation.ps1` (passed: 20 required files, 1 active roadmap phase). |
| Next step | (1) Verify merged suite on `feat/refactor-multi-agent-stylist` and open PR / run optional live Multi-Agent Judge benchmark. (2) On `main` Phase 1: owner decides thesis integration (`ALIGNMENT_BACKLOG.md` T-2) and reruns Gemini detector on sets A/B/C after quota reset. |

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
