# API Contract Specification — MVP

## 1. Conventions

- Base path MUST be `/api/v1`.
- Payloads MUST use JSON except multipart upload operations.
- The local MVP MUST accept `X-User-Id`; every private operation MUST validate ownership.
- The client MAY supply `X-Client-Session-Id` header (e.g. UUID stored in `sessionStorage`) or provide `client_session_id` in request payloads to track session-scoped suppression of proactive feedback prompts.
- All session identifiers (in header or body) MUST be valid UUID v4 strings.
- If both the `X-Client-Session-Id` header and `client_session_id` body field are present in the same request, they MUST be identical; any conflict MUST return HTTP 422 `VALIDATION_ERROR`.
- Datetimes MUST use ISO 8601 UTC.
- Except where an HTTP status or redirect is explicitly described, the examples below show the value of the success envelope's `data` field.
- Successful responses MUST use this envelope:

```json
{"success": true, "data": {}}
```

- Error responses MUST use this envelope. `message` is user-facing Vietnamese copy:

```json
{"success": false, "error": {"code": "ERROR_CODE", "message": "Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.", "details": null}}
```

## 2. Ingestion API

### 2.1 `POST /ingestions`

Uploads 1–10 images, with a maximum size of 10 MB per image. Multipart fields are `images[]` and optional `declared_input_kind`.

The operation MUST return HTTP `202` with `batch_id` and `status=processing`. Files MUST be stored privately before provider processing begins.

### 2.2 `GET /ingestions/{batch_id}`

Returns current status, quality warnings, and detections for user review:

```json
{
  "batch_id": "uuid",
  "input_kind": "multi_item",
  "status": "needs_review",
  "detections": [
    {
      "detection_id": "uuid",
      "crop_url": "/api/v1/media/uuid",
      "bounding_box": [0.1, 0.2, 0.6, 0.8],
      "attributes": {
        "category": "top",
        "sub_category": "polo",
        "primary_color": "white",
        "style": "smart_casual",
        "formality_level": 3,
        "weather_suitability": ["warm", "cool"]
      },
      "field_confidence": {"category": 0.97, "primary_color": 0.94}
    }
  ],
  "quality_warnings": []
}
```

### 2.3 `POST /ingestions/{batch_id}/confirm`

Accepts selected detections and user-corrected attributes. It MUST return the created `wardrobe_item_id` values. Repeated submission of the same confirmation MUST be idempotent.

### 2.4 `DELETE /ingestions/{batch_id}`

Cancels an unconfirmed batch and schedules its temporary assets for cleanup.

## 3. Wardrobe API

| Method | Endpoint | Purpose |
| :---: | :--- | :--- |
| GET | `/wardrobe/items` | Paginated list/filter by category, style, color, and text |
| POST | `/wardrobe/items` | Manual item creation from an already uploaded asset |
| GET | `/wardrobe/items/{item_id}` | Item detail |
| PATCH | `/wardrobe/items/{item_id}` | Partial update and retrieval-document refresh |
| DELETE | `/wardrobe/items/{item_id}` | Soft delete and active-index removal |

An item response MUST include a short-lived media URL, normalized metadata, per-field confidence, `is_user_confirmed`, `times_worn`, and `last_worn_at`.

## 4. Stylist Chat API

### 4.1 `POST /stylist/chat`

Request example; the user query MUST remain Vietnamese:

```json
{
  "query": "Tối nay đi cafe ngoài trời ở Đà Lạt, hơi lạnh, muốn lịch sự nhẹ",
  "location": null,
  "client_session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Response data:

```json
{
  "request_id": "uuid",
  "needs_clarification": false,
  "clarification_question": null,
  "context": {
    "occasion": "cafe",
    "time_of_day": "evening",
    "event_date": "2026-09-03",
    "location_text": "Đà Lạt",
    "environment": "outdoor",
    "weather_condition": "cold",
    "temperature_celsius": null,
    "target_formality_range": [2, 3],
    "style_hints": ["smart_casual"],
    "vibe_keywords": ["lịch sự nhẹ"],
    "must_have": [],
    "must_avoid": [],
    "weather_source": "user"
  },
  "recommendations": [
    {
      "outfit_id": "persisted-uuid",
      "rank": 1,
      "composite_score": 0.91,
      "items": [
        {"slot": "top", "item_id": "item-top-01", "name": "Áo polo trắng", "image_url": "/api/v1/media/uuid"}
      ],
      "explanation_vi": "Bộ trang phục phù hợp với thời tiết se lạnh và không gian ngoài trời.",
      "applied_preferences": ["Phù hợp phong cách smart casual đã chọn"]
    }
  ],
  "feedback_prompt_eligible": false,
  "feedback_target_outfit_id": null,
  "warnings": []
}
```

If `needs_clarification=true`, `recommendations` MUST be empty, `clarification_question` MUST contain a concise Vietnamese user-facing question, and the request MUST NOT increment feedback cadence.

## 5. Profile and Personalization API

| Method | Endpoint | Purpose |
| :---: | :--- | :--- |
| GET | `/user/profile` | Retrieve the user profile and selected options |
| PUT | `/user/profile/preferences` | Replace validated onboarding choices |
| GET | `/user/profile/preference-options` | Retrieve the canonical options rendered by the UI |

The API MUST NOT accept free-form text as a mechanism for inferring sensitive traits.

`PUT /user/profile/preferences` replaces all onboarding selections. Omitted groups are
stored as empty selections. The request and the `preferences` field returned by profile
responses use this shape:

```json
{
  "styles": ["minimalist", "smart_casual"],
  "color_palettes": ["neutral"],
  "priorities": ["comfort"],
  "avoid_colors": ["orange"],
  "avoid_styles": ["streetwear"],
  "fit_preferences": ["regular"]
}
```

Style, color-palette, and priority groups accept at most three options. Fit accepts at
most one. Values MUST come from `GET /user/profile/preference-options`; duplicate and
unknown values MUST return `VALIDATION_ERROR`. A profile response also includes
`user_id`, `email`, `full_name`, versioned `feature_weights`, and `ratings_count`.

## 6. Outfit Actions API

All endpoints in this section require the `X-User-Id` header and verify ownership against `outfit_recommendations.user_id`.

| Method | Endpoint | Purpose |
| :---: | :--- | :--- |
| GET | `/outfits/{outfit_id}` | Retrieve a persisted outfit with ordered items and metadata |
| PUT | `/outfits/{outfit_id}/rating` | Idempotently create or update a 1–5 rating |
| POST | `/outfits/{outfit_id}/worn` | Confirm wear, requiring `idempotency_key` (UUID v4) and optional `worn_at` |
| PUT | `/outfits/{outfit_id}/bookmark` | Set `{ "is_bookmarked": true/false }` |
| GET | `/outfits/saved` | Retrieve paginated bookmarked outfits |

### 6.1 `GET /outfits/{outfit_id}`

Retrieves a persisted outfit belonging to the authenticated user. If wardrobe items in the outfit were later deactivated or deleted, their historical attributes remain readable with `is_active: false`.

Response `data`:
```json
{
  "id": "uuid",
  "request_id": "uuid",
  "user_query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?",
  "explanation_vi": "Set đồ trẻ trung, thoải mái cho buổi cafe...",
  "fashion_score": 0.85,
  "personalization_score": 0.80,
  "composite_score": 0.83,
  "rank": 1,
  "is_bookmarked": false,
  "times_worn": 0,
  "last_worn_at": null,
  "user_rating": null,
  "items": [
    {
      "slot_role": "top",
      "wardrobe_item_id": "uuid",
      "name": "Áo polo trắng",
      "category": "top",
      "sub_category": "polo",
      "primary_color": "white",
      "secondary_color": null,
      "pattern": "solid",
      "material": "cotton",
      "style": "smart_casual",
      "image_url": "/api/v1/media/uuid",
      "is_active": true
    }
  ],
  "created_at": "2026-09-14T03:00:00Z"
}
```

### 6.2 `GET /outfits/saved`

Retrieves a paginated list of bookmarked outfits for the requesting user, sorted deterministically by `created_at DESC, id DESC`.

Query parameters:
- `page`: integer >= 1 (default `1`)
- `page_size`: integer between 1 and 50 (default `10`)

Response `data`:
```json
{
  "items": [],
  "page": 1,
  "page_size": 10,
  "total": 0
}
```

### 6.3 `PUT /outfits/{outfit_id}/bookmark`

Sets or updates the bookmark state of an outfit. Repeated calls with the same boolean are idempotent and do not create duplicate records.

Request:
```json
{
  "is_bookmarked": true
}
```

Response `data`:
```json
{
  "outfit_id": "uuid",
  "is_bookmarked": true,
  "updated_at": "2026-09-14T03:05:00Z"
}
```

### 6.4 `POST /outfits/{outfit_id}/worn`

Confirms that the user has worn the outfit.
- `idempotency_key` (UUID v4 string) is REQUIRED. Retrying with the same `(user_id, idempotency_key)` returns the existing wear record with `already_processed: true` without creating a second wear log or incrementing `times_worn` again.
- If the same `idempotency_key` is reused with a different `outfit_id` or conflicting payload, the API MUST return HTTP 409 `IDEMPOTENCY_CONFLICT`.
- `worn_at` is optional (ISO 8601 UTC). Defaults to current server time if omitted. Must be timezone-aware UTC and must not be in the future.
- Viewing or bookmarking an outfit DOES NOT create a wear log.

Request:
```json
{
  "idempotency_key": "550e8400-e29b-41d4-a716-446655440000",
  "worn_at": "2026-09-14T03:10:00Z"
}
```

Response `data`:
```json
{
  "wear_log_id": "uuid",
  "outfit_id": "uuid",
  "worn_at": "2026-09-14T03:10:00Z",
  "times_worn": 1,
  "already_processed": false
}
```

### 6.5 `PUT /outfits/{outfit_id}/rating`

Idempotently creates or updates a rating (integer 1 to 5 only).
- `stars`: integer between 1 and 5 (strict integer: booleans and floats MUST be rejected with `VALIDATION_ERROR`).
- `source`: `"prompted"` or `"manual"`.
- `client_session_id`: UUID v4 string. REQUIRED when `source="prompted"`; optional when `source="manual"`. If provided, backend records this session in `feedback_suppressed_sessions` so no further proactive feedback prompts are shown in the same session.
- `ratings_count` in response reflects the number of *distinct* outfits rated by this user. Updating an existing rating does not increment `ratings_count`.
- The MVP MUST NOT expose Like/Dislike endpoints or fields.

Request:
```json
{
  "stars": 4,
  "source": "prompted",
  "client_session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Response `data`:
```json
{
  "rating_id": "uuid",
  "outfit_id": "uuid",
  "stars": 4,
  "source": "prompted",
  "ratings_count": 5,
  "created_at": "2026-09-14T03:15:00Z",
  "updated_at": "2026-09-14T03:15:00Z"
}
```

## 7. Feedback Lifecycle API

### 7.1 `POST /feedback/prompts/dismiss`

Dismisses the proactive feedback rating prompt.
- Increments or sets `cooldown_remaining` (minimum 3 eligible outfits) so the prompt is not shown again immediately.
- `client_session_id`: optional client session UUID stored in `sessionStorage`.
- Dismissal MUST NOT add the session to `feedback_suppressed_sessions`; after cooldown and the normal cadence threshold, a prompt MAY appear again in the same session. Session-wide suppression is created only by a successful rating.

Request:
```json
{
  "client_session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Response `data`:
```json
{
  "cooldown_remaining": 3,
  "dismissed": true
}
```

## 8. Try-On API

### 8.1 `POST /tryons`

Request: `{"outfit_id":"uuid"}`.

The operation MUST return HTTP `200` when image generation completes or when the moodboard fallback succeeds:

```json
{
  "tryon_id": "uuid",
  "outfit_id": "uuid",
  "image_url": "/api/v1/media/uuid",
  "render_kind": "generated_lookbook",
  "fallback_used": false,
  "duration_ms": 4200,
  "status": "ready"
}
```

`render_kind` MUST be `generated_lookbook` or `moodboard`. The API MUST return `504 TRYON_FAILED` only when both the external provider and the fallback fail.

## 9. Media API

### 9.1 `GET /media/{media_asset_id}`

The operation MUST verify ownership, then redirect to a short-lived signed URL or stream the asset. A client MUST NOT supply a raw object key.

## 10. Error Codes

All `message` values below are normative user-facing Vietnamese copy.

| Code | HTTP | User-facing message |
| :--- | :---: | :--- |
| `VALIDATION_ERROR` | 422 | `Dữ liệu không hợp lệ. Vui lòng kiểm tra lại.` |
| `FORBIDDEN_ASSET` | 403 | `Bạn không có quyền truy cập ảnh này.` |
| `INGESTION_NOT_READY` | 409 | `Ảnh vẫn đang được xử lý. Vui lòng thử lại sau.` |
| `IDEMPOTENCY_CONFLICT` | 409 | `Idempotency key đã được sử dụng cho một yêu cầu khác.` |
| `WARDROBE_EMPTY` | 404 | `Tủ đồ của bạn chưa có trang phục. Hãy thêm quần áo trước nhé.` |
| `NO_COMPLETE_OUTFIT` | 422 | `Tủ đồ hiện chưa đủ món để tạo một bộ trang phục hoàn chỉnh.` |
| `ITEM_NOT_FOUND` | 404 | `Không tìm thấy món đồ này.` |
| `OUTFIT_NOT_FOUND` | 404 | `Không tìm thấy bộ trang phục này.` |
| `NOT_IMPLEMENTED` | 501 | `Chức năng đang được phát triển trong task tiếp theo.` |
| `PROVIDER_ERROR` | 502 | `Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau.` |
| `TRYON_FAILED` | 504 | `Không thể tạo ảnh minh họa lúc này. Vui lòng thử lại sau.` |

## 11. API Invariants

- **INVARIANT:** OpenAPI generated from code matches every endpoint and response field in this contract.
- **INVARIANT:** A successful stylist response returns persisted, user-owned outfit IDs only.
- **INVARIANT:** Every private endpoint uses the same resolved user identity for database and media ownership checks.
- **INVARIANT:** Idempotent endpoints remain idempotent under client retries.
