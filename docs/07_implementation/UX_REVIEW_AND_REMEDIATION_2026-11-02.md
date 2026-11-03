# UX Review and Remediation Draft — 2026-11-02

> Historical proposal below is preserved. Implemented scope and acceptance are recorded in the closure addendum and `REVIEW_CLOSURE_2026-11-03.md`.

This follow-up records the user's five UI test observations and four screenshots. It supplements `PROJECT_REVIEW_2026-11-02.md`; the original 12 code-review findings retain their numbering. The changes below are a concrete implementation proposal, not a claim that the application has already been fixed. API/data changes must update their normative contracts and tests when implemented.

## 1. Multiple uploaded images lose their source identity in review

**Confirmed defect.** `get_batch_review` in `backend/app/services/ingestion_service.py` selects the first original asset with `.first()`. `DetectionReviewItem` exposes no source-image identifier, and `IngestionDetection` records the batch and crop but no original asset reference. `IngestionWorkflow` passes all detections to one `BoundingBoxOverlay` using that first original. The code comment intending to suppress ambiguous overlays does not protect against the server's non-null `original_media_url`.

An isolated two-image reproduction stored two originals and produced two detections, but the review response exposed one original URL and no per-detection source field. This confirms the display/mapping problem; it does not establish that every multi-image upload fails. The long-batch timeout issue is separately confirmed in R11 of the main review.

Proposed behavior:

- Return an ordered list of source images, each with an owned media ID, private URL, dimensions, and processing/review status.
- Persist and expose each detection's source-image ID. Validate that source, detection, crop, batch, and user ownership agree.
- Show a thumbnail strip and an image counter. Selecting a photo displays only its regions and items; selecting an item selects its source photo.
- Retain the batch ID while processing. Show progress and retry/recovery per source image so one image problem does not conceal other successful results.
- Preserve source selection after reload using server data rather than relying on local preview blobs.

Acceptance: upload 1, 2, and 10 distinct images; switch between every original; verify each region/crop remains attached to the correct source before and after reload. Include a partial provider failure and a batch lasting longer than 45 seconds.

## 2. Reduce reminder fatigue and simplify confirmation

The screenshot combines general instructions, current detector failures, and untranslated provider output in one warning panel. `IngestionWorkflow` renders all `quality_warnings` directly. `DetectionItemCard` expands many metadata fields and shows confidence badges for most of them, creating a long inspection form.

Proposed reminder policy:

- A short onboarding hint appears for the first two successfully confirmed upload batches, then once every 12 successfully confirmed batches. This uses the user's suggested 10–15 interval as a concrete draft value.
- Count one confirmed batch as one upload event, regardless of its number of photos. Failed, cancelled, and retried confirmations do not advance the counter. Keep this counter independent from outfit-rating cadence.
- Current actionable failures, missing category/type, and uncertain regions appear next to the affected photo/item whenever present. Reminder cadence does not hide these current failures.
- Every batch retains one explicit save action. Reducing hints does not introduce automatic wardrobe persistence.

Proposed UI:

- Default review shows photo, item type, color, inclusion/removal action, and a concise status for fields needing attention.
- Move material, pattern, fit, season, formality, comfort, silhouette, and functional tags into an expandable details section. Show category-appropriate controls; garment length should not dominate footwear review.
- Replace raw model output with concise Vietnamese messages tied to a useful action. Keep provider diagnostics, internal IDs, input-kind enums, and high-confidence percentages out of the main flow.
- Use one summary such as a count of items needing attention and one primary save button. Keep actions accessible on mobile without covering the current editing controls.

Acceptance: deterministic tests for reminder batches 1, 2, 3, and the later interval; retries do not advance the counter; a real current error remains visible between reminder intervals. Keyboard and 375 px checks cover selecting an item, expanding details, correcting it, removing it, and saving.

## 3. Correct item boundaries and offer actual crop editing

The sneaker screenshot shows two regions for the two shoes of one pair, which would create two wardrobe items if both were accepted. The current detector prompt does not define a pair of footwear as one wardrobe unit, and ingestion processes every returned box without pair handling. This is a recognition/unit-of-item problem as well as a crop problem.

`BoundingBoxOverlay` only selects detections; it has no drag/resize callback. Confirmation accepts attribute changes but no revised region. Consequently the current UI cannot perform the crop adjustment mentioned in fallback messages. Separately, wardrobe inventory displays images with `object-cover`, which can visually cut off a correctly stored crop inside its fixed aspect ratio.

Proposed behavior:

- Treat a visible pair of the same footwear as one wardrobe item, with a region enclosing the pair. Add explicit detector guidance and representative examples.
- Review likely duplicates using source identity and item semantics. Do not merge all overlapping boxes or all footwear: two different pairs must remain distinct.
- Provide a visible crop-edit action with drag/resize, zoom, reset, full-image fallback, and remove/merge controls where appropriate. Persist a corrected region and regenerate its crop/thumbnail through `ObjectStorage` before confirmation.
- Validate source ownership and normalized crop bounds. Check EXIF orientation consistently between displayed original, detector input, and crop pixels.
- Use a contained item preview in inventory/cards so a complete garment or pair remains visible.

Acceptance: one pair yields one item; two distinct pairs remain two items; overlapping garments remain separate; a worn outfit yields appropriate item regions; user-adjusted pixels survive save/reload; portrait/rotated photos align correctly; another user's source cannot be cropped.

## 4. Remove the context panel and explain real outfit differences

**User-requested UI change:** remove the visible extracted-context panel from `frontend/src/components/chat/RecommendationView.tsx`. Retain context extraction internally for filtering, scoring, clarifications, and API compatibility. Also remove developer-oriented request IDs from the main recommendation display.

The current explanation generator in `backend/app/agents/coordinator.py` chooses broad templates by score band and rank. Changing introductory wording does not explain why trousers were selected instead of jeans, or how two otherwise similar recommendations differ. Final selection in `personalization_agent.py` takes the first ranked candidates without an explicit cross-result diversity step.

Proposed behavior:

- Each outfit gets one or two short sentences based on its actual garments, verified attributes, and relevant scoring reasons.
- Explain the distinguishing choice: for example, the more formal trouser option versus a more casual jeans option. State a useful tradeoff when supported by the data.
- Select the best outfit first, then favor meaningfully different alternatives among candidates that still meet context and explicit constraints. Consider differences in principal garments, style, and formality; swapping one accessory alone should not create a supposedly distinct option.
- Return fewer outfits when the wardrobe cannot support useful variety. Preserve ownership, active-item grounding, valid outfit branches, and deterministic item selection.
- Do not invent materials, comfort claims, or additional garments to make explanations sound different.

Acceptance: the context panel is absent; context still affects recommendations; reasons describe actual differences; adequate wardrobes yield varied options; sparse wardrobes remain honest; explicit constraints and grounding remain intact.

## 5. Separate user-facing item types and make search understand categories

**Recommended decision:** separate trousers and skirts in UI navigation, cards, and type selection. Keep their shared internal outfit slot `bottom` because either can complete `top + bottom`. User-facing item type and composition slot serve different purposes. Use the existing category/subcategory relationship with a shared canonical type/alias map; do not create a new top-level slot for every garment name.

Suggested UI groups: tops, trousers, skirts, dresses, shoes, sandals/slides, outerwear, accessories. Detailed types include jeans/chinos/trousers, sneakers/derby/oxford, and other supported subcategories. A skirt remains a bottom; a one-piece dress remains a dress. Normalize aliases such as `tshirt`, `tee`, and `t-shirt` consistently across Vision, edit forms, search, display, and scoring.

**Confirmed search behavior:** `list_wardrobe_items` uses `%query%` across several raw attribute strings, does not search `category`, and has no Vietnamese category/type alias expansion. The UI fetches when each character changes. In an isolated wardrobe containing sneakers and derby, the English type names matched individually while the Vietnamese category query did not; a single `a` matched both, and `%`/`_` acted as SQL wildcards.

Proposed search:

- Support accent-insensitive Vietnamese type/category aliases before metadata filtering. Category words expand to compatible detailed types; specific words narrow to those types.
- Keep search-as-you-type with a short debounce and suggestions, or submit a complete query. Match meaningful words/types and useful prefixes rather than unrelated arbitrary substrings across all metadata.
- Parse supported type/color combinations and combine independent filters predictably. Escape wildcard characters when retaining SQL LIKE for free-text fallback.
- Share the taxonomy and localization map between category buttons, onboarding/review controls, item labels, inventory search, and recommendation constraints. Advanced semantic search is unnecessary for this baseline.

Acceptance examples:

| User query | Expected behavior |
| --- | --- |
| `giày`, `giay` | Sneakers, derby, oxford, and other shoe types; respect active-user scope |
| `sneaker` | Sneakers, including normalized plural aliases |
| `quần`, `quan` | Jeans, chinos, trousers, shorts; exclude skirts and dresses |
| `chân váy` | Skirt variants; exclude trousers and one-piece dresses |
| `váy liền`, `đầm` | One-piece dresses; exclude skirts |
| `giày đen` | Black shoes in the requesting user's active wardrobe |
| `%`, `_` | Literal/safely rejected query behavior; never implicit match-all wildcards |

## Implementation order and verification boundary

1. Resolve the main review's data-loss/grounding issues and broken edit payload.
2. Implement source-image linkage and multi-photo review/recovery, then crop/pair handling.
3. Simplify review fields and reminder presentation while preserving explicit save and current-error visibility.
4. Apply the shared item taxonomy, split UI filters, and Vietnamese inventory search.
5. Remove the context panel, ground concise explanations, and improve diversity across returned outfits.

Contract/schema changes require their source documents, migrations, and associated tests in the same implementation task. Use provider fakes for default verification. Add a browser journey that uploads multiple distinct photos, changes source, corrects a crop/type, saves, edits a persisted item, searches by Vietnamese category, and requests diverse grounded recommendations. Follow with a separately opted-in real-image demonstration to assess actual detector boundaries.

This follow-up used source inspection, the user's screenshots, and temporary local database/storage probes. It did not run a live Vision benchmark or alter application code. The earlier full-suite results remain the baseline recorded in the main review.

## Closure addendum — 2026-11-03

The five reported problem groups have implemented corrections and executable regression coverage:

1. Source ownership/mapping persists for every uploaded photo; 1/2/10-photo tests cover reload and a controlled per-photo detector failure. Browser checks restore the selected source. Nonterminal polling survives beyond 45 seconds.
2. Onboarding hints follow confirmed batches 1, 2, 14, 26; actionable errors remain visible. Default review is concise, additional attributes expandable, and saving remains explicit. Desktop and 375 px browser flows verify crop/type/detail changes and saving.
3. Source-aligned crop editing persists through ObjectStorage, includes reset/full-image/restore-raw actions, and handles EXIF orientation. New detections preserve the raw rectangle; historical rows remain unknown. Contained inventory/outfit images avoid display clipping. Pair guidance/grouping and conservative margins have deterministic tests; real-model missed detections remain a separate measured limitation.
4. Context panel and request IDs are removed from recommendation display. Grounded descriptions name actual selected items and their verified differences. Core-garment diversity avoids alternatives differing only in accessories; sparse wardrobes may produce fewer results.
5. Shared taxonomy separates trousers/skirts in user navigation and labels while retaining composition slots. Submitted accent-insensitive Vietnamese category/alias search finds sneakers/derby under giày. Query word matching replaces arbitrary live per-character filtering.

The proposal also mentioned optional zoom controls, manual merge controls, and per-source progress/retry UX. These are not included in this defect-closure scope and are not claimed as implemented. Arbitrarily wrong AI boxes are not fixed by a margin heuristic; manual adjustment and raw/full-image restoration remain explicit controls. Final evidence and live-model limits: `REVIEW_CLOSURE_2026-11-03.md`.
