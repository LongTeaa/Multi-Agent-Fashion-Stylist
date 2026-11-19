# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | None active. MVP Phases 1–7 and advisor stages 1–6 are complete (archived in docs/archive/). docs/07_implementation/ROADMAP.md has no approved phase yet. |
| Active task | 2026-11-19: Review item (9) committed as a1d5751 and fast-forwarded to main (no PR). validate_image_bytes now removes EXIF (GPS, device), XMP, JPEG comments and PNG text from every upload after applying the EXIF orientation; uploads without metadata stay byte-identical; ICC profile, PNG transparency and JPEG quantization are kept. Avatars now go through validate_image_bytes, so they are stored upright, the detector gets clean bytes, and non PNG/JPEG/WebP files return 422 as API_CONTRACT 8.4 states. Review items (1)–(6) merged to main in PR #12 (7f5e15d). Demo user IDs: female 115a5b13-f981-507f-87be-a3df6a1bf093, male 7df1e5c1-0248-5746-933e-3e069f998dcb. |
| Most recently modified files | (9) backend/app/services/upload_validation.py; backend/app/services/tryon_service.py; backend/tests/unit/test_upload_validation.py; backend/tests/integration/test_tryon_api.py; docs/04_data/OBJECT_STORAGE_SPEC.md (3); docs/03_domain/INGESTION_AND_RETRIEVAL_SPEC.md; docs/05_api/API_CONTRACT.md (8.4); docs/06_features/VIRTUAL_TRYON_SPEC.md; CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-19: backend `python -m pytest -q` (820 passed, after (9)); frontend `npx vitest run` (128 passed, 17 files) and `npx tsc --noEmit` from D:\ (after (3)); `scripts/verify_documentation.ps1`. Every new or extended test fails without its fix. |
| Next step | Originals already stored before (9) still carry their EXIF; no backfill was run. Remaining review items: ProviderError details leak internals; avatar upload reads the whole file before the size check; 403 vs 404 for another user's ingestion batch; owner decision on A-1. Tests in tests/unit/test_upload_validation.py that do not override providers call the live detector from the local .env (about 160 s). Thesis alignment items T-1 to T-4. Known UI nits on demo data: footwear/accessory cards show a length label; rain and water_resistant both render as 'Chống mưa'. |

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
