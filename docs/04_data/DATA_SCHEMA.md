# Data Schema Specification — MVP

## 1. Principles

- SQLite MUST store relational metadata and relationships. Image bytes MUST reside in ObjectStorage.
- Entity identifiers MUST use UUID strings.
- Timestamps MUST be stored in UTC.
- JSON columns SHOULD contain only small bounded structures. PostgreSQL migration requires an explicit migration script; changing the connection string alone is insufficient.
- API/domain code MUST validate canonical enums defined by the executable schema source of truth.

## 2. Entity Overview

```text
users
  |-- user_preferences
  |-- ingestion_batches -- ingestion_detections -- media_assets
  |-- wardrobe_items ---- item_media
  |-- outfit_recommendations -- outfit_items
  |                         |-- ratings
  |                         |-- wear_logs
  |                         |-- tryon_renders
  |-- feedback_prompt_state
```

## 3. Tables

### 3.1 `users`

| Field | Type/constraint |
| :--- | :--- |
| `id` | Primary-key UUID string |
| `email` | Unique; MAY be nullable for a local demonstration |
| `full_name` | Nullable string |
| `created_at`, `updated_at` | UTC datetime |

### 3.2 `user_preferences`

| Field | Type/constraint |
| :--- | :--- |
| `user_id` | Primary key and foreign key to `users` |
| `styles`, `color_palettes`, `priorities` | JSON arrays |
| `avoid_colors`, `avoid_styles`, `fit_preferences` | JSON arrays |
| `learned_feature_weights` | Versioned JSON object |
| `ratings_count` | Integer >= 0 |
| `updated_at` | UTC datetime |

### 3.3 `ingestion_batches`

| Field | Type/constraint |
| :--- | :--- |
| `id`, `user_id` | Primary key and indexed foreign key |
| `input_kind` | `unknown`, `single_item`, `multi_item`, `worn_outfit`, `cluttered` |
| `status` | `uploaded`, `processing`, `needs_review`, `confirmed`, `failed`, `expired` |
| `quality_warnings` | JSON array |
| `created_at`, `expires_at` | UTC datetime |

### 3.4 `ingestion_detections`

| Field | Type/constraint |
| :--- | :--- |
| `id`, `user_id`, `ingestion_batch_id` | Primary key and foreign keys |
| `crop_media_asset_id` | Nullable foreign key to `media_assets` until crop creation succeeds |
| `bounding_box` | JSON array `[x_min, y_min, x_max, y_max]`, normalized to `[0,1]` |
| `proposed_attributes` | Validated JSON object |
| `field_confidence` | JSON object with values in `[0,1]` |
| `status` | `proposed`, `accepted`, `rejected` |
| `created_at`, `updated_at` | UTC datetime |

### 3.5 `media_assets`

| Field | Type/constraint |
| :--- | :--- |
| `id`, `user_id`, `ingestion_batch_id` | Primary key and foreign keys; batch is nullable for generated assets |
| `kind` | `original`, `crop`, `thumbnail`, `tryon`, `moodboard` |
| `bucket`, `object_key` | Private storage location |
| `mime_type`, `size_bytes`, `width`, `height`, `sha256` | Validated media metadata |
| `created_at`, `deleted_at` | UTC datetime |

### 3.6 `wardrobe_items`

| Field | Type/constraint |
| :--- | :--- |
| `id`, `user_id`, `ingestion_batch_id` | Primary key and foreign keys; ingestion batch MAY be nullable for manual creation |
| `ingestion_detection_id` | Nullable, unique ownership-scoped foreign key to `ingestion_detections`; null for manual creation |
| `category` | `top`, `bottom`, `dress`, `footwear`, `outerwear`, `accessory` |
| `sub_category` | Normalized string |
| `primary_color`, `secondary_color` | Canonical color; secondary is nullable |
| `pattern`, `material`, `style`, `fit` | Normalized strings |
| `formality_level` | Integer 1–5 |
| `season`, `weather_suitability`, `functional_flags` | JSON arrays |
| `free_text_tags` | User-confirmed JSON array |
| `field_confidence` | JSON object |
| `is_active`, `is_user_confirmed` | Boolean |
| `times_worn`, `last_worn_at` | Derived/cache fields |
| `created_at`, `updated_at`, `deleted_at` | UTC datetime |

### 3.7 `item_media`

This table links `wardrobe_item_id`, `media_asset_id`, ownership key `user_id`, and `role` (`primary`, `alternate`, `thumbnail`). The `(wardrobe_item_id, media_asset_id)` pair MUST be unique. Composite foreign keys MUST enforce that the item and media asset have the same `user_id`.

### 3.8 `outfit_recommendations`

| Field | Type/constraint |
| :--- | :--- |
| `id`, `user_id`, `request_id` | Primary key and indexed identifiers |
| `user_query` | Text |
| `context_snapshot` | Validated JSON object |
| `explanation_vi` | Vietnamese user-facing text |
| `fashion_score`, `personalization_score`, `composite_score` | Float in `[0,1]` |
| `rank` | Integer 1–3 |
| `is_bookmarked` | Boolean |
| `rule_version` | Version string |
| `created_at` | UTC datetime |

### 3.9 `outfit_items`

This table links `outfit_id`, `wardrobe_item_id`, ownership key `user_id`, and `slot_role`. Supported roles are `top`, `bottom`, `dress`, `footwear`, `outerwear`, and `accessory`. The `(outfit_id, wardrobe_item_id)` pair MUST be unique. Composite foreign keys MUST enforce that the outfit and wardrobe item have the same `user_id`.

### 3.10 `ratings`

| Field | Type/constraint |
| :--- | :--- |
| `id`, `user_id`, `outfit_id` | Primary/foreign keys; `(user_id, outfit_id)` MUST be unique |
| `stars` | Integer 1–5 |
| `source` | `prompted` or `manual` |
| `created_at`, `updated_at` | UTC datetime |

MVP MUST NOT define a Like/Dislike `feedback_type`.

### 3.11 `feedback_prompt_state`

| Field | Type/constraint |
| :--- | :--- |
| `user_id` | Primary/foreign key |
| `eligible_count_since_prompt` | Integer >= 0 |
| `next_threshold` | Integer 5–10 |
| `cooldown_remaining` | Integer >= 0 |
| `last_prompted_at`, `last_rated_at` | Nullable UTC datetime |

### 3.12 `wear_logs`

One record represents a user-confirmed wear action: `id`, `user_id`, `outfit_id`, and `worn_at`. Item usage MUST be derived through `outfit_items`; the implementation SHOULD NOT create a separate wear record for every item in the outfit.

### 3.13 `tryon_renders`

Fields: `id`, `user_id`, `outfit_id`, `media_asset_id`, `provider`, `model`, `fallback_used`, `duration_ms`, `status`, and `created_at`.

## 4. Relational Invariants

- **INVARIANT:** An outfit and every wardrobe item within it have the same `user_id`.
- **INVARIANT:** A rating, wear log, or try-on render references a persisted outfit owned by the same user.
- **INVARIANT:** A standard outfit contains `dress` or `top + bottom`, never both branches.
- **INVARIANT:** Every item used in a recommendation is active at recommendation time.
- **INVARIANT:** Object ownership is checked through `media_assets.user_id` before URL signing or streaming.
- **INVARIANT:** An accepted ingestion detection can create at most one wardrobe item.

## 5. Golden Seed Fixture

The golden fixture MUST include one test user and these eight items:

| ID | Category | Description | Style/Formality | Weather |
| :--- | :--- | :--- | :--- | :--- |
| `item-top-01` | top | white solid cotton polo | smart_casual/3 | warm,cool |
| `item-top-02` | top | black button-down shirt | smart_casual/3 | warm,cool,cold |
| `item-top-03` | top | grey graphic tee | streetwear/1 | hot,warm |
| `item-bottom-01` | bottom | navy chinos | smart_casual/3 | warm,cool |
| `item-bottom-02` | bottom | black wool trousers | formal/4 | warm,cool,cold |
| `item-bottom-03` | bottom | denim shorts | casual/1 | hot,warm |
| `item-shoes-01` | footwear | white leather sneakers | minimalist/2 | hot,warm,cool |
| `item-shoes-02` | footwear | brown leather Oxford shoes | formal/4 | warm,cool,cold |

Fixture images SHOULD reside in `data/fixtures/sample_clothes/`. The seed command MUST be idempotent.

## 6. Required Indexes

- `wardrobe_items(user_id, is_active, category)`
- `wardrobe_items(user_id, primary_color, style)`
- `outfit_recommendations(user_id, created_at)`
- `ratings(user_id, created_at)`
- `wear_logs(user_id, worn_at)`
- A unique `(bucket, object_key)` index on `media_assets`
