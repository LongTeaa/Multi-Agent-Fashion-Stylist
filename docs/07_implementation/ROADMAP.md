# Implementation Roadmap

This is the active roadmap. The completed MVP roadmap (Phases 1–7) is archived at `../archive/MVP_ROADMAP.md`, and the completed advisor-feedback integration plan at `../archive/KE_HOACH_TICH_HOP_GOP_Y_GIANG_VIEN.md`. Archived roadmaps MUST NOT be reopened; follow-up work MUST be added here as a new phase.

## 1. Status

| Field | Value |
| :--- | :--- |
| Baseline | MVP Phases 1–7 and advisor stages 1–6 complete; `main` at the merge of PR #11 |
| Active phases | Phase 1 — Live-Provider Ingestion Evaluation (approved 2026-11-19; only the Gemini-detector rerun remains). Phase 2 — Public Deployment (approved 2026-11-20). Phase 3 — Try-On Provider Spike (approved 2026-11-20). |
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
- [ ] Rerun the Gemini detector on sets A, B and C with sufficient quota and add the comparison to the report. The 2026-11-19 run failed on 54/58 attribute and 21/21 localization detector requests (HTTP 429 daily quota, 503, timeouts) and is kept only as failure evidence.
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
- [ ] Collect blind ratings from at least three raters with `review`, then score them with `score`, passing the same raw files to both.
- [ ] Write `docs/archive/reports/TRYON_PROVIDER_SPIKE_<date>.md` with the score tables, failure list, example images and limitations (preset avatars only; garment crops, not product photos; both models measured through fal.ai; FLUX VTO v1, not v2).
- [ ] Record the decision (keep the Space, switch to FASHN v1.6, or switch to FLUX VTO). If the provider changes, update `VIRTUAL_TRYON_SPEC.md` and `ALIGNMENT_BACKLOG.md` T-3 in that follow-up task.

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

## 4. Roadmap Invariants

- **INVARIANT:** A phase is complete only when every checklist item is complete and every listed command passes.
- **INVARIANT:** A later phase MUST NOT be used to hide a failure in an earlier phase.
- **INVARIANT:** `CURRENT_STATE.md` reflects the actual active phase and latest passing command.
- **INVARIANT:** External API credentials are not required for default phase verification.
- **INVARIANT:** A phase MUST NOT add shopping, affiliate, social-network, or 3D body-scanning features unless the thesis scope is changed first.
