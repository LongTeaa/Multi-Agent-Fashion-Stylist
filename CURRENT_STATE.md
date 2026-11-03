# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | Phase 7 — Evaluation and Acceptance (follow-up hardening) |
| Active task | Completed source-only worn-trousers annotation re-review and fixed boundary corpus. V1 remains unchanged; V2 updates only two worn-trousers reference rectangles. Frozen predictions re-score 0/2 to 2/2 without threshold changes; +/-3 pixel sensitivity is 81/81 for trousers and 76/81 for shoes. Production margin policy is unchanged. |
| Most recently modified files | Real-image evaluation runner default manifest; evaluate_crop_boundaries script; annotation-version and boundary-pixel tests; v2 real-image manifest, annotation sensitivity evidence, boundary corpus/results; test strategy and 2026-11-03 review report; CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-03: python -m pytest tests/unit/test_crop_boundaries.py tests/unit/test_annotation_versions.py tests/unit/test_crop_policy.py tests/unit/test_vision_evaluation.py tests/unit/test_real_ingestion_runner.py tests/integration/test_auto_crop_margin.py -q: 26 passed outside Windows sandbox after long Temp path failures. python backend/scripts/evaluate_crop_boundaries.py --report data/fixtures/crop_boundary_results_20261103.json: 9 policy-conforming cases, 6/6 protected-region guards and 2/2 positive controls; negative control exposes 1680 added protected pixels and is not a safety pass. Offline real-image v2 replay passed 7 sources/10 crops outside sandbox. git diff --check passed. No external AI calls this task. |
| Next step | Retain raw detector coordinates alongside effective padded crops and offer an easy restore-original-frame option during review, preserving exact manual crop behavior. This improves user control for known confidently wrong scene/candidate cases but does not solve missed-object/face detection. Independent human/inter-rater annotation remains outstanding; same-agent source-only v2 review is not new AI accuracy evidence. Public findings: docs/07_implementation/CROP_BOUNDARY_AND_ANNOTATION_REVIEW_2026-11-03.md. Private originals and crops remain ignored; existing migration 0008/schema-test and generated next-env changes stay outside the task commit. |

## Update Rules

- This file MUST be read at the start of each coding session.
- This file MUST be updated when the active phase or task changes.
- Only a command that completed successfully MAY be recorded as the latest passing verification command.
- Detailed product or technical decisions MUST remain in their source-of-truth specifications, not in this file.
