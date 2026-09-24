# MVP Test Strategy

## 1. Purpose and Test Stack

Every implementation phase MUST end with executable automated verification. Default automated tests MUST NOT call billable or nondeterministic external AI services.

| Layer | Required tooling | Scope |
| :--- | :--- | :--- |
| Backend unit/contract/integration | `pytest`, `pytest-asyncio`, FastAPI `TestClient`/`httpx` | Domain logic, schemas, repositories, API, agent graph |
| HTTP provider mocking | `respx` or provider-interface fakes | Weather and remote service failure behavior |
| Frontend unit/component | Vitest + React Testing Library | Hooks, components, cadence UI, accessibility |
| Browser E2E | Playwright | Golden user journeys and responsive behavior |
| Evaluation | `pytest`-driven fixed fixtures | Vision, context, retrieval, ranking metrics |

## 2. Required Test Layout

```text
backend/tests/
├── conftest.py
├── unit/
├── contract/
├── integration/
├── e2e/
└── evaluation/
frontend/src/**/*.test.ts(x)
frontend/e2e/
data/fixtures/
```

Shared fixtures MUST include an isolated temporary SQLite database, a temporary local object store, two distinct users, the eight-item golden wardrobe, and deterministic provider fakes.

## 3. Provider Mock Strategy

### 3.1 LLM and Context Extraction

- Default tests MUST inject `FakeLLMProvider`; they MUST NOT patch SDK internals.
- The fake MUST support: valid structured response, malformed response, timeout, provider error, and low-confidence/clarification response.
- Fixed mappings MUST include Vietnamese queries such as `Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?` and `Mặc gì?`.
- A small opt-in live smoke test MAY exist under `@pytest.mark.live_provider`; CI and phase verification MUST exclude it.

### 3.2 Vision and Detection

- Default tests MUST inject `FakeVisionProvider` and `FakeDetector` fixtures with stored outputs for single-item, multi-item, worn-outfit, cluttered, low-quality, malformed, and timeout cases.
- Assertions MUST use fixture bounding boxes, confidence, and normalized attributes rather than comparing generative prose.
- A live-provider evaluation MAY run manually against the fixed image set, but MUST NOT gate normal development.

### 3.3 Weather

- Tests SHOULD mock HTTP at the service boundary with `respx` or inject `FakeWeatherProvider`.
- Fixtures MUST cover successful lookup, timeout, unknown location, and conflict with user-provided weather.
- User-provided weather MUST win over provider data.

### 3.4 Object Storage and Image Generation

- Fast unit/integration tests MUST use `LocalObjectStorage` rooted in a temporary directory.
- Contract tests MUST run the same behavioral suite against local storage and an ephemeral MinIO instance when available.
- `FakeImageProvider` MUST return deterministic image bytes and MUST support timeout/error modes.
- Moodboard tests SHOULD compare dimensions, format, and included asset identifiers; brittle pixel-perfect snapshots SHOULD NOT be the only assertion.

### 3.5 Time and Randomness

- Feedback cadence and anti-repetition MUST receive an injectable clock and threshold chooser.
- Tests MUST use fixed time and deterministic thresholds. They MUST NOT depend on wall-clock time or unseeded randomness.

## 4. Phase Verification Matrix

All commands are executed from the repository root.

| Phase | Target test files | Mock/isolation strategy | Core assertions | Executable command |
| :---: | :--- | :--- | :--- | :--- |
| 1 | `backend/tests/contract/test_database_schema.py`; `backend/tests/contract/test_object_storage.py`; `backend/tests/integration/test_seed_data.py` | Temporary SQLite; temporary local storage; optional ephemeral MinIO; no AI providers | Tables/indexes exist; relational invariants reject cross-user links; storage adapters share behavior; private-key convention; seed is idempotent and creates exactly eight golden items | `pytest backend/tests/contract/test_database_schema.py backend/tests/contract/test_object_storage.py backend/tests/integration/test_seed_data.py -q` |
| 2 | `backend/tests/unit/test_upload_validation.py`; `backend/tests/unit/test_vision_normalization.py`; `backend/tests/integration/test_ingestion_flow.py`; `backend/tests/integration/test_ingestion_cleanup.py` | FakeDetector/FakeVisionProvider; temporary storage/DB; fixed clock | MIME/size/pixel rejection; all input kinds classified; low-confidence fields flagged; no item before confirmation; confirmation idempotent; temp assets removed after 24 hours; provider failure permits manual review | `pytest backend/tests/unit/test_upload_validation.py backend/tests/unit/test_vision_normalization.py backend/tests/integration/test_ingestion_flow.py backend/tests/integration/test_ingestion_cleanup.py -q` |
| 3 | `backend/tests/unit/test_retrieval.py`; `backend/tests/integration/test_wardrobe_api.py`; `backend/tests/integration/test_profile_api.py`; `backend/tests/evaluation/test_retrieval_metrics.py` | Two-user SQLite fixture; local storage; fixed 30-query relevance set; no LLM required | CRUD updates retrieval state; soft-deleted/unconfirmed items excluded; cross-user results absent; preference options validate; Recall@10 >= 0.90 and sparse-wardrobe Precision@5 >= 0.75; fixed-denominator Precision@5 reported diagnostically | `pytest backend/tests/unit/test_retrieval.py backend/tests/integration/test_wardrobe_api.py backend/tests/integration/test_profile_api.py backend/tests/evaluation/test_retrieval_metrics.py -q` |
| 4 | `backend/tests/unit/test_context_agent.py`; `backend/tests/unit/test_fashion_scoring.py`; `backend/tests/unit/test_personalization.py`; `backend/tests/unit/test_grounding.py`; `backend/tests/integration/test_stylist_graph.py`; `backend/tests/integration/test_golden_scenario.py` | FakeLLMProvider; FakeWeatherProvider; fixed clock; deterministic wardrobe/profile fixtures | Context fields and precedence correct; `Mặc gì?` clarifies/defaults correctly; both outfit branches valid; scores in `[0,1]`; deterministic tie-break; no invented IDs; coordinator persists atomically; golden outfit is top 3 | `pytest backend/tests/unit/test_context_agent.py backend/tests/unit/test_fashion_scoring.py backend/tests/unit/test_personalization.py backend/tests/unit/test_grounding.py backend/tests/integration/test_stylist_graph.py backend/tests/integration/test_golden_scenario.py -q` |
| 5 | `backend/tests/unit/test_feedback_cadence.py`; `backend/tests/integration/test_outfit_actions_api.py`; `frontend/src/components/OutfitCard.test.tsx`; `frontend/src/components/RatingPrompt.test.tsx`; `frontend/src/hooks/useStylistChat.test.ts` | Injected threshold chooser/clock; API mocks in frontend; two-user fixtures | Rating integer 1–5 only; threshold 5–10; duplicates/errors do not increment; dismissal cooldown; rating target is persisted/unrated/owned; bookmark and worn behavior matches the API contract; no Like/Dislike controls; Vietnamese prompt renders accessibly | Run both Phase 5 commands in `MVP_ROADMAP.md` |
| 6 | `backend/tests/unit/test_tryon_prompt.py`; `backend/tests/unit/test_moodboard.py`; `backend/tests/integration/test_tryon_api.py`; `backend/tests/contract/test_media_access.py`; `frontend/src/components/TryOnModal.test.tsx` | FakeImageProvider success/timeout/error; temporary storage; deterministic image fixtures; API mocks | Prompt includes only outfit items; timeout triggers fallback; fallback returns 200 and `fallback_used=true`; both failures return 504; cross-user render/media access denied; Vietnamese render-kind labels are correct | Run both Phase 6 commands in `MVP_ROADMAP.md` |
| 7 | Entire backend suite; entire frontend suite; `frontend/e2e/golden-scenario.spec.ts`; `frontend/e2e/responsive.spec.ts`; evaluation suite | All external providers fake by default; optional live-provider marker executed separately; Playwright uses seeded local environment | All prior assertions; context F1 >= 0.85; vision target >= 0.85 on acceptable fixtures; grounding/isolation 100%; p95 budgets; complete upload-to-rating-to-try-on flow; 375 px usability | Run all Phase 7 commands in `MVP_ROADMAP.md` |

## 5. Additional Assertion Requirements

### Schema and API Consistency

- Contract tests MUST compare OpenAPI route/method presence with `docs/05_api/API_CONTRACT.md`.
- Response serializers MUST assert exact required fields for stylist context, recommendation, feedback cadence, try-on, and errors.
- `outfit_id` returned by `/stylist/chat` MUST be retrievable immediately through `/outfits/{outfit_id}`.

### Ownership and Grounding

- Every private endpoint MUST include a negative test using User B against User A's entity.
- Grounding tests MUST assert both candidate-pool membership and current database ownership.
- A grounding failure MUST assert transaction rollback and zero persisted recommendations.

### Failure and Fallback

- Each external provider MUST have success, timeout, and error tests.
- Tests MUST distinguish an application error from a successful fallback.
- Vietnamese user-facing error messages MUST match the API contract exactly where marked normative.

## 6. Evaluation Dataset

The minimum fixed evaluation set MUST contain:

- 20 acceptable-quality single-item images.
- 10 multi-item, worn-outfit, cluttered, or low-quality images.
- 30 Vietnamese queries with labeled context and relevant items.
- Five synthetic wardrobes, including a small wardrobe and a wardrobe containing dresses.
- Three distinct onboarding profiles.

Datasets MUST be versioned. Reports MUST record dataset version, rule version, provider/model version for optional live runs, and execution timestamp.

## 7. Quality Gates

- **INVARIANT:** Phase completion requires its executable command to pass.
- **INVARIANT:** Normal CI never requires external API credentials.
- **INVARIANT:** A test cannot pass by weakening ownership, grounding, or schema assertions.
- **INVARIANT:** A live-provider smoke test is informative and MUST NOT replace deterministic tests.
