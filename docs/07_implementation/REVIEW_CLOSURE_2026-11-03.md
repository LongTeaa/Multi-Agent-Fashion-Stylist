# Repository review closure — 2026-11-03

## Scope and disposition

The twelve reproducible findings in [the original review](PROJECT_REVIEW_2026-11-02.md) and the five reported [UX problem groups](UX_REVIEW_AND_REMEDIATION_2026-11-02.md) have corrective implementation and regression coverage. This closes the software review scope; it does not certify production readiness or real-model accuracy.

Earlier corrections are recorded in commits `c6b8193`, `9c62948`, `aca7be3`, `17232ff`, and `1db088a`. Vision coordinate normalization, measured crop policy, and versioned boundary evidence are in `9b25db5`, `ffc08b6`, `e0e66ef`, and `6462620`.

The final correction adds durable content-bound retry responses, feedback metadata replay, bounded fit preferences, balanced candidate generation, seed UUID preservation, explicit-null validation, raw crop restoration, contained previews, consistent taxonomy labels, and selected-photo recovery. Normative API/data/feature contracts were updated together with tests.

## Acceptance record

Deterministic browser tests use a temporary database/storage and explicitly fake/offline providers; they do not consume live AI quota or alter the canonical wardrobe.

| Verification | Final result |
| --- | --- |
| Backend: `.venv/Scripts/python.exe -m pytest tests -q -m "not live_provider" --tb=short` | 631 passed, 32 deprecation warnings, 285.81 seconds |
| Frontend: `npm test` | 109 passed across 15 files |
| Frontend: `npm run type-check` and `npm run lint` | Passed |
| Frontend: `npm run build` | Passed; all eight static pages generated |
| Browser: `npm run test:e2e`, backend venv on PATH | 9 passed, 47.3 seconds |
| Targeted upload/replay/migration integration checks | 8 passed before final regression; final regression includes the additional legacy-key and rated-target assertions |
| `git diff --check` | Passed |

Windows process/network restrictions required approved external-sandbox test/build runs. Browser teardown emitted Windows Proactor connection-reset diagnostics; all nine assertions completed successfully. These diagnostics and library deprecations are not counted as failed acceptance checks.

## Canonical database upgrade

The configured `data/fashion_stylist.db` was backed up using SQLite backup to `data/fashion_stylist.before_0012_20261103_093240.db`, then upgraded **0009 → 0012** without reseeding. All pre-existing table row counts were unchanged, including 22 wardrobe items, 94 media assets, 28 item-media links, 2 outfits, 6 outfit-item links, 19 retrieval documents, and 33 detections. Media rows (including keys/checksums) and media link ownership/roles were compared unchanged; `PRAGMA foreign_key_check` was empty and `PRAGMA integrity_check` returned `ok`. Golden legacy item aliases were replaced by UUIDs. No storage objects were rewritten. Sanitized verification: [upgrade record](REVIEW_UPGRADE_2026-11-03.json).

The regression set covers uploads of 1, 2, and 10 distinct photos; controlled per-photo detector failure; long-running polling; source selection and reload; explicit crop save and raw-frame restoration; actual persisted-item editing; Vietnamese search; grounding and diversity; null rejection; retry content conflicts and metadata; rating prompt suppression; concurrent request binding/persistence; and populated migration reference preservation.

Screenshots use deterministic synthetic inputs and demonstrate control layout, not detector accuracy:

- [Desktop crop review](screenshots/review-closure-desktop.png)
- [375 px crop review](screenshots/review-closure-mobile.png)

## Remaining evaluation limits

- Gemini availability errors (including HTTP 503/reset) remain an external live-provider limitation. Deterministic regression success does not establish provider uptime or latency.
- Seven private real source images and the pooled partial live responses are diagnostic evidence, not a representative accuracy benchmark. The worn-polo live case has no successful measured response in that evidence set.
- The v2 worn-trousers annotation was a source-only review by the same agent. It is not independent human/inter-rater validation or a new inference result. See [annotation and boundary review](CROP_BOUNDARY_AND_ANNOTATION_REVIEW_2026-11-03.md).
- The confidently wrong singleton negative control adds 1,680 protected pixels. The margin heuristic cannot guarantee missed-object/face safety. Explicit manual crop, full-image, and raw-frame controls improve reviewability; they do not solve recognition.
- Optional zoom, manual merge, and individual-photo progress/retry controls from the UX proposal are outside this defect-closure scope.

Independent human annotation and representative live-provider evaluation remain separate evaluation work before making model-quality claims. No additional software correction from R1–R12 remains assigned by this review.

## Working-tree provenance

The migration-0008 fix and its schema-test changes already existed before this closure task; their contents are preserved outside the task commit. The unrelated lecturer-plan draft and generated `next-env.d.ts` are also excluded. Verification below applies to the full working tree including those existing migration corrections.
