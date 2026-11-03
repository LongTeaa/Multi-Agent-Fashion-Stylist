# Clothing Ingestion and Retrieval Specification

New detections retain the raw detector rectangle separately from the effective crop. Automatic margin and manual crop updates MUST NOT overwrite it. Existing detections with no recoverable raw rectangle remain null. Review offers an explicit restore-original-frame action followed by save; it does not change confirmed wardrobe media automatically. Review resumes the valid selected source after reload. Inventory and outfit previews fit the stored image without visually clipping it. These controls do not claim to solve missed-object or face detection.

## 1. Objective

The ingestion system converts clothing images into structured, reviewable `WardrobeItem` records that can be searched and used in outfit generation. It MUST NOT assume that every image contains exactly one item.

## 2. Supported Input Cases

| Input case | Required MVP behavior | Persistence result |
| :--- | :--- | :--- |
| One item on a reasonably clean background | Detect and propose attributes directly | One `WardrobeItem` after confirmation |
| Multiple spatially separated items | Detect each bounding box and produce an item crop | Multiple items sharing one `ingestion_batch_id` |
| A person wearing an outfit | Detect garment regions and request confirmation/crop adjustment | Multiple items when sufficiently clear; otherwise keep the batch in review and request clearer item photos |
| Dense wardrobe/rack with occlusion | MUST NOT auto-persist bulk items | Request closer photos or manual region selection |
| Blurred, dark, or heavily occluded image | Return quality warnings | No item until the user confirms or replaces the image |
| Image containing a person or face | Avoid retaining the face-containing original unless needed for a user-requested feature | Store garment crops and apply original-image retention policy |

## 3. Digitization Pipeline

```text
upload batch
  -> validate file and image quality
  -> object detection / segmentation
  -> classify input: single_item | multi_item | worn_outfit | cluttered
  -> crop each candidate item
  -> extract attributes and per-field confidence through Vision AI
  -> normalize enums and colors
  -> user reviews, edits, accepts, or rejects each candidate
  -> store original/crop/thumbnail through ObjectStorage
  -> persist relational metadata
  -> update the retrieval document/index
```

The system MUST NOT persist a wardrobe item solely from AI output without explicit user confirmation.

Detections MUST retain their original media identifier independently of crop
identifiers. Multi-photo review MUST offer source selection and show regions only
on the matching source. Phone EXIF orientation MUST be normalized before storing
the original and sending it to detection, so displayed and cropped pixels agree.
Crop edits regenerate both crop and thumbnail through
ObjectStorage and remain review-only until explicit confirmation. A matching
pair of footwear is one wardrobe unit; different pairs remain separate. The
detector prompt MUST express this rule; users can enlarge one region to enclose
a pair and reject a duplicate proposal. Live pair-detection accuracy requires
a separate real-image evaluation.

The Gemini adapter MUST request native `box_2d` coordinates in
`[y_min, x_min, y_max, x_max]` order on the 0–1000 grid and convert them once
to the domain's `[x_min, y_min, x_max, y_max]` order on 0–1. A response schema
MUST make the provider format explicit. Ambiguous, out-of-range, reversed,
or degenerate boxes MUST fail validation before cropping; they MUST NOT be
silently rescaled or interpreted as domain coordinates. Explicit legacy
`box` fields remain canonical 0–1 XYXY only. The HTTP/UI contract is unchanged.

Automatic crop policy `isolated-footwear-margin-v1` adds 0.02 of the source
width/height at each edge only when the detector explicitly classifies the photo
as `single_item`, returns exactly one recognized footwear candidate, and reports
confidence >= 0.70. Coordinates are clipped to the source bounds. A matching pair
remains one unit. Scene kinds inferred from box count or a client hint do not
qualify. Worn/multi-item/cluttered scenes, unknown labels and low-confidence
candidates receive no expansion. This conservative guard limits adjacent garment
or face inclusion; it cannot guarantee that a model classified the scene correctly.
The stored/reviewed bounding box, crop, thumbnail and extraction input all use the
same effective rectangle. Explicit crop PATCH coordinates remain exact and never
receive an automatic margin. Existing persisted crops are not rewritten.

Processing clients MUST retain a recoverable batch identifier while the server
is processing; elapsed polling time alone is not a failed ingestion. Consecutive
network failures MAY pause polling, with a resume/reload path. Only terminal
server failure/expiration or explicit cancellation clears recovery state.

## 4. Minimum Retrieval Attributes

- `category`, `sub_category`
- `primary_color`, `secondary_color`
- `pattern`, `material`, `style`, `fit`
- `formality_level`
- `weather_suitability`, `season`, `functional_flags`
- user-confirmed `free_text_tags`
- `is_active`

Every AI-produced field MUST have a confidence value. A field below the configurable default threshold of `0.70` MUST be marked for review.

### Review presentation and reminder cadence

The default review shows the crop, category, specific item type, primary color,
and inclusion toggle. Additional attributes remain editable in a collapsed details
section; its summary MUST indicate uncertain additional fields. High-confidence
percentages and internal identifiers/input-kind enums are not user-facing copy.
Garment length controls are omitted for footwear/accessories without changing
their stored metadata. Explicit save is required for every batch.

The optional onboarding hint appears for upload ordinals 1, 2, 14, 26, and so on:
the first two batches, then every twelve further confirmed batches. The backend
derives eligibility from confirmed batches owned by the same user, excluding the
current batch. Failed, expired, pending, and duplicate confirmation retries do not
advance the count. Repeated review GETs do not mutate cadence. This policy is
independent of outfit-rating cadence. Current quality failures and uncertain fields
MUST remain visible regardless of hint eligibility. Provider diagnostics MUST be
mapped to concise Vietnamese guidance rather than rendered as raw provider text.

## 5. Search-Intent Extraction

The Context Agent converts a natural-language prompt into a structured `SearchIntent`.

Example user query: `Tối nay đi cafe ngoài trời ở Đà Lạt, hơi lạnh, muốn lịch sự nhẹ`.

| Field | Extracted value |
| :--- | :--- |
| `occasion` | `cafe` |
| `time_of_day` | `evening` |
| `event_date` | Current date in the user's timezone |
| `location_text` | `Đà Lạt` |
| `environment` | `outdoor` |
| `weather_condition` | `cold` |
| `target_formality_range` | `[2,3]` |
| `style_hints` | `smart_casual` |
| `must_have` | Empty |
| `must_avoid` | Empty |
| `weather_source` | `user` |

Extraction SHOULD use structured LLM output. If the provider fails, a rule-based parser MAY support common Vietnamese expressions. An uncertain field MUST remain `null` or carry low confidence; it MUST NOT be fabricated.

## 6. Hybrid Retrieval Policy

Metadata is the mandatory MVP baseline because a personal wardrobe is usually small:

1. Apply hard filters: matching `user_id`, `is_active=true`, and required categories.
2. Apply constraints: `must_have`, `must_avoid`, weather, and formality, with controlled relaxation.
3. Compute metadata score from color, style, formality, and weather.
4. MAY add full-text or semantic score for free descriptions such as `nhẹ nhàng`, `retro`, or `không quá công sở`.
5. Merge scores and retain at most 15 items per category.

The executable metadata baseline uses applicable-signal normalization with weights
`style=0.30`, `color=0.25`, `formality=0.25`, and `weather=0.20`. When no ranking hint
is present, the neutral metadata score is `0.50`. `must_avoid` and `must_have` are not
relaxed. If a required category has no result, weather is relaxed first and formality
second, and every relaxation MUST be reported with the candidate result.

Optional full-text ranking tokenizes the normalized retrieval document and query. When
enabled with a non-empty text query, the merged score is `0.80 * metadata_score + 0.20 *
full_text_score`; otherwise ranking remains metadata-only. Ties MUST use the persisted
item identifier for deterministic ordering.

A vector database MUST NOT be required in Phases 1–4. Semantic indexing MAY be enabled only if evaluation proves that metadata/full-text retrieval is insufficient. When enabled, create/update/delete operations MUST update the semantic index transactionally or through a recoverable outbox.

## 7. Retrieval Evaluation

The project MUST include at least 30 Vietnamese queries with human-labeled relevant wardrobe items.

| Metric | MVP target |
| :--- | :---: |
| Required context-field exact/F1 | >= 0.85 |
| Relevant-item Recall@10 | >= 0.90 |
| Sparse-wardrobe Precision@5 | >= 0.75 |
| Cross-user leakage | 0 records |
| Search p95 with 500 items | < 300 ms, excluding LLM extraction |

Evaluation MUST compare metadata-only, metadata + full-text, and hybrid semantic configurations. Semantic search SHOULD be retained only if it produces a meaningful Recall@10 improvement on the fixed evaluation set.

Because a filtered personal wardrobe may contain fewer than five eligible candidates,
the executable `sparse-wardrobe-v1` metric defines Precision@5 as `relevant results in
the first min(5, N) positions / min(5, N)`, where `N` is the complete number of
candidates returned after ownership, active-state, category, and explicit-constraint
filtering. Returning fewer candidates MUST NOT improve the score: retrieval evaluates
the complete bounded candidate pool, not an arbitrary display truncation. For
transparency, reports MUST also include fixed-denominator Precision@5, calculated as
`relevant results in the first five positions / 5`, as a diagnostic that is not used as
the sparse-wardrobe quality gate. Queries with no labeled relevant item are excluded
from the fixed-denominator diagnostic because precision is undefined for them. Such a
query scores `1.0` in the sparse-wardrobe metric only when retrieval also returns no
candidate.

The versioned `retrieval-v1` evaluation contains 30 Vietnamese queries across five
synthetic wardrobes. The recorded `metadata-v1` result is Recall@10 `1.000` and
Sparse-wardrobe Precision@5 `0.845` for metadata-only retrieval, and Recall@10 `1.000`
and sparse-wardrobe Precision@5 `0.8783` with optional full-text ranking. The respective
fixed-denominator diagnostic values are `0.6000` and `0.6345`. Search p95 with 500 items
is `100.838 ms` in the local SQLite evaluation. Because both non-semantic configurations
meet the normative sparse-wardrobe targets, semantic indexing is not justified for the
current dataset and MUST remain disabled.

## 8. Ingestion and Retrieval Invariants

### Inventory display and search

The executable display catalog is `backend/app/services/garment_taxonomy.py`, exposed through the wardrobe taxonomy endpoint. Inventory filters and ingestion choices MUST share it. Display groups distinguish pants, skirts, shoes, and sandals without changing outfit composition roles. Alias resolution is category scoped; unknown custom bottom/footwear subtypes MUST NOT be guessed into a specific group.

Inventory text search uses deterministic longest-phrase alias parsing with case/accent folding, group/type/color constraints, then metadata token/prefix matching. Multiple terms use AND. This search is separate from stylist candidate retrieval and does not introduce semantic indexing. The MVP implementation evaluates text/group matching over the requesting user's SQL-filtered active, confirmed wardrobe, then paginates. Larger wardrobes require a measured normalized index before expanding this approach.

- **INVARIANT:** Every confirmed item is traceable to its ingestion batch and media asset.
- **INVARIANT:** No unconfirmed detection is visible as an active wardrobe item.
- **INVARIANT:** Retrieval never returns an item owned by another user.
- **INVARIANT:** Soft-deleted items are removed from all active retrieval paths.
