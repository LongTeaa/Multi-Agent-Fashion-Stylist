# Object Storage Specification

## 1. Decision

Image bytes MUST NOT be stored as SQLite BLOBs. The backend MUST use an `ObjectStorage` interface with these adapters:

- `MinioObjectStorage`: default for local development and production-like demonstrations.
- `LocalObjectStorage`: allowed for automated tests and minimal offline demonstrations.

Business logic MUST persist `object_key` references, not absolute filesystem paths or permanent public URLs.

## 2. Buckets and Object Keys

| Bucket | Content | Access policy |
| :--- | :--- | :--- |
| `wardrobe-private` | Original uploads and item crops | Private |
| `wardrobe-thumbnails` | Optimized thumbnails | Private; short-lived signed URL or media proxy |
| `tryon-private` | Generated lookbooks and moodboards | Private |

Normative key convention:

```text
users/{user_id}/ingestions/{batch_id}/original/{asset_id}.{ext}
users/{user_id}/items/{item_id}/crop/{version}.{ext}
users/{user_id}/items/{item_id}/thumbnail/{version}.webp
users/{user_id}/tryons/{tryon_id}/render.webp
```

An object key MUST NOT contain an email address, real name, or original client filename.

## 3. Upload Lifecycle

1. The backend MUST validate actual MIME type, maximum 10 MB file size, and configured pixel limits.
2. It MUST create an `ingestion_batch` with `processing` status.
3. It MUST upload the original image to a private bucket.
4. It SHOULD create and upload item crops and optimized thumbnails.
5. After user confirmation, it MUST link each confirmed crop to a `wardrobe_item`.
6. A cleanup job MUST remove unconfirmed or temporary assets after 24 hours.

Deleting a wardrobe item is a metadata soft delete. Physical objects SHOULD be retained for 30 days unless the user explicitly requests data erasure.

## 4. Media Access

- The frontend MUST NOT receive MinIO credentials.
- The API MUST return a short-lived signed URL, default 15 minutes, or stream through an authenticated endpoint.
- The backend MUST validate ownership before signing or streaming an object.
- Buckets MUST NOT be public.
- The backend MUST NOT accept a raw object key from an untrusted client as an authorization decision.

## 5. Configuration Contract

```env
OBJECT_STORAGE_BACKEND=minio
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key
MINIO_SECURE=false
MINIO_BUCKET_WARDROBE=wardrobe-private
MINIO_BUCKET_THUMBNAILS=wardrobe-thumbnails
MINIO_BUCKET_TRYON=tryon-private
SIGNED_URL_TTL_SECONDS=900
```

Secrets MUST exist only in `.env` or an equivalent secret store. `.env.example` MUST contain placeholders only.

## 6. Failure Semantics

- Database persistence MUST NOT commit when the required object upload failed.
- If database persistence fails after object upload, the object MUST be registered for compensating cleanup.
- A failed cleanup operation MUST be retryable and observable.
- Object retrieval failure SHOULD return a normalized API error without exposing internal bucket or key data.

## 7. Acceptance Criteria and Invariants

- **INVARIANT:** No bucket is publicly readable.
- **INVARIANT:** User A cannot obtain a signed URL for User B's object.
- Orphaned temporary objects MUST be removed within 24 hours.
- Removing an item MUST NOT corrupt historical outfit records; the UI SHOULD display a placeholder when an asset is no longer retained.
- Local and MinIO adapters MUST pass the same contract-test suite.
