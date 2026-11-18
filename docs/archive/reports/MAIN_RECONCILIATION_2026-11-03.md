# Main reconciliation — 2026-11-03

## Scope and explicit decision

The user requested completion of publication preparation, excluded
`KE_HOACH_TICH_HOP_GOP_Y_GIANG_VIEN.md` from commits, and explicitly selected
preservation of the current local schema/API contract when asked about the
remote nullable footwear/accessory changes.

`origin/main` was fetched at `a1a7c7b`. Local main had twelve exclusive commits;
the remote had three. The populated-database migration repair and regression
test were committed separately as `4fda642`.

## Remote changes and reconciliation

| Remote commit | Decision |
| :--- | :--- |
| `389fd04` — require schema revision 0008 | Superseded by local startup validation at revision 0012. |
| `24144a6` — Gemini box normalization and longer polling | Superseded by the explicit native `box_2d` YXYX/1000 contract, canonical XYXY validation, coordinate regression tests, and local ingestion polling that continues until terminal state. The old implicit coordinate guessing must not be restored. |
| `a1a7c7b` — nullable footwear/accessory attributes | Excluded by the user's explicit decision. Keep the documented non-null defaults, current scoring, UI and PATCH validation. Keep foreign-key enforcement enabled during migration. |

Merge `5b46197` records the fetched remote history with the `ours` strategy.
Its tree is identical to its first parent; this is an intentional whole-tree
resolution after inspecting the three remote commits, not an automatic textual
merge. The remote-only nullable migration and associated tests are not imported.
The local migration 0009 remains detection-source linkage, followed by 0010–0012.

## Database deployment boundary

The remote and local histories used the same revision string `0009` for
different schemas. A database already upgraded with the remote nullable
migration is **not** a supported starting point for blindly running the local
0010–0012 chain: the revision string alone cannot establish compatibility.
Before deploying against such a database, back it up and reconcile its actual
schema and data through a separately verified migration. Do not stamp a new
revision to bypass this difference. Fresh databases and the existing local
0012 database follow the local chain. This task does not modify the canonical
database or private media.

## Publication boundary

Production `next build` regenerates `next-env.d.ts` to the already tracked
production type paths, leaving no content change to commit. Development/E2E
runs may regenerate dev paths; finish verification with a production build.
The lecturer-plan draft remains untracked and excluded. `.env` is ignored;
no environment file, private database, or private image is added by this task.
No push is performed as part of this preparation. Gemini Context remains
enabled locally, but successful live extraction is still unverified because
the previous five calls returned HTTP 429; fallback tests do not resolve that.

## Final verification

Verified on the reconciled code tree:

- Backend `.venv/Scripts/python.exe -m pytest tests -q -m "not live_provider" --tb=short`: 664 passed, 32 deprecation warnings, 257.46 seconds.
- Migration/schema regression: 13 passed, including populated upgrade preservation and schema validation.
- Frontend `npm run test -- --run`: 109 passed across 15 files.
- Browser `npm run test:e2e`: 9 passed, 47.0 seconds. Windows Proactor connection-reset diagnostics during teardown did not fail the tests.
- `npm run lint` and final `npm run build`: passed, including production TypeScript compilation.
- `git diff --check`: passed; the merge has no tree difference from its first parent, and fetched origin/main is an ancestor of local HEAD.

The first frontend test run was blocked by sandbox EPERM on Vitest cache renames;
the successful rerun used approved execution outside the sandbox. A backend run
inside the sandbox stopped progressing after a failure indicator and was
interrupted; only the completed full rerun outside the sandbox is counted as
passing. The initial sandbox build could not download Google Fonts; approved
builds with network access succeeded. No product code was changed to bypass
these execution restrictions.
