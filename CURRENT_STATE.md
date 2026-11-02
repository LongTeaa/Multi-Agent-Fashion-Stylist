# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | Phase 7 — Evaluation and Acceptance (follow-up hardening) |
| Active task | Completed real-image ingestion review and fixed Gemini coordinate conversion. Seven private originals and ten human-annotated regions verify isolated multi-photo source association, exact crops, later-photo crop edits/reload/confirmation. Gemini now requests native YXYX 0..1000 box_2d and validates/converts to canonical XYXY 0..1. |
| Most recently modified files | Gemini provider; vision_evaluation metrics and regression tests; evaluate_real_ingestion runner; digest-pinned real-image manifest; ingestion/test specifications and real-image findings report; .gitignore and CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-02: python -m pytest tests/unit/test_gemini_coordinates.py tests/unit/test_provider_selection.py tests/unit/test_vision_evaluation.py tests/unit/test_crop_engine.py tests/unit/test_vision_normalization.py tests/integration/test_ingestion_flow.py tests/integration/test_multi_photo_crop.py -q: 93 passed. python backend/scripts/evaluate_real_ingestion.py passed for 7 real source photos and 10 annotated crops in temporary DB/storage. git diff --check passed. Post-fix --live runs were incomplete due two consecutive HTTP 503 responses; no passing live model-quality claim. |
| Next step | Repeat the live localization evaluation when the configured Gemini service is stable; inspect predicted crops and expand the real annotated corpus (different shoe pairs, clutter, blur, partial garments, EXIF orientations) before asserting model accuracy. Private artifacts: data/private-vision-review/; public findings: docs/07_implementation/REAL_IMAGE_INGESTION_REVIEW_2026-11-02.md. MinIO was started to read existing originals; application wardrobe data was not edited. Existing migration 0008/schema-test and generated next-env changes remain outside this task commit. |

## Update Rules

- This file MUST be read at the start of each coding session.
- This file MUST be updated when the active phase or task changes.
- Only a command that completed successfully MAY be recorded as the latest passing verification command.
- Detailed product or technical decisions MUST remain in their source-of-truth specifications, not in this file.
