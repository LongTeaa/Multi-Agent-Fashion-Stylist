# Current Implementation State

| Field | Value |
| :--- | :--- |
| Current phase | None active. MVP Phases 1–7 and advisor stages 1–6 are complete (archived in docs/archive/). docs/07_implementation/ROADMAP.md has no approved phase yet. |
| Active task | 2026-11-18 (d): Review item B2, demo wardrobe from a public dataset (uncommitted, on main working tree). data/fixtures/demo_wardrobe_v1.json lists 58 CC0 single-garment photos (Alexey Grigorev Clothing dataset), visually reviewed, split into female (31) and male (27) personas; backend/scripts/build_demo_wardrobe.py downloads to git-ignored data/demo-wardrobe/ and ingests through the ingestion services, stopping at needs_review. Local data/fashion_stylist.db now holds both confirmed demo wardrobes: female 115a5b13-f981-507f-87be-a3df6a1bf093 (31 items; ingested by the script, confirmed through the web UI) and male 7df1e5c1-0248-5746-933e-3e069f998dcb (27 items; uploaded and confirmed through the web UI with Playwright). Confirmation accepted Gemini's proposals as-is, except one male shirt whose extraction failed (category set from the manifest) and one duplicate jeans detection that was deleted. Category vs manifest: female 31/31, male 26/27 (quarter-zip fleece labelled Hoodie stored as outerwear). Backups: data/fashion_stylist.before_demo_wardrobe_20261118_083003.db, data/fashion_stylist.before_ui_confirm_*.db. |
| Most recently modified files | (d) .gitignore; backend/scripts/build_demo_wardrobe.py (new); backend/tests/unit/test_demo_wardrobe_manifest.py (new); data/fixtures/demo_wardrobe_v1.json (new); docs/07_implementation/TEST_STRATEGY.md (section 2); CURRENT_STATE.md. |
| Latest passing verification command | 2026-11-18 (d): backend pytest tests/unit/test_demo_wardrobe_manifest.py (4 passed); build_demo_wardrobe.py --download --dry-run (58 images, hashes verified); wardrobe API totals 31 (female) and 27 (male). Previous full backend suite: 795 passed (2026-11-18, before (d)). |
| Next step | Commit (d). Open the app as a demo user with localStorage.setItem('fashion_stylist_user_id', '<id>'). Known UI nits seen on the demo data: footwear/accessory cards show a length label; rain and water_resistant both render as 'Chống mưa'. Detections do not record which Gemini model answered (needed for E2). Then E2 benchmark using expected_category and confirmed attributes. |

## Local Environment Notes

- Frontend tests MUST be run from `D:\` (uppercase drive); lowercase `d:\` breaks Vitest module resolution. A reused dev server on :3000 makes the golden Playwright spec fail.
- Local `.env` uses real providers: Gemini vision/context, YOLO-World detector (`backend/models/yolov8s-worldv2.onnx`, git-ignored, from `scripts/download_yolo_world_model.py`), FASHN try-on, local object storage. Media previously in MinIO was copied to `data/storage/<bucket>/<key>`; the MinIO volume was left intact.
- `data/fashion_stylist.db` is at migration 0014 with the 2026-11-18 golden seed. Backups: `data/fashion_stylist.before_0013_*.db`, `data/fashion_stylist.before_0014_*.db`, `data/fashion_stylist.before_reseed_20261118_081930.db`. Pass an absolute path to `scripts/seed_data.py --database-url`; a relative `sqlite:///../data/...` fails with `unable to open database file`.
- Known pre-existing lint error: `react-hooks/set-state-in-effect` at `frontend/src/components/tryon/TryOnModal.tsx:233`. `frontend/e2e/real-backend.spec.ts` selectors were updated in the redesign but that spec has not been run.

## Update Rules

- This file MUST be read at the start of each coding session.
- This file MUST be updated when the active phase or task changes.
- Only a command that completed successfully MAY be recorded as the latest passing verification command.
- Detailed product or technical decisions MUST remain in their source-of-truth specifications, not in this file.
- Completed task history belongs in git and `docs/archive/`, not in this file.
