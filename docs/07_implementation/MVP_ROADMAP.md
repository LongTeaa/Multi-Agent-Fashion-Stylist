# MVP Implementation Roadmap

A task MAY be checked only after its specified verification passes. A later phase MUST NOT be used to hide a failure in an earlier phase. All commands below are executed from the repository root.

## Phase 1 — Scaffold, Database, and Object Storage

Specification files:

- `../02_architecture/SYSTEM_ARCHITECTURE.md`
- `../04_data/DATA_SCHEMA.md`
- `../04_data/OBJECT_STORAGE_SPEC.md`
- `TEST_STRATEGY.md`, Phase 1

- [x] Initialize Next.js and FastAPI using the normative source tree.
- [x] Add `.env.example`, `.gitignore`, and typed settings.
- [x] Implement SQLModel tables and migrations for all MVP entities.
- [x] Implement the `ObjectStorage` interface, local adapter, and MinIO adapter.
- [x] Provide Docker Compose for local MinIO when that adapter is enabled.
- [ ] Add an idempotent seed command for one test user and the eight-item golden wardrobe.
- [ ] Add database invariant, storage contract, and seed tests.

Verification MUST assert schema creation, exactly eight golden items after repeated seeding, and common behavior across storage adapters.

**Executable Command:**

```powershell
pytest backend/tests/contract/test_database_schema.py backend/tests/contract/test_object_storage.py backend/tests/integration/test_seed_data.py -q
```

## Phase 2 — Ingestion and Wardrobe Digitization

Specification files:

- `../03_domain/INGESTION_AND_RETRIEVAL_SPEC.md`
- `../04_data/OBJECT_STORAGE_SPEC.md`
- `../05_api/API_CONTRACT.md`, Ingestion API
- `TEST_STRATEGY.md`, Phase 2

- [ ] Implement batch upload, MIME/size/pixel validation, and private object persistence.
- [ ] Classify `single_item`, `multi_item`, `worn_outfit`, and `cluttered` inputs.
- [ ] Detect/crop items and extract structured Vision attributes.
- [ ] Persist confidence and warnings; MUST NOT auto-confirm an item.
- [ ] Build the review UI for editing or rejecting each detection.
- [ ] Make confirmation idempotent and remove unconfirmed assets after 24 hours.
- [ ] Test normal, low-quality, malformed, timeout, and provider-error behavior.

Verification MUST demonstrate that a multi-item image can produce two separately confirmed wardrobe items without exposing the original object publicly.

**Executable Command:**

```powershell
pytest backend/tests/unit/test_upload_validation.py backend/tests/unit/test_vision_normalization.py backend/tests/integration/test_ingestion_flow.py backend/tests/integration/test_ingestion_cleanup.py -q
```

## Phase 3 — Wardrobe, Profile, and Retrieval

Specification files:

- `../03_domain/INGESTION_AND_RETRIEVAL_SPEC.md`
- `../06_features/PERSONALIZATION_AND_FEEDBACK_SPEC.md`
- `../05_api/API_CONTRACT.md`, Wardrobe and Profile APIs
- `TEST_STRATEGY.md`, Phase 3

- [ ] Implement wardrobe CRUD, filters, retrieval, and authenticated media URLs.
- [ ] Refresh retrieval documents after confirmation, update, and delete.
- [ ] Implement option-based profile onboarding and editing.
- [ ] Implement metadata retrieval and optional full-text ranking.
- [ ] Evaluate 30 labeled queries; add semantic indexing only if the benchmark justifies it.
- [ ] Verify cross-user isolation for database and media access.

Verification MUST meet Recall@10 and Precision@5 targets and MUST prove that unconfirmed, deleted, or cross-user items are excluded.

**Executable Command:**

```powershell
pytest backend/tests/unit/test_retrieval.py backend/tests/integration/test_wardrobe_api.py backend/tests/integration/test_profile_api.py backend/tests/evaluation/test_retrieval_metrics.py -q
```

## Phase 4 — Multi-Agent Recommendation

Specification files:

- `../02_architecture/MULTI_AGENT_SPEC.md`
- `../03_domain/FASHION_KNOWLEDGE_BASE.md`
- `../05_api/API_CONTRACT.md`, Stylist Chat API
- `TEST_STRATEGY.md`, Phase 4

- [ ] Implement typed shared state and the fixed LangGraph workflow.
- [ ] Implement Context Agent fields for occasion, date/time, location, environment, weather source, formality, and explicit constraints.
- [ ] Implement Wardrobe Agent retrieval, including the `dress` branch.
- [ ] Implement deterministic Fashion Agent scoring and bounded top-k generation.
- [ ] Implement Personalization Agent cold-start and reranking behavior.
- [ ] Implement Coordinator grounding, per-outfit Vietnamese explanation, and transactional persistence.
- [ ] Implement API mapping and clarification behavior.
- [ ] Add node unit tests, scoring tests, graph tests, and the golden scenario.

Verification MUST place White Polo + Navy Chinos + White Sneakers in the top three for `Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?`, with 100% grounding and persisted outfit IDs.

**Executable Command:**

```powershell
pytest backend/tests/unit/test_context_agent.py backend/tests/unit/test_fashion_scoring.py backend/tests/unit/test_personalization.py backend/tests/unit/test_grounding.py backend/tests/integration/test_stylist_graph.py backend/tests/integration/test_golden_scenario.py -q
```

## Phase 5 — Chat UI, Saved Outfits, Rating, and Wear History

Specification files:

- `../01_product/PRD_MVP.md`
- `../06_features/PERSONALIZATION_AND_FEEDBACK_SPEC.md`
- `../05_api/API_CONTRACT.md`, Outfit Actions API
- `TEST_STRATEGY.md`, Phase 5

- [ ] Build chat UI with loading, clarification, empty, and error states.
- [ ] Build outfit cards with items, scores, and Vietnamese explanations.
- [ ] Implement saved-outfit list and bookmark action.
- [ ] Implement the `Đã mặc` action and wear-history update.
- [ ] Implement 1–5 rating; MUST NOT implement Like/Dislike.
- [ ] Implement 5–10 outfit cadence, dismissal cooldown, and non-blocking Vietnamese prompt.
- [ ] Inject deterministic time and threshold selection into tests.

Verification MUST prove that rating is not requested after every response, duplicates/errors do not increment cadence, and an accepted rating affects reranking within configured bounds.

**Executable Commands:**

```powershell
pytest backend/tests/unit/test_feedback_cadence.py backend/tests/integration/test_outfit_actions_api.py -q
npm --prefix frontend run test -- --run
```

## Phase 6 — Illustrative Lookbook

Specification files:

- `../06_features/VIRTUAL_TRYON_SPEC.md`
- `../04_data/OBJECT_STORAGE_SPEC.md`
- `../05_api/API_CONTRACT.md`, Try-On and Media APIs
- `TEST_STRATEGY.md`, Phase 6

- [ ] Implement an image-provider interface and configurable model identifier.
- [ ] Supply item reference images when supported.
- [ ] Apply an 8-second timeout and generate a moodboard fallback without requiring transparent PNG input.
- [ ] Persist private render assets and benchmark metadata.
- [ ] Build a responsive modal with render-kind labels and ownership protection.

Verification MUST prove that disabling or timing out the image provider returns a private moodboard within the fallback budget and that another user cannot access it.

**Executable Commands:**

```powershell
pytest backend/tests/unit/test_tryon_prompt.py backend/tests/unit/test_moodboard.py backend/tests/integration/test_tryon_api.py backend/tests/contract/test_media_access.py -q
npm --prefix frontend run test -- --run
```

## Phase 7 — Evaluation and Acceptance

Specification files:

- `TEST_STRATEGY.md`
- `../01_product/PRD_MVP.md`, Acceptance Metrics

- [ ] Finalize the fixed fixture and evaluation dataset.
- [ ] Run all unit, contract, integration, frontend, and browser E2E tests.
- [ ] Measure Vision accuracy, Context F1, Recall@10, grounding, isolation, and latency.
- [ ] Verify 375 px responsive behavior and baseline accessibility.
- [ ] Record dataset, rule-set, and optional live provider/model versions in the thesis results.

Final verification MUST complete upload -> confirmation -> retrieval -> chat -> persistence -> save/worn -> cadence rating -> try-on/fallback with all MVP quality gates satisfied.

**Executable Commands:**

```powershell
pytest backend/tests -q -m "not live_provider"
npm --prefix frontend run test -- --run
npm --prefix frontend run test:e2e
```

## Roadmap Invariants

- **INVARIANT:** A phase is complete only when every checklist item is complete and every listed command passes.
- **INVARIANT:** `CURRENT_STATE.md` reflects the actual active phase and latest passing command.
- **INVARIANT:** External API credentials are not required for default phase verification.
