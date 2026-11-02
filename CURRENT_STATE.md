# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | Phase 7 — Evaluation and Acceptance (follow-up hardening) |
| Active task | Completed conservative automatic crop margins for explicit single-item footwear at detector confidence >= 0.70. Each edge gains 2% of source dimensions, clipped to image bounds. Unknown/inferred scenes, worn/multi-item scenes, uncertain labels and manual crop edits remain exact. Stored review rectangle, crop, thumbnail and extraction pixels agree. |
| Most recently modified files | crop_policy service; classifier/provider scene-inference metadata; ingestion service and real-image evaluation runner; crop policy/integration/runner tests; frozen margin regression evidence; ingestion/API/test specifications and findings report; CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-02: backend pytest test_crop_policy, test_auto_crop_margin, test_real_ingestion_runner, test_crop_engine, test_multi_photo_crop, test_ingestion_flow, test_vision_normalization, test_provider_selection and test_gemini_coordinates: 104 passed. Final policy/integration/runner subset after test expansion: 15 passed. python backend/scripts/evaluate_real_ingestion.py passed with seven real photos/ten regions. Frozen Derby replay changes strict localization 0/1 to 1/1 and visibly retains sole; sneakers remain passing and non-footwear/worn scenes unchanged. Two fresh Derby live attempts unavailable; no new model-quality claim. git diff --check passed. |
| Next step | Independently review coarse worn-trousers annotations and expand the boundary corpus with nearby garments/faces, partial items and image-edge cases before broadening automatic margins beyond explicit isolated footwear. Preserve raw and effective boxes/metrics separately in future live runs. Worn-polo post-fix live accuracy remains unmeasured due provider instability. Frozen replay assumptions are explicit in data/fixtures/vision_crop_margin_regression_v1.json. Private originals/crops remain ignored; existing persisted wardrobe crops were not rewritten. Existing migration 0008/schema-test and generated next-env changes remain outside this task commit. |

## Update Rules

- This file MUST be read at the start of each coding session.
- This file MUST be updated when the active phase or task changes.
- Only a command that completed successfully MAY be recorded as the latest passing verification command.
- Detailed product or technical decisions MUST remain in their source-of-truth specifications, not in this file.
