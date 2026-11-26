# Implementation Roadmap

This is the active roadmap. The completed MVP roadmap (Phases 1–7) is archived at `../archive/MVP_ROADMAP.md`, and the completed advisor-feedback integration plan at `../archive/KE_HOACH_TICH_HOP_GOP_Y_GIANG_VIEN.md`. Archived roadmaps MUST NOT be reopened; follow-up work MUST be added here as a new phase.

## 1. Status

| Field | Value |
| :--- | :--- |
| Baseline | MVP Phases 1–7 and advisor stages 1–6 complete; `main` at the merge of PR #11 |
| Active phases | Phase 2 — Public Deployment (approved 2026-11-20; not started). |
| Completed phases | Phase 7 — Interface Polish Before Deployment (approved and complete 2026-11-26). Phase 1 — Live-Provider Ingestion Evaluation (approved 2026-11-19; complete 2026-11-25). Phase 3 — Try-On Provider Spike (approved 2026-11-20; complete 2026-11-22). Phase 4 — Switch Try-On to FLUX VTO (approved 2026-11-22; complete 2026-11-22, merged in PR #17). Phase 5 — Gemini Detector with YOLO-World Fallback (approved and complete 2026-11-25). Phase 6 — Live Multi-Agent Benchmark (recorded after the fact, complete 2026-11-25, PR #21 and #22). |
| Open alignment items | `ALIGNMENT_BACKLOG.md` |

Until a phase is approved, agents MUST NOT start feature work. Documentation alignment from `ALIGNMENT_BACKLOG.md` MAY proceed.

## 2. How to Add a Phase

Each phase MUST be a level-2 heading of the form `## Phase N — Title`, numbered from 1 within this roadmap, and MUST contain, in this order:

1. **Goal** — one or two sentences stating the user-visible or measurable outcome, and which thesis objective (chapter 1.2) it serves.
2. **Specification files** — the exact source-of-truth files and sections to read. A phase that changes the schema, API, or scoring MUST list the document it will update.
3. **Checklist** — bounded tasks as `- [ ]` items. A task MAY be checked only after its verification passes.
4. **Acceptance criteria** — observable conditions, including the golden scenario when recommendation behavior changes.
5. An executable-command block: a bold line reading `Executable Command:` or `Executable Commands:` followed by a fenced `powershell` block run from the repository root. Default verification MUST NOT require external API credentials.

`scripts/verify_documentation.ps1` checks that every phase heading has an executable-command block.

## 3. Phases

## Phase 1 — Live-Provider Ingestion Evaluation

**Goal:** Measure how accurately the deployed digitization pipeline (YOLO-World or Gemini detector, Gemini Vision attributes) localizes garments and extracts their attributes on real photos, and compare the two detectors. Serves thesis objective 1.2 "Xây dựng tủ đồ số" and resolves `ALIGNMENT_BACKLOG.md` item T-2. This phase does not touch the recommendation graph.

**Specification files:**

- `../03_domain/INGESTION_AND_RETRIEVAL_SPEC.md` (detection, crop, attribute extraction).
- `TEST_STRATEGY.md` section 3.2 (vision evaluation rules); this phase updates it.
- `../../data/fixtures/demo_wardrobe_v1.json` (58 CC0 single-garment photos) and `../../data/fixtures/vision_real_review_v2.json` (7 private real photos).

**Checklist:**

- [x] Freeze an attribute gold set `data/fixtures/vision_attribute_gold_v1.json` for the 58 demo photos. Category comes from the source dataset's human labels. Garment group and type, primary color, pattern, material and formality are drafted by an AI assistant and MUST be reviewed by the project owner; each field records its provenance. Labels confirmed in the app are not used, because they agree with the provider's proposals on 59 of 60 items and are therefore not independent.
- [x] Extend the localization set with private multi-item, worn-outfit and hanger photos annotated by the owner, as `data/fixtures/vision_real_review_v3.json` (14 web photos, 47 rectangles). Photos stay in the git-ignored `data/private-vision-review/`.
- [x] Provide an offline annotation page for reviewing attribute drafts and drawing garment rectangles that exports manifest JSON with SHA-256 digests.
- [x] Add pure attribute-scoring functions (category, garment-type group, color with canonical aliases, pattern, material, formality exact/±1/MAE, per-class confusion) to `backend/app/services/vision_evaluation.py` with unit tests.
- [x] Add an opt-in live runner that sends the gold photos through the real ingestion service in an isolated temporary database and storage, once per detector, and records raw provider outputs, latency and failures without secrets. A `--score` mode recomputes every metric from a saved raw-output file without network access.
- [x] Run YOLO-World live on sets A, B and C, write `docs/archive/reports/LIVE_INGESTION_EVALUATION_2026-11-19.md` with the frozen raw results under `data/fixtures/live_ingestion_*.json`, and draft the Vietnamese evaluation section for thesis chapter 7 (`docs/archive/reports/CHUONG_7_DANH_GIA_SO_HOA_TU_DO_NHAP_2026-11-19.md`).
- [x] Add the garment subtypes observed in the live run as taxonomy aliases (`backend/app/services/garment_taxonomy.py`, tests in `test_garment_taxonomy.py`) and re-score the frozen raw file offline; report section 3.1.
- [x] Rerun the Gemini detector on sets A, B and C with sufficient quota and add the comparison to the report. The 2026-11-19 run failed on 54/58 attribute and 21/21 localization detector requests (HTTP 429 daily quota, 503, timeouts) and is kept only as failure evidence. Done 2026-11-25 with a paid Tier 1 key and no provider failures (`docs/archive/reports/LIVE_INGESTION_EVALUATION_2026-11-25.md`): localization 25/47 vs 17/47 on set B (flat-lay 16/27 vs 8/27) and 9/10 vs 5/10 on set C, sign test over 21 photos p = 0.021. The report adds a same-day YOLO-World repeat (run-to-run variation) and a `gemini-3.5-flash-lite` vision baseline; no attribute difference on set A is significant.
- [x] Update `TEST_STRATEGY.md` section 3.2 and `ALIGNMENT_BACKLOG.md` T-2.

**Acceptance criteria:**

- Every reported metric states its denominator, the provider model identifiers, the run date and the number of provider failures. Failed calls are reported, never dropped silently.
- Gold labels are never changed after a live run to improve a score; any correction after the first run is recorded with its reason and both scores are reported.
- Default verification runs without credentials or network; the live runner is opt-in and never modifies the configured database or storage.

**Executable Commands:**

```powershell
cd backend; python -m pytest tests/unit/test_vision_evaluation.py tests/unit/test_live_ingestion_evaluation.py -q; cd ..
python backend/scripts/evaluate_live_ingestion.py --score data/fixtures/live_ingestion_attributes_v1_yolo_world.json
python backend/scripts/evaluate_live_ingestion.py --score data/fixtures/live_ingestion_localization_v3_yolo_world.json --localization-manifest data/fixtures/vision_real_review_v3.json
python backend/scripts/evaluate_live_ingestion.py --score data/fixtures/live_ingestion_attributes_v1_yolo_world.json data/fixtures/live_ingestion_attributes_v1_yolo_world_20261125.json data/fixtures/live_ingestion_attributes_v1_gemini_20261125.json data/fixtures/live_ingestion_attributes_v1_yolo_world_flash_lite_20261125.json
python backend/scripts/evaluate_live_ingestion.py --score data/fixtures/live_ingestion_localization_v3_yolo_world.json data/fixtures/live_ingestion_localization_v3_gemini_20261125.json --localization-manifest data/fixtures/vision_real_review_v3.json
./scripts/verify_documentation.ps1
```

## Phase 2 — Public Deployment

**Status:** Approved by the owner on 2026-11-20, with the proposed defaults for the authentication method, sign-up policy, and hosting topology. Still open, and owned by the owner: the VPS provider and domain, and the daily quota values. The first checklist item is complete only when those are recorded here.

**Goal:** Run the application on a public HTTPS URL where each person signs in to a private account, provider spending is capped, and data survives restarts and can be restored. This lets a small pilot group of real users produce the usage, rating, and latency evidence for thesis chapter 6.1 ("Trải nghiệm người dùng", "Tốc độ phản hồi") and gives the report a real "Hiện thực và Triển khai" chapter. Recommendation, scoring, and ingestion behavior MUST NOT change in this phase.

**Specification files:**

- `../01_product/PRD_MVP.md` section 3.2, which lists production-grade authentication as out of scope; this phase updates it (resolves `ALIGNMENT_BACKLOG.md` D-2 for this change).
- `../05_api/API_CONTRACT.md` section 1 (`X-User-Id` identity) and the error envelope; this phase adds the authentication endpoints, the session identity rule, and the `429` quota error.
- `../04_data/DATA_SCHEMA.md` (`users`); this phase adds credential, session, and usage-quota storage.
- `../02_architecture/SYSTEM_ARCHITECTURE.md` (components, ownership invariants); this phase adds the deployment topology.
- `../04_data/OBJECT_STORAGE_SPEC.md` (MinIO and local adapters, persistence).
- `../06_features/VIRTUAL_TRYON_SPEC.md` (paid try-on calls that need a quota).

**Checklist:**

- [ ] Record the owner decisions in this phase before implementation:
  - The authentication method. Proposed default: email and password with an Argon2 or bcrypt hash, and an opaque server-side session in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie. No third-party identity provider, so automated tests stay offline.
  - Sign-up policy. Proposed default: invite codes only during the pilot.
  - The hosting target and domain. Proposed default: one Linux VPS running Docker Compose behind a reverse proxy with automatic TLS. Serverless hosting does not fit, because SQLite, object storage, and the YOLO-World ONNX model need a persistent disk.
  - Daily quota values for chat, ingestion images, and try-on renders.
- [ ] Update `PRD_MVP.md`, `API_CONTRACT.md`, `DATA_SCHEMA.md`, and `SYSTEM_ARCHITECTURE.md` with the decisions above, before the code that depends on them.
- [ ] Add an Alembic migration for password credentials, sessions (stored as a token hash with expiry and revocation), and per-user daily usage counters. Existing users and their wardrobes MUST be preserved. Demo users MUST get credentials through a seed script, never through committed secrets.
- [ ] Add `register` (requires an invite code), `login`, `logout`, and `me` endpoints. Login MUST be rate-limited. Error messages MUST NOT reveal whether an email exists.
- [ ] Add an `auth_mode` setting with values `header` (default, for local development and the existing test suite) and `session`. In `session` mode, `get_current_user_id` MUST derive the user only from a valid session and MUST ignore `X-User-Id`. The application MUST refuse to start when the production profile is combined with `header` mode.
- [ ] Protect state-changing requests in `session` mode against cross-site requests: check `Origin` against the configured origins, or use an equivalent CSRF control.
- [ ] Frontend: add sign-in and invite-code sign-up pages. Send credentialed requests and stop generating a `localStorage` user UUID in `session` mode. Private media loading MUST keep working with the cookie. Redirect to sign-in on `401`. Copy is in Vietnamese and follows the UI copy rules in `AGENTS.md`.
- [ ] Enforce per-user daily quotas on chat requests that call the context or explanation provider, on ingestion images, and on try-on renders. Add a global daily cap per provider. An exceeded quota returns `429` with a Vietnamese message and makes no provider call. Requests that use the deterministic fallback alone MAY stay unmetered.
- [ ] Close the review items that matter once the API is public: `ProviderError` details that leak internals, and avatar uploads that read the whole file before the size check (`CURRENT_STATE.md`, older open items).
- [ ] Add a backend Dockerfile (Python 3.11, non-root, health check on `/health`), a frontend Dockerfile (production Next.js build), and a `compose.prod.yaml` with the reverse proxy and named volumes for the database, object storage, and detector model. Secrets come only from an untracked environment file. Configure SQLite for one writer process with WAL mode.
- [ ] Production hardening:
  - CORS limited to the deployed origin;
  - interactive API docs disabled or protected;
  - security headers set by the reverse proxy;
  - logs that contain no secrets, raw images, or user query text beyond what debugging requires.
- [ ] Add a backup script for the SQLite database (online backup API) and object storage. Restore it into a clean environment once, and record the result.
- [ ] Add a short Vietnamese privacy notice in the app: what is stored (wardrobe photos, avatar photos, ratings), which external providers receive images, and how to delete items and avatars.
- [ ] Deploy, then run the golden scenario manually on the public URL with two pilot accounts, including a cross-account access attempt. Record it in `docs/archive/reports/DEPLOYMENT_SMOKE_<date>.md` with screenshots and measured p95 chat latency.

**Acceptance criteria:**

- In `session` mode, a request carrying another user's ID in `X-User-Id` gets the caller's own data or `401`, never the other user's wardrobe, outfit, rating, wear-log, avatar, or media. The cross-user isolation tests pass in both modes.
- No endpoint except `register`, `login`, and `/health` is reachable without a valid session in `session` mode.
- When a quota is exceeded, the API returns `429`, and the provider fakes record zero calls for that request.
- The existing backend and frontend suites pass unchanged in the default `header` mode, and no new test needs network access or provider credentials.
- The deployed site serves HTTPS only, keeps all data after a container restart, and has a documented restore that has been carried out once.
- No secret, invite code, password, or environment-specific URL is committed.

**Executable Commands:**

```powershell
cd backend; python -m pytest tests/unit/test_auth.py tests/unit/test_usage_quota.py tests/integration/test_auth_api.py tests/integration/test_session_isolation.py -q; python -m pytest -q; cd ..
cd frontend; npx vitest run; npx tsc --noEmit; cd ..
docker compose -f compose.prod.yaml config --quiet
./scripts/verify_documentation.ps1
```

## Phase 3 — Try-On Provider Spike

**Status:** Approved by the owner on 2026-11-20. On the same day the owner chose the minimal run (two arms, one repeat) and removed the Gemini arm: neither vendor publishes quantitative quality results, so the choice needs a measurement on the project's own outfits, while Gemini is better suited to placing an already rendered try-on into a scene than to try-on itself (see Out of scope).

**Goal:** Decide, with measured evidence, whether to replace the FASHN VTON v1.5 Hugging Face ZeroGPU Space with FASHN Try-On v1.6 or FLUX VTO, by comparing them on real demo outfits for end-to-end latency, success rate, cost per outfit and blind human ratings. Serves thesis objective 1.2 "Phòng thử đồ trực tuyến". The current Space takes about 37 s per pass and fails on the second pass under the anonymous ZeroGPU quota (`../archive/reports/FASHN_VTON_SPIKE_REPORT.md`). 3D or 360-degree try-on is out of scope (`../01_product/PRD_MVP.md` 3.2).

**Specification files:**

- `../06_features/VIRTUAL_TRYON_SPEC.md` (garment selection, fallback, labels). It changes only if the decision below replaces the provider.
- `../archive/reports/FASHN_VTON_SPIKE_REPORT.md` (current provider baseline).
- `backend/app/services/tryon_service.py` (`_execute_virtual_tryon` garment rule that the spike mirrors).

**Method:**

- Both models are called through fal.ai with one key, and both get the same preset avatar downscaled to at most 1 MP:
  - FASHN Try-On v1.6 (`fal-ai/fashn/tryon/v1.6`): one garment per call, chained top then bottom, as `tryon_service` does.
  - FLUX VTO (`fal-ai/flux-pro/v1/vto`): one call with a left-to-right garment composite and a prompt built only from recorded attributes. fal serves the first VTO version; Black Forest Labs recommends `vto-v2` (2026-07-17), available only on its own API, so the report MUST state that FLUX may score below its latest version.
- Cases are the persisted outfits of the two demo users, plus deterministic fills so each user has at least three upper + bottom cases and, when the wardrobe has dresses, three dress cases: ten cases for the current demo data, 20 rendered images per repeat. The call order alternates per case.
- Latency is measured end to end per outfit, including the final image download. Failed calls and empty responses are recorded, never dropped. Cost estimates use the fal.ai prices read on 2026-11-20.
- Raters (fashion students or the advisor, at least three) score each result 1–5 for garment fidelity, person preservation and realism, and may flag it unacceptable. They receive only the `review/` bundle, where results are labelled A/B by a salted per-case permutation and image files carry only those labels.

**Out of scope:** Gemini image editing that places a finished try-on render into the requested occasion's scene (for example an outdoor cafe in the evening), as an optional, illustrative step after try-on. It needs its own phase after this decision, including a garment-preservation check before and after editing and a privacy note, because personal avatars would be sent to Google.

**Checklist:**

- [x] Add the spike clients and pure helpers (`backend/tests/evaluation/tryon_spike.py`, not imported by the application) and the CLI (`backend/scripts/spike_tryon_providers.py` with `plan`, `run`, `review`, `score`). Output goes to the git-ignored `data/private-tryon-spike/`. The fal key comes only from `FAL_KEY`, is never sent to image CDNs, and is never written to files.
- [x] Add offline tests (`backend/tests/evaluation/test_tryon_spike.py`) for garment selection, prompt, composite, pixel budget, cost formula, chained calls, failures and empty responses recorded without the key, summaries, the blind permutation, and a review bundle that leaks no provider name.
- [x] Run `run --live` once with a funded fal.ai key (one repeat, ten demo cases). Done 2026-11-20 08:11–08:16 UTC: 20/20 renders succeeded, estimated cost $1.75 (FASHN 17 calls, $1.275; FLUX 10 calls, $0.475). Raw results are frozen as `data/fixtures/tryon_spike_raw_v1_20261120.json`. The review bundle re-encodes every result as JPEG at 1024 px height, because the native formats (FASHN PNG 864×1157, FLUX JPEG 736×1024) would unblind raters.
- [x] Collect blind ratings from at least three raters with `review`, then score them with `score`, passing the same raw files to both. Done 2026-11-22: R1 (owner, not blind) and R2, R3 (friends, not fashion specialists), 60 ratings; pseudonymized as `data/fixtures/tryon_spike_ratings_v1_R1.json`, `_R2.json`, `_R3.json`.
- [x] Write `docs/archive/reports/TRYON_PROVIDER_SPIKE_2026-11-22.md` with the score tables, failure list and limitations. Garment fidelity FASHN 3.83 vs FLUX 4.73, realism 4.60 vs 5.00, unacceptable 4/30 vs 0/30; FLUX higher on 8 of 10 cases (sign test p = 0.109, not significant with ten cases).
- [x] Record the decision: on 2026-11-22 the owner chose to switch to FLUX VTO. The provider change, `VIRTUAL_TRYON_SPEC.md` and `ALIGNMENT_BACKLOG.md` T-3 are Phase 4.

**Acceptance criteria:**

- Every reported number states its denominator, model identifiers, hosts, run date, number of repeats and number of failed calls.
- Nothing in the `review/` bundle names a provider, model or host; the mapping is recovered only by `score`.
- No application table or object-storage bucket is written by the spike, and no secret appears in any output file.
- Default verification runs without network access or credentials.

**Executable Commands:**

```powershell
cd backend; python -m pytest tests/evaluation/test_tryon_spike.py -q; cd ..
./scripts/verify_documentation.ps1
```

## Phase 4 — Switch Try-On to FLUX VTO

**Status:** Approved by the owner on 2026-11-22, following the Phase 3 decision.

**Goal:** Make FLUX VTO on fal.ai the application's try-on provider, rendering a whole outfit in one call, so a preset or personal avatar wearing the outfit appears in about 7 s instead of the 37 s per pass and quota failures of the Hugging Face Space. Serves thesis objective 1.2 "Phòng thử đồ trực tuyến". Moodboard fallback, ownership, avatar and privacy rules do not change.

**Specification files:**

- `../06_features/VIRTUAL_TRYON_SPEC.md` (sections 1–4); this phase updates it.
- `../archive/reports/TRYON_PROVIDER_SPIKE_2026-11-22.md` (evidence and limitations).
- `ALIGNMENT_BACKLOG.md` T-3; this phase updates it.

**Checklist:**

- [x] Add an optional whole-outfit provider capability (`OutfitTryOnProviderProtocol`, `OutfitTryOnRequest`, `OutfitGarment` in `backend/app/services/providers.py`). `tryon_service` makes one call when the provider supports it and keeps the garment passes otherwise, so the FASHN adapter still works.
- [x] Add `backend/app/services/flux_vto_provider.py`: person image at most 1 MP, left-to-right garment composite at most about 0.5 MP, attribute-only prompt, the key sent only to fal.ai, fixed user-facing error messages, timeout bounded by `TRYON_TIMEOUT_SECONDS`, WebP output.
- [x] Add `TRYON_PROVIDER=flux`, `FAL_KEY` and `FLUX_VTO_MODEL` settings and `.env.example` entries; the try-on dependency fails with a configuration error when `FAL_KEY` is missing.
- [x] Include the provider model in the render cache key, so switching providers never serves another model's cached render.
- [x] Tests: `backend/tests/unit/test_flux_vto_provider.py`, two integration tests in `backend/tests/integration/test_tryon_api.py` (one outfit call; cache scoped to the model) that fail without the change, and the configuration tests.
- [x] Update `VIRTUAL_TRYON_SPEC.md` and `ALIGNMENT_BACKLOG.md` T-3.
- [x] Check footwear, headwear and layered tops on six demo outfits (`backend/scripts/spike_tryon_extras.py`, `docs/archive/reports/TRYON_EXTRAS_CHECK_2026-11-22.md`); all 12 renders succeeded and the extended renders wore the shoes, hats and both layers. Owner approved rendering them on 2026-11-22.
- [x] Whole-outfit providers wear outerwear over the inner top or a dress, the bottom, the first footwear item and the first headwear accessory, using a grid composite and the provider's multi-garment prompt; other accessories stay as cards. Garment-pass providers keep the previous rule.
- [x] The try-on response lists the worn items in `rendered_item_ids` (`API_CONTRACT.md` 8.1, 8.2). The modal sends every item, lists worn items apart from the cards beside the image, and offers the outer/inner choice only when the render did not wear both. Tests: three integration tests in `test_tryon_api.py`, three unit tests in `test_flux_vto_provider.py`, `frontend/src/__tests__/TryOnModal.test.tsx`, and the updated layering test in `frontend/src/components/TryOnModal.test.tsx`.
- [x] Owner sets `TRYON_PROVIDER=flux` and `FAL_KEY` in the local `.env` (never committed) and renders outfits in the app to confirm the end-to-end path. Confirmed by the owner on 2026-11-22, first with the single-call version on a preset, then with layers and footwear.

**Acceptance criteria:**

- With `TRYON_PROVIDER=flux`, every outfit is rendered with exactly one provider call; a dress outfit never carries a top or bottom, and bags, watches and jewelry are never sent.
- The modal never lists an item as worn that the response did not report in `rendered_item_ids`.
- A provider error, quota error or timeout returns HTTP 200 with the moodboard and `fallback_used=true`.
- No fal key appears in logs, error messages, stored records or requests to image CDNs.
- Default verification runs without network access or credentials.

**Executable Commands:**

```powershell
cd backend; python -m pytest tests/unit/test_flux_vto_provider.py tests/unit/test_config.py tests/integration/test_tryon_api.py -q; cd ..
cd frontend; npx vitest run src/__tests__/TryOnModal.test.tsx src/components/TryOnModal.test.tsx; npx tsc --noEmit; cd ..
./scripts/verify_documentation.ps1
```

## Phase 5 — Gemini Detector with YOLO-World Fallback

**Status:** Approved by the owner on 2026-11-25 (option b of the Phase 1 follow-up): Gemini detector by default, YOLO-World only when Gemini fails, and `gemini-3.5-flash-lite` for attribute extraction subject to one measured run. The run showed a significant formality loss (exact 36/58 vs 44/58, p = 0.021), so on the same day the owner kept `gemini-3.6-flash` for attributes. Complete 2026-11-25.

**Goal:** Split multi-item and flat-lay photos into garments about twice as well as YOLO-World (Phase 1: 16/27 vs 8/27 flat-lay regions) while keeping digitization usable when the Gemini API fails, Attribute extraction stays on `gemini-3.6-flash` (about 11–12 s per photo with the Gemini detector), because the faster model rates formality less accurately. Serves thesis objective 1.2 "Xây dựng tủ đồ số". Recommendation, try-on and the HTTP contract do not change.

**Specification files:**

- `../03_domain/INGESTION_AND_RETRIEVAL_SPEC.md` (detector selection); this phase updates it.
- `../archive/reports/LIVE_INGESTION_EVALUATION_2026-11-25.md` (evidence for the choice).
- `TEST_STRATEGY.md` section 3.2 (live evaluation rules).

**Checklist:**

- [x] Add a fallback detector that calls the primary detector and, only when it raises (provider error, timeout or any other exception), calls a secondary detector once. A primary result with no boxes is a valid answer and MUST NOT trigger the fallback. The secondary detector is created lazily, so the YOLO-World model is loaded only after a Gemini failure. When both fail, the primary error is raised and the existing full-frame manual-review fallback applies. Logs MUST NOT contain provider response bodies or keys.
- [x] Add the `DETECTOR_FALLBACK_BACKEND` setting (`none` default, `yolo_world`). It applies only when the effective detector is Gemini, and it is skipped with a warning when the YOLO-World model file is missing. Code defaults stay `DETECTOR_BACKEND=auto` and no fallback, so offline tests do not change.
- [x] Recommended configuration in `.env.example`: `DETECTOR_FALLBACK_BACKEND=yolo_world`, `VISION_MODEL=gemini-3.6-flash`, `VISION_FALLBACK_MODEL=gemini-3.5-flash-lite` (after the measured run below; initially proposed the other way round), and an explicit `DETECTOR_MODEL=gemini-3.6-flash` (it otherwise follows `VISION_MODEL`). `.env.example` keeps `VISION_PROVIDER=fake` and `DETECTOR_BACKEND=auto` so a fresh checkout runs offline; with `VISION_PROVIDER=gemini`, `auto` selects the Gemini detector.
- [x] Tests (`backend/tests/unit/test_fallback_detector.py`, `backend/tests/integration/test_detector_fallback_ingestion.py`, `test_config.py`): the fallback is used on errors and not on empty results, the secondary is never built when the primary succeeds, both-fail behavior, configuration selection, and the `.env.example` entries.
- [x] Update `INGESTION_AND_RETRIEVAL_SPEC.md`.
- [x] Run Gemini detector + `gemini-3.5-flash-lite` once on set A (58 photos), with a same-day Gemini detector + `gemini-3.6-flash` run, and add the paired comparison to `LIVE_INGESTION_EVALUATION_2026-11-25.md` as an addendum. Done (section 7): 118 calls, 0 failures; all fields equal within run variation except formality exact 36/58 vs 44/58 (p = 0.021); median 5.3 s vs 11.6 s.

**Acceptance criteria:**

- With `DETECTOR_FALLBACK_BACKEND=yolo_world`, a Gemini detector failure produces YOLO-World boxes, not the full-frame fallback, and makes exactly one YOLO-World call.
- A Gemini detector success makes no YOLO-World call and does not load the YOLO-World model.
- The measured run reports provider failures, latency and every attribute metric with its denominator; any attribute that drops beyond the run-to-run variation measured in Phase 1 is stated as a limitation.
- Default verification runs without network access or credentials.

**Executable Commands:**

```powershell
cd backend; python -m pytest tests/unit/test_fallback_detector.py tests/unit/test_config.py tests/integration/test_detector_fallback_ingestion.py -q; python -m pytest -q; cd ..
python backend/scripts/evaluate_live_ingestion.py --score data/fixtures/live_ingestion_attributes_v1_gemini_20261125.json data/fixtures/live_ingestion_attributes_v1_gemini_flash_lite_20261125.json
./scripts/verify_documentation.ps1
```

## Phase 6 — Live Multi-Agent Benchmark (recorded after the fact)

**Status:** Carried out on branch `feat/live-multi-agent-evaluation` between 2026-11-19 and 2026-11-25 without a phase entry, and merged by the owner on 2026-11-25 (PR #21) with two known defects. This entry records its scope and the follow-up fixes; it does not approve further work. Owner decisions are recorded in `../archive/reports/MULTI_AGENT_BENCHMARK_REVIEW_2026-11-25.md` section 2; complete 2026-11-25.

**Goal:** Measure the advisory quality of the five-node multi-agent stylist against simpler baselines and ablations with live Gemini context and explanations and a cross-family LLM judge calibrated against blind human raters. Serves thesis objective 1.2 "Tư vấn phối đồ thông minh" and chapter 7.

**Specification files:**

- `TEST_STRATEGY.md` (Multi-Agent Advisory Benchmark, two-layer framework).
- `../02_architecture/MULTI_AGENT_SPEC.md` section 3 (context provider policy); updated by the follow-up.
- `../03_domain/FASHION_KNOWLEDGE_BASE.md` (comfort and active weight profiles changed by PR #21; owner and advisor decision pending).

**Checklist:**

- [x] Benchmark v3 (56 cases, 38 dev / 18 holdout), judge calibration v2 (20 pointwise, 12 pairwise samples), live run and reports (`../archive/reports/LIVE_MULTI_AGENT_BENCHMARK_2026-11-23.md`, `..._HOLDOUT_2026-11-23.md`, `LIVE_DEV_CHATBOT_ONLY_2026-11-23.md`, `MULTI_AGENT_OFFLINE_BENCHMARK_2026-11-22_v3.md`).
- [x] Blind human calibration with three anonymized raters (`../archive/reports/HUMAN_VS_JUDGE_CALIBRATION_2026-11-25.md`).
- [x] Fix the formality coercion that read `1.0` as level 5 (F-1) and the retries and sleeps of the application context provider inside chat requests (F-2); tests in `backend/tests/unit/test_context_agent.py` and `backend/tests/unit/test_context_provider_chat_policy.py`.
- [x] Record the review findings and reporting caveats (`../archive/reports/MULTI_AGENT_BENCHMARK_REVIEW_2026-11-25.md`).
- [x] Simulate learning from 1–5 star ratings through the real API (`backend/scripts/simulate_rating_personalization.py`, `../archive/reports/RATING_PERSONALIZATION_SIMULATION_2026-11-25.md`): learned weights follow the hidden taste, but rank-1 quality moves only 3.17 → 3.24 stars after 20 ratings (4 better, 0 worse of 63; p = 0.125), because the learned term can shift a composite score by at most ±0.02. A sensitivity run with learned shares 0.20–1.00 improves at most 6 of 63 requests, all for one simulated user, with no context violation, and saturates from 0.60; the owner kept the application weight on 2026-11-25.
- [x] Measure live chat latency without cache (`backend/scripts/measure_live_chat_latency.py`, `../archive/reports/LIVE_CHAT_LATENCY_2026-11-25.md`): p50 2.1 s / p95 4.2 s with explanations off, 4.9 s / 8.7 s with LLM explanations; local agent work about 0.07 s. The run exposed provider timeouts that bounded each httpx phase only (one 199 s context call); fixed with wall-clock deadlines (`backend/app/services/deadline.py`).
- [x] Compare the pre-PR #21 and current comfort/active profiles offline (`backend/scripts/compare_weight_profiles_offline.py`): profile differentiation 2/5 → 5/5 for M-Full, every constraint, structure, functional and stress metric unchanged (review report section 2.1).
- [x] Owner and advisor confirm or revert the comfort and active weight changes; a revert requires a new live run. On 2026-11-25 the owner kept the new weights and informed the advisor with the offline comparison; no objection recorded. Raters R1–R3 are recorded as informed non-experts (review report section 3).

**Acceptance criteria:**

- Every reported metric states its denominator, model identifiers, run date and provider failures; judge figures are reported with their in-sample calibration and within-tier human agreement.
- Default verification runs the offline benchmark without network access or credentials.

**Executable Commands:**

```powershell
cd backend; python -m pytest tests/evaluation/test_multi_agent_benchmark.py tests/unit/test_context_agent.py tests/unit/test_context_provider_chat_policy.py -q; cd ..
python backend/scripts/compare_weight_profiles_offline.py --out data/private-weight-comparison/summary.json
./scripts/verify_documentation.ps1
```

## Phase 7 — Interface Polish Before Deployment

**Status:** Approved by the owner on 2026-11-26 and completed the same day, with the full scope of `../archive/reports/UI_REVIEW_2026-11-26.md` (U-1 to U-13). The inter-agent trace panel stays on the chat page, collapsed by default, under a plain-language title. Recommendation, scoring, and ingestion behavior MUST NOT change in this phase.

**Goal:** Fix the accessibility, copy, and phone-layout issues found by driving the running app, so that pilot users of the public deployment meet a consistent Vietnamese interface. Serves thesis chapter 6.1 "Trải nghiệm người dùng" and the "Hiện thực và Triển khai" chapter.

**Specification files:**

- `../archive/reports/UI_REVIEW_2026-11-26.md` (issue list and locations).
- `../../AGENTS.md` section 3 (UI copy rules: clear Vietnamese, no decorative emoji, accessible labels for functional icons).
- `../05_api/API_CONTRACT.md` section 10 (`PROVIDER_ERROR` copy); updated by this phase.
- `../06_features/VIRTUAL_TRYON_SPEC.md` section 6 (try-on dialog contract).
- `../02_architecture/MULTI_AGENT_SPEC.md` section 7 (explanation format, kept unchanged in the API).

**Checklist:**

- [x] U-1: associate every review-screen label with its control.
- [x] U-2: tap targets of at least 24 px on phones for rating stars, notice close buttons, the remove-photo button, and subtype chips.
- [x] U-3: one `h1` in each step of the add-item flow.
- [x] U-4: remove "AI" from user-facing backend messages (context fallback warning, `PROVIDER_ERROR`, ingestion timeout warnings) and update `API_CONTRACT.md`.
- [x] U-5: replace the text symbols used as icons with icon components.
- [x] U-6: show bracketed garment names in explanations as names, without the brackets; the API text keeps them.
- [x] U-7, U-8: Vietnamese labels for the jacket subtype and the color magenta.
- [x] U-9: collapse the inter-agent trace panel by default and give it a plain-language title.
- [x] U-10: try-on dialog on phones shows the result first; hide the timing and the before/after switch for moodboard results.
- [x] U-11: keep the review-screen save action reachable without scrolling to the end on phones.
- [x] U-12: home query placeholder fits a 390 px screen.
- [x] U-13: distinct labels for the comfort style and the comfort priority.
- [x] Check every item again in the running app at 1280 px and 390 px and record the result in the UI review report.

**Acceptance criteria:**

- The automated checks of the UI review report pass on every main screen at 390 px: no unlabeled fields, no tap target under 24 px, one `h1`, no horizontal overflow.
- No user-facing string outside the spec-mandated try-on labels contains "AI".
- The existing backend and frontend suites pass; recommendation output for the golden scenario is unchanged.

**Executable Commands:**

```powershell
cd backend; python -m pytest -q; cd ..
cd frontend; npx vitest run; npx tsc --noEmit; cd ..
./scripts/verify_documentation.ps1
```

## 4. Roadmap Invariants

- **INVARIANT:** A phase is complete only when every checklist item is complete and every listed command passes.
- **INVARIANT:** A later phase MUST NOT be used to hide a failure in an earlier phase.
- **INVARIANT:** `CURRENT_STATE.md` reflects the actual active phase and latest passing command.
- **INVARIANT:** External API credentials are not required for default phase verification.
- **INVARIANT:** A phase MUST NOT add shopping, affiliate, social-network, or 3D body-scanning features unless the thesis scope is changed first.
