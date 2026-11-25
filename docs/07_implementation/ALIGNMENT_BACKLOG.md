# Alignment Backlog

This file lists known divergences between documents, or between documents and the implementation, that need an owner decision. Agents MUST NOT resolve an item marked **Owner decision** without the user's approval. When an item is resolved, it SHOULD be removed here and the fix recorded in the affected source-of-truth document.

Recorded 2026-11-18, against `main` at the merge of PR #11.

## 1. Thesis (`thesis/tro_ly_phoi_do_thong_minh_multi_agent.md`)

The thesis is the highest-priority source of truth and is the author's academic text. It MUST NOT be edited by an agent without explicit approval.

| ID | Section | Divergence | Owner decision |
| :--- | :--- | :--- | :--- |
| T-1 | 6.1.1 | Reports 417 backend, 75 frontend, and four Chromium E2E tests from the 2026-09-17 acceptance run. The latest recorded runs are 772 backend unit/contract/integration plus 7 evaluation tests (2026-11-18) and 123 frontend tests in 16 files (2026-11-17). Sparse-wardrobe Precision@5 is now 79.00% (metadata) instead of 84.50%, after near-formality widening for sparse categories; Recall@10 is unchanged at 100%. | Keep 6.1.1 as a dated MVP snapshot, or rerun acceptance and replace the figures. |
| T-2 | 6.1.1 | All metrics came from fake providers (`fake-vision-v1`, `deterministic-fallback-v1`, image provider disabled). The application now also runs with Gemini Vision/Context, the YOLO-World detector, and FASHN VTON, A versioned live-provider ingestion evaluation now exists (`../archive/reports/LIVE_INGESTION_EVALUATION_2026-11-19.md`, Phase 1): YOLO-World + Gemini Vision on 58 single-garment photos and 21 annotated real photos. A Vietnamese draft for chapter 7 is in `../archive/reports/CHUONG_7_DANH_GIA_SO_HOA_TU_DO_NHAP_2026-11-19.md`. The Gemini-detector comparison was completed on 2026-11-25 (`../archive/reports/LIVE_INGESTION_EVALUATION_2026-11-25.md`): Gemini localizes 25/47 vs 17/47 annotated garments (flat-lay 16/27 vs 8/27), while attribute accuracy on single-garment photos does not differ significantly between detectors or between `gemini-3.6-flash` and `gemini-3.5-flash-lite`. Try-on was measured live in the Phase 3 spike. A live multi-agent recommendation benchmark exists on the unmerged branch `feat/live-multi-agent-evaluation`; context and recommendation are otherwise measured with fakes. | Decide whether to add the ingestion results to chapter 6.1.1 or a new chapter 7 section, and whether context/recommendation also need live metrics. |
| T-3 | 6.2 | Lists FASHN VTON 2D virtual try-on as a future direction. It is implemented (migration `0013`, `../06_features/VIRTUAL_TRYON_SPEC.md`); since 2026-11-22 the default provider is FLUX VTO on fal.ai (`backend/app/services/flux_vto_provider.py`), chosen by a measured comparison with FASHN Try-On v1.6 (`../archive/reports/TRYON_PROVIDER_SPIKE_2026-11-22.md`), with the FASHN adapter kept. | Move it from 6.2 into the implemented scope (chapters 2.4 and 5) or keep it described as experimental. |
| T-4 | 4.3 | Describes expert fashion knowledge only in general terms. The implementation encodes the advisor's 5-attribute garment profile, 3-tier evaluation, and dynamic weight profiles (`../03_domain/FASHION_KNOWLEDGE_BASE.md`). | Decide whether chapter 4.3 should summarize this model, since it is a core academic contribution. |

## 2. Documentation Rules

| ID | Divergence | Owner decision |
| :--- | :--- | :--- |
| D-1 | `../README.md` requires English except for user-query examples, test queries, and user-facing messages. `../03_domain/FASHION_KNOWLEDGE_BASE.md` is largely Vietnamese. | Allow Vietnamese in domain-knowledge documents, or translate the knowledge base to English. |
| D-2 | `../01_product/PRD_MVP.md` and `TEST_STRATEGY.md` section 4 are scoped to the completed MVP. | When the first upgrade phase changes product requirements, decide whether to extend the PRD in place or start a new PRD version. |

## 3. API Contract (`../05_api/API_CONTRACT.md`)

| ID | Divergence | Owner decision |
| :--- | :--- | :--- |
| A-1 | Section 8.5 specifies `204 No Content` for `DELETE /tryons/avatars/{avatar_id}`. The implementation (`backend/app/api/v1/endpoints/tryons.py`) returns `200` with `{"deleted": true, "avatar_id": ...}`, and the frontend and tests rely on that body. Recorded 2026-11-19. | Change the contract to `200` with this body, or change the endpoint, client, and tests to `204`. |
