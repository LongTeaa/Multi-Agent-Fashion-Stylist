# Repository Review — 2026-11-02

> Historical findings and baseline evidence below are preserved. See the 2026-11-03 closure addendum and `REVIEW_CLOSURE_2026-11-03.md` for the corrected implementation and final verification.

## Scope and result

Reviewed the current working tree, including the existing uncommitted migration/startup changes, against the thesis, PRD, API/data contracts, feature specifications, and roadmap. Inspection covered ingestion, storage/cleanup, wardrobe/profile APIs, retrieval, the recommendation pipeline, feedback/actions, try-on, frontend integration, migrations, fixtures, and test configuration.

Found **3 P1 issues and 9 P2 issues**. P1 means a broken normal user workflow, loss of persisted media, or a core recommendation invariant violation. P2 means a reproducible correctness defect or an operational/test-isolation gap requiring correction. Passing baseline tests do not cover the failure cases below.

Application code was not changed during this review. Database/storage reproductions used temporary directories and isolated databases. The previously recorded migration backup remains `data/fashion_stylist.before_0008_20261005_172128.db`.

## Findings

### R1 — P1: Every wardrobe edit sends a forbidden field

- Location: `frontend/src/components/wardrobe/WardrobeInventory.tsx:161`, `backend/app/schemas/wardrobe.py:68`.
- `handleOpenEdit` always includes `is_active` in `editForm`; `handleSaveEdit` sends that entire object. `WardrobeItemUpdate` has `extra="forbid"` and no `is_active` field.
- Evidence: validating the exact form payload produces `extra_forbidden` at `is_active`. Consequently, saving an otherwise valid edit is rejected with HTTP 422. The component test mocks `updateWardrobeItem` and checks only a subset of fields, so it passes despite this integration failure.
- Correction: align the frontend update type and payload with the contract. Add one browser/API integration check that edits an actual ingested UUID item and reloads its persisted attributes.

### R2 — P1: Expiration cleanup can delete a concurrently confirmed item's image

- Location: `backend/app/services/cleanup_service.py:173` and `:188`.
- `cleanup_expired_batches` reads batch status and checks `ItemMedia`, then deletes objects without atomically claiming expiration against confirmation. Confirmation can commit between the link check and deletion. The cleanup session retains the old batch status and can subsequently overwrite `confirmed` with `expired`.
- Evidence: an isolated reproduction paused cleanup at `delete_object`, confirmed the detection in another session, and resumed cleanup. Confirmation created one active item; cleanup then reported no failures, deleted its linked crop, and left the batch `expired`.
- Correction: serialize the confirmation/expiration claim before storage deletion. Reuse the atomic state transition discipline already implemented for explicit cancellation and add a two-session regression test.

### R3 — P1: Retrying a recommendation returns deleted wardrobe items

- Location: `backend/app/api/v1/endpoints/stylist.py:74` and `:179`.
- A cache hit calls `_reconstruct_idempotent_response` and returns before normal grounding checks. Its wardrobe join does not require active, confirmed, non-deleted items and does not revalidate slot/category consistency.
- Evidence: recommend using UUID wardrobe items, delete a recommended top through the wardrobe API, then resend the same idempotency key. Initial recommendation, deletion, and retry all return HTTP 200; the retry still recommends the deleted top.
- Correction: apply the active-wardrobe invariant on replay, with an explicit stale-result policy. Historical outfit reads can retain inactive items, but a successful recommendation response must satisfy the active-item rule.

### R4 — P2: Concurrent retries persist duplicate recommendation sets

- Location: `backend/app/services/outfit_persistence.py:122`, `backend/app/models/entities.py:436`.
- Persistence checks for an existing `(user_id, request_id)` before inserting, but no atomic request claim or unique `(user_id, request_id, rank)` constraint protects that check. Both requests can observe an empty result and create different IDs for the same request and rank.
- Evidence: two isolated sessions synchronized immediately after the existing-result lookup both returned success and committed separate rank-1 recommendations for the same user/request key.
- Impact: retries can create duplicate outfit IDs and distort feedback cadence; a later replay can contain duplicate ranks or too many recommendations.
- Correction: claim the request atomically and recover the winning persisted result on collision. Any schema change must include the data contract, migration, and concurrency test.

### R5 — P2: Cache hits bypass mandatory client-session reconciliation

- Location: `backend/app/api/v1/endpoints/stylist.py:191` and `:194`.
- The cache-hit return precedes `reconcile_client_session_id`. Two individually valid but different header/body session UUIDs are therefore accepted on retries even though the API contract requires HTTP 422 for every such conflict.
- Evidence: after creating a cached recommendation, a retry with different valid UUID v4 values in `X-Client-Session-Id` and `client_session_id` returned HTTP 200.
- Correction: complete request validation before any cache return. Also bind idempotency keys to the original query/location: the current implementation accepts a changed query under the same key and silently returns the old occasion.

### R6 — P2: Retry reconstruction drops saved context and explanation metadata

- Location: `backend/app/api/v1/endpoints/stylist.py:64` and `:105`.
- Reconstruction restores only seven context fields, resets `applied_preferences` and warnings to empty lists, and replaces feedback metadata with defaults. Fields already present in `context_snapshot`, including explicit constraints and weather source, are omitted.
- Evidence: the same request first returned `target_formality_range=[2,3]` and `weather_source="user"`; its retry returned `[]` and `"default"`. The frontend deliberately reuses the key after a network failure, so users can receive this degraded response during normal recovery.
- Correction: use a shared complete response mapping and persist response metadata needed for faithful retries. Avoid counting the same outfit IDs again when restoring feedback state.

### R7 — P2: The 500-combination cutoff starves later garments

- Location: `backend/app/agents/fashion_agent.py:101`.
- Depth-first nested loops exhaust the combination budget on early tops/bottoms before later garments are considered. Personalization exclusions are applied after this truncation, so the system may relax exclusions despite having valid alternatives in its candidate pool.
- Evidence: with three tops (first two black, third white), 15 bottoms, 15 footwear items, and one outerwear item, all 500 generated combinations used only the first two tops. With `avoid_colors=["black"]`, reranking returned black items and warned that all outfits violated the preference, although the white top could form complete valid outfits.
- Correction: apply exclusions before budget allocation where possible and distribute candidate exploration across garments as well as outfit branches. Add a wardrobe-size regression case.

### R8 — P2: Saved fit preferences have no ranking effect

- Location: `backend/app/agents/personalization_agent.py:427`, `backend/app/services/profile_service.py:141`.
- The profile API/UI accepts and persists `fit_preferences`, but reranking never reads it. Initial weight construction also excludes this group, and learned features do not include fit.
- Evidence: two otherwise equivalent candidates with slim versus oversized tops produced the exact same ordering and scores for `fit_preferences=["slim"]` and `["oversized"]`.
- Correction: connect the offered option to a documented bounded ranking signal and test a pair of otherwise equivalent outfits.

### R9 — P2: Seeded wardrobe IDs cannot be used by wardrobe detail/edit/delete routes

- Location: `backend/app/core/seed.py:46`, `backend/app/api/v1/endpoints/wardrobe.py:68`.
- The canonical seed persists IDs such as `item-top-01`, while GET/PATCH/DELETE item routes require `uuid.UUID` path parameters. List and recommendation operations accept those stored strings, masking the mismatch.
- Evidence: deletion of a seeded item returned HTTP 422 `uuid_parsing` before reaching ownership/service logic. All eight seeded item IDs use the incompatible format.
- Correction: use deterministic UUIDs for persisted seed items and migrate/reference them consistently, or explicitly align route identifier validation with the normative identifier contract. Verify CRUD against the seeded wardrobe.

### R10 — P2: Browser tests inherit real AI providers from the developer environment

- Location: `backend/scripts/run_browser_e2e.py:78`.
- The fixture isolates the database/storage and disables the scheduler, but leaves Vision, Context, Weather, and Image provider modes inherited from `.env`. Default automated tests can invoke external AI, consume credentials/quota, and vary with external service availability.
- Evidence: the first browser run inherited Gemini Vision/Image settings. Its real-backend try-on test logged `Gemini image provider failed` before falling back. A second run explicitly forcing offline provider modes passed all five tests without that external dependency.
- Correction: explicitly select deterministic provider modes or inject fakes in the browser fixture. Reserve real provider calls for separately opted-in live tests.

### R11 — P2: Ingestion polling abandons valid long-running batches

- Location: `frontend/src/components/ingestion/IngestionWorkflow.tsx:75` and `:122`.
- The UI stops after 30 polls at 1.5-second intervals and removes the recoverable batch ID from session storage while the server may still be processing. The backend supports ten images and processes images/detections sequentially, with individual Vision requests allowed 30 seconds and retry backoff on transient failures.
- Failure scenario established from these control paths: a valid batch still processing after approximately 45 seconds is shown as failed, and reload cannot resume it through the saved ID. Two slow extraction calls alone can exceed that budget. There is no batch-list recovery UI.
- Correction: retain the batch ID and offer continued/resumable polling for a nonterminal server status. Test delayed multi-image processing using a controlled fake rather than live waiting.

### R12 — P2: PATCH accepts null for non-null wardrobe fields and returns server/conflict errors

- Location: `backend/app/schemas/wardrobe.py:71`, `backend/app/services/wardrobe_service.py:169`.
- The update schema uses nullable types to express optional fields. `exclude_unset=True` still includes explicitly supplied nulls, which the service blindly assigns to non-null fields and lists consumed by retrieval-document construction.
- Evidence with a valid UUID item: `{"comfort_level":null}` returned HTTP 409 `DATA_CONFLICT`; `{"weather_suitability":null}` returned HTTP 500 `INTERNAL_SERVER_ERROR`. The latter transaction rolled back, and a subsequent GET remained valid.
- Correction: distinguish omitted fields from explicitly null values and reject null with HTTP 422 for required attributes. Preserve null support for fields that are actually nullable, such as `secondary_color`.

## Verification performed

| Check | Result |
| --- | --- |
| Backend: `.venv/Scripts/python.exe -m pytest tests -q -m 'not live_provider'` from `backend` | **537 passed**, 13 deprecation warnings, 448.32 s |
| Frontend: `npm run test -- --run` | **101 passed**, 13 files |
| Frontend: `npm run type-check` | Passed |
| Frontend: `npm run lint` | Passed |
| Frontend: `npm run build` | Passed after allowing Google Fonts access outside the sandbox |
| Browser: `npm run test:e2e`, with offline provider environment overrides | **5 passed**, 23.8 s |
| Targeted temporary-database/service reproductions | Confirmed R1–R10 and R12 as described; R11 is a control-flow/configuration finding |

Offline browser command used in PowerShell from `frontend`:

```powershell
$env:PATH = 'D:\source\Multi-Agent-Fashion-Stylist\backend\.venv\Scripts;' + $env:PATH
$env:VISION_PROVIDER = 'fake'
$env:CONTEXT_PROVIDER = 'fallback'
$env:WEATHER_PROVIDER = 'disabled'
$env:IMAGE_PROVIDER = 'disabled'
npm run test:e2e
```

The first frontend test/browser launches were blocked by sandbox process creation (`EPERM`); approved reruns succeeded. The first production build could not fetch Google Fonts inside the network-restricted sandbox; the approved rerun succeeded. Those environment failures are not counted as application defects.

## Coverage limits and follow-up

- The user's subsequent five UI observations and four screenshots are analyzed separately in `UX_REVIEW_AND_REMEDIATION_2026-11-02.md`, with confirmed multi-photo source-mapping/search defects and a concrete UX remediation proposal. These follow-up observations are not included in the original 12-finding count above.
- Existing cross-user ownership/foreign-key tests passed. The local MVP deliberately trusts `X-User-Id`; production authentication is explicitly outside PRD scope and is not reported as an MVP regression.
- MinIO adapter contract tests use a fake client. This review did not validate a running MinIO deployment or measure its latency.
- Existing Vision acceptance metrics explicitly use synthetic images and deterministic fake outputs. This review does not establish real-model tagging accuracy, live context F1, or provider latency. The incidental failed Gemini call during the first E2E run is not a live acceptance benchmark.
- The migration/startup changes present before review passed the full backend suite, including populated-database migration coverage. This review did not rerun migrations against the user's canonical database.
- Fix R1–R3 first. Next address atomic/complete retry handling (R4–R6), candidate coverage (R7), and the remaining profile/demo/test/input-lifecycle defects. Add regression coverage at the service/API boundary where mocked component tests currently hide integration mismatches.

## Closure addendum — 2026-11-03

| Finding | Implemented correction and regression evidence |
| --- | --- |
| R1 | Contract-compliant edit payload; real browser edits and reloads a persisted UUID item. |
| R2 | Expiration and confirmation serialize the ownership/state claim before deleting storage; two-session regression preserves confirmed media. |
| R3 | Retry revalidates active, confirmed ownership and slot compatibility; stale results return 409. |
| R4 | Serialized persistence returns one committed request/rank set under competing sessions. |
| R5 | Session reconciliation precedes replay; durable query/location fingerprint rejects changed-content reuse. Legacy wrong-query requests cannot claim an existing key. |
| R6 | Complete response snapshot commits with feedback delivery; retry retains context, preferences, warnings and prompt metadata without double-counting. Rated targets no longer prompt. |
| R7 | Balanced core/layer enumeration and clean-pool prefilter prevent the reproduced 500-candidate starvation; large-wardrobe API test covers saved exclusions. |
| R8 | Documented bounded fit preference signal swaps equivalent slim/oversized candidate ranking; neutral default remains unchanged. |
| R9 | Deterministic seed UUIDs; migration preserves existing media/outfits/retrieval/cache references; CRUD and populated downgrade/upgrade tests. |
| R10 | Browser fixture pins fake/offline providers independently of developer environment. |
| R11 | Resumable nonterminal polling retains batch identity beyond 45 seconds and restores selected photo. |
| R12 | Explicit null in required PATCH fields returns 422; nullable secondary color remains supported. |

The final test results, canonical database upgrade evidence, screenshots, and remaining live-model measurement limits are recorded in the linked closure report. This addendum supersedes the historical next-step list; it does not rewrite the initial reproductions.
