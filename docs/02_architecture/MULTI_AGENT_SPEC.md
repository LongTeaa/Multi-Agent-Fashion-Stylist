# Multi-Agent System Specification — MVP

## 1. Orchestration

```text
Context Agent
    -> Wardrobe Agent
    -> Fashion Agent
    -> Personalization Agent
    -> Coordinator
    -> API response
```

The Try-On Agent runs on demand through a separate API operation. Vision analysis belongs to the ingestion service and is not a node in the recommendation graph.

Each node MUST receive the typed shared state and MUST return only the fields it owns. Every node MUST define normal, empty, and error behavior.

## 2. Shared State Contract

| Field | Owner | Meaning |
| :--- | :--- | :--- |
| `request_id`, `user_id`, `user_query` | API entry | Immutable request input |
| `context` | Context Agent | Normalized situational context |
| `candidate_pool` | Wardrobe Agent | Retrieved active wardrobe items |
| `evaluated_outfits` | Fashion Agent | Valid combinations and deterministic domain scores |
| `ranked_outfits` | Personalization Agent | Top 1–3 reranked outfits |
| `recommendation_ids` | Coordinator | Persisted outfit identifiers |
| `grounding_validated` | Coordinator | MUST be true before a successful response |
| `feedback_prompt_eligible` | Coordinator/service | Feedback-cadence decision |
| `feedback_target_outfit_id` | Coordinator/service | Nullable outfit selected for a rating prompt |
| `errors`, `warnings` | Producing node | Machine-readable failures and UX warnings |

Executable schema definitions MUST live only in `backend/app/agents/state.py`. This table is the normative contract and is not implementation code.

## 3. Context Agent

Context includes more than weather. The normalized output MUST support:

| Field | Required | Example |
| :--- | :---: | :--- |
| `occasion` | Yes | `cafe`, `interview`, `wedding`, `daily_work` |
| `time_of_day` | Yes | `morning`, `afternoon`, `evening`, `night` |
| `event_date` | No | ISO date inferred from `hôm nay` or `ngày mai` in the user's timezone |
| `location_text` | No | `Đà Lạt` |
| `environment` | No | `indoor`, `outdoor`, `mixed` |
| `weather_condition` | Yes | `hot`, `warm`, `cool`, `cold`, `rainy` |
| `temperature_celsius` | No | `18` |
| `target_formality_range` | Yes | `[2,3]` |
| `style_hints` | No | `minimalist`, `smart_casual` |
| `vibe_keywords` | No | `thoải mái`, `thanh lịch` |
| `must_have`, `must_avoid` | No | `không mặc màu đen` |
| `weather_source` | Yes | `user`, `api`, `default` |
| `needs_clarification` | Yes | Boolean |

User-provided facts MUST take precedence. A weather API MAY enrich context only when location and event timing are sufficiently precise; it MUST NOT silently override user-provided weather.

For an underspecified query such as `Mặc gì?`, the agent MAY apply documented safe defaults but MUST lower confidence. It SHOULD request clarification when ambiguity would materially change formality or garment selection.

## 4. Wardrobe Agent

- The agent MUST read only items with matching `user_id` and `is_active=true`.
- It MUST NOT create, modify, or hallucinate an item.
- It MUST consume the structured search intent and execute the retrieval policy in `../03_domain/INGESTION_AND_RETRIEVAL_SPEC.md`.
- It MUST return separate pools for `tops`, `bottoms`, `dresses`, `footwear`, `outerwear`, and `accessories`.
- It SHOULD cap each ranked category at 15 items.
- If a mandatory slot is missing, it MAY relax weather/formality constraints according to configuration and MUST emit a warning.

## 5. Fashion Agent

The agent MUST generate these two valid outfit branches:

```text
top + bottom + footwear [+ outerwear] [+ accessory]
dress + footwear [+ outerwear] [+ accessory]
```

Item selection and scoring MUST be deterministic. An LLM MUST NOT select item IDs. It MAY produce natural-language rationale for an already selected top-k candidate only.

Normative score:

```text
0.30 color
+ 0.20 style
+ 0.20 formality
+ 0.20 weather/environment
+ 0.10 pattern/proportion
```

Lookup tables, penalties, and tie-break rules are defined in `../03_domain/FASHION_KNOWLEDGE_BASE.md`.

## 6. Personalization Agent

- It MUST rerank no more than five fashion candidates into a top 1–3 result.
- It MUST use onboarding weights, rating affinity, explicit exclusions, and confirmed wear history.
- It MUST apply a strong penalty to an exact outfit confirmed as worn within three days.
- It SHOULD apply a smaller penalty to a major item confirmed as worn within 48 hours.
- It MUST NOT infer sensitive traits or body characteristics.

The complete policy is defined in `../06_features/PERSONALIZATION_AND_FEEDBACK_SPEC.md`.

## 7. Coordinator

The Coordinator MUST execute these steps in order:

1. Validate every item ID against the candidate pool and current database ownership.
2. Validate outfit completeness, including the `dress` branch.
3. Produce a separate Vietnamese user-facing explanation for each outfit without introducing new items.
4. Persist `outfit_recommendations` and `outfit_items` in one transaction.
5. Evaluate feedback cadence after persistence.
6. Map shared state to the response defined by `../05_api/API_CONTRACT.md`.

If grounding fails, no recommendation MAY be persisted.

## 8. Try-On Agent

- It MUST accept only a persisted `outfit_id` owned by the requesting user.
- It MUST obtain item reference images through `ObjectStorage`.
- It SHOULD use an image provider that supports reference-image inputs.
- It MUST apply an 8-second provider timeout and then attempt a moodboard fallback.
- It MUST NOT claim body-fit accuracy.

## 9. Empty and Error Behavior

| Case | Required result |
| :--- | :--- |
| Empty wardrobe | Return `WARDROBE_EMPTY` with user-facing message `Tủ đồ của bạn chưa có trang phục. Hãy thêm quần áo trước nhé.` |
| Missing required outfit slot | Return `NO_COMPLETE_OUTFIT`; never invent an item |
| Materially ambiguous query | Set `needs_clarification=true` and return one concise Vietnamese clarification question |
| External provider failure | Execute the defined fallback or return a normalized provider error |
| Missing user profile | Use a neutral personalization score |

## 10. Agent Invariants

- **INVARIANT:** Only the Wardrobe Agent supplies candidate wardrobe item identifiers.
- **INVARIANT:** Only the Coordinator persists recommendations.
- **INVARIANT:** Try-on never runs inside the recommendation graph.
- **INVARIANT:** An error state cannot also produce a successful recommendation payload.
