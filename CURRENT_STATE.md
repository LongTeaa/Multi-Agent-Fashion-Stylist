# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | Phase 7 — Evaluation and Acceptance (follow-up hardening) |
| Active task | Completed automatic-crop-first ingestion review. Default layout displays generated item crops; originals/overlays/sliders are hidden until optional per-item editing. Manual recropping is not required to confirm. Multi-source recovery, explicit saves and failure warnings remain. |
| Most recently modified files | IngestionWorkflow.tsx, DetectionItemCard.tsx, CropEditor.tsx; workflow and browser regressions; ingestion specification; review closure follow-up and desktop/mobile screenshots; CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-03 UI follow-up: npm test: 109 passed; npm run type-check, npm run lint and npm run build passed; npm run test:e2e: 9 passed in 50.4 seconds. git diff --check passed. Previous backend review regression: 631 passed. No backend/API/schema/database changes or external AI calls in this UI task. |
| Next step | Software review scope closed; see docs/07_implementation/REVIEW_CLOSURE_2026-11-03.md. Separate model-quality work remains: independent human/inter-rater annotation and representative live evaluation, including the unavailable worn-polo case and provider stability. Raw/manual crop controls do not solve missed-object/face detection. Optional zoom/merge/per-source retry UX is deferred. Preserve pre-existing migration 0008/schema-test changes, generated next-env and lecturer-plan draft outside the closure commit. |

## Update Rules

- This file MUST be read at the start of each coding session.
- This file MUST be updated when the active phase or task changes.
- Only a command that completed successfully MAY be recorded as the latest passing verification command.
- Detailed product or technical decisions MUST remain in their source-of-truth specifications, not in this file.
