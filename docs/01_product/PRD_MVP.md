# Product Requirements Document — MVP

## 1. Problem Statement

Users spend unnecessary time choosing outfits, forget garments they already own, and often receive generic advice that is not grounded in their real wardrobe. The product digitizes a user's wardrobe, interprets Vietnamese natural-language requests in context, and recommends outfits composed only of items owned by that user.

## 2. Objectives

1. Convert single-item, multi-item, and worn-outfit images into user-confirmed structured wardrobe data.
2. Recommend 1–3 outfits based on occasion, event date/time, location, environment, weather, formality, explicit constraints, and the user's active wardrobe.
3. Apply deterministic, testable fashion-domain rules.
4. Personalize ranking from option-based onboarding, 1–5 ratings, and confirmed wear history.
5. Produce an illustrative, reference-conditioned lookbook with a moodboard fallback.
6. Demonstrate a multi-agent architecture with an explicit workflow, typed shared state, and isolated responsibilities.

## 3. MVP Scope

### 3.1 In Scope

- Digital wardrobe: batch upload, image analysis, item detection/cropping, user confirmation, CRUD, filters, and retrieval.
- Vietnamese conversational input and structured context extraction.
- A fixed multi-agent recommendation pipeline.
- Preference onboarding and 1–5 rating prompts following a 5–10 eligible-outfit cadence.
- Wear history, anti-repetition, and saved outfits.
- Private object storage through MinIO, with a local adapter for automated tests and offline demonstrations.
- Illustrative lookbook generation with a deterministic moodboard fallback.

### 3.2 Out of Scope

- Shopping, affiliate links, and e-commerce marketplace integration.
- Body analysis or inference of sensitive personal attributes.
- Claims of exact garment fit, size, drape, or body-shape simulation.
- Dynamic agent routing, production-grade authentication, and 3D avatars.

## 4. Primary User Flows

### 4.1 Wardrobe Digitization

1. The user uploads one or more images.
2. The system classifies each input as `single_item`, `multi_item`, `worn_outfit`, or `cluttered`.
3. The system proposes item regions, normalized attributes, and per-field confidence.
4. The user MUST confirm, edit, or reject each detected item.
5. Images are stored in private object storage; structured metadata is persisted and indexed for retrieval.

Detailed behavior is defined in `../03_domain/INGESTION_AND_RETRIEVAL_SPEC.md`.

### 4.2 Outfit Request

1. The user submits a natural-language query, for example: `Tối nay đi cafe ngoài trời ở Đà Lạt, hơi lạnh, muốn lịch sự nhẹ`.
2. The system extracts structured context and requests clarification when missing information would materially change the result.
3. Retrieval MUST return items owned by the requesting user only.
4. The Fashion Agent builds valid combinations and applies deterministic scoring.
5. The Personalization Agent reranks the candidates.
6. The Coordinator validates grounding, persists each recommendation, and returns 1–3 outfits with a separate explanation for each outfit.

### 4.3 Rating and Wear History

- The user MAY rate an outfit from 1 to 5 stars.
- The application SHOULD proactively request a rating only after 5–10 eligible outfits, using a non-blocking prompt.
- The user MAY mark an outfit as worn. Only that explicit action updates wear history.

### 4.4 Try-On Lookbook

- The user selects a persisted outfit and requests a lookbook render.
- The service SHOULD provide item reference images to the configured image-generation provider.
- After an 8-second provider timeout or provider failure, the service MUST generate a moodboard fallback.

## 5. User Stories and Acceptance Criteria

| ID | User story | Core acceptance criteria |
| :--- | :--- | :--- |
| US-1 | Upload and digitize wardrobe images | Items MUST NOT persist before confirmation; all supported input kinds MUST follow the ingestion specification |
| US-2 | Manage a digital wardrobe | CRUD, filters, retrieval, and soft delete MUST preserve cross-user isolation |
| US-3 | Request styling advice in Vietnamese | Response contains 1–3 outfits; 100% of item IDs belong to the user's active wardrobe |
| US-4 | Resolve context | Occasion, event date/time, location, environment, weather source, formality, and constraints are captured when available |
| US-5 | Understand recommendations | Every outfit has its own explanation and MUST NOT introduce unowned items |
| US-6 | Configure preferences | Onboarding uses selectable options and MUST support skip and later editing |
| US-7 | Rate recommendations | Rating is 1–5 only; cadence and cooldown MUST follow the feedback specification |
| US-8 | Avoid repetition | An exact outfit confirmed as worn within three days receives a strong ranking penalty |
| US-9 | Save and mark outfits as worn | Recommendation IDs MUST be persisted before subsequent actions are allowed |
| US-10 | View an illustrative try-on | Generated output or fallback SHOULD complete within 10 seconds and MUST identify its render kind |

## 6. Golden Scenario

Test query: `Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?`

The fixture wardrobe contains White Polo, Black Shirt, Graphic Tee, Navy Chinos, Black Trousers, Denim Shorts, White Sneakers, and Brown Oxford Shoes.

Expected behavior:

- Extracted context: `occasion=cafe`, `time_of_day=evening`, `weather_condition=cool`, `target_formality_range=[2,3]`.
- White Polo + Navy Chinos + White Sneakers appears in the top three.
- Every returned item identifier exists in the active test wardrobe.
- Each recommendation has a persisted outfit identifier before the response is returned.

## 7. Acceptance Metrics

| Metric | MVP target |
| :--- | :---: |
| Vision tagging accuracy on acceptable-quality images | >= 85% for category, color, and formality |
| Required context-field F1 | >= 85% |
| Retrieval Recall@10 | >= 90% |
| Wardrobe grounding | 100% |
| Cross-user isolation | 100% |
| Styling response p95 | <= 5 seconds |
| Generated lookbook or moodboard fallback | <= 10 seconds |

The evaluation dataset and commands are defined in `../07_implementation/TEST_STRATEGY.md`.

## 8. Product Invariants

- **INVARIANT:** The system never recommends an item that is not active and owned by the requesting user.
- **INVARIANT:** Viewing an outfit does not imply that the user wore it.
- **INVARIANT:** Like/Dislike feedback is not part of the MVP.
- **INVARIANT:** Generated imagery is labeled as illustrative and is not presented as an exact fit simulation.
