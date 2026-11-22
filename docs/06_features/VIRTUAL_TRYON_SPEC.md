# Virtual Try-On / Lookbook Specification — MVP

## 1. Scope Terminology

The application supports two visual presentation modes for a selected outfit:
1. **Illustrative Lookbook / Moodboard Fallback:** Produces a catalog lookbook image or structured item moodboard.
2. **2D Photorealistic Virtual Try-On (VTON):** Renders the outfit's garments onto a full-body person or standard preset model. The default provider is FLUX VTO on fal.ai (`fal-ai/flux-pro/v1/vto`), selected over FASHN Try-On v1.6 by the 2026-11-22 provider spike (`../archive/reports/TRYON_PROVIDER_SPIKE_2026-11-22.md`); the FASHN VTON v1.5 Hugging Face adapter remains available.

The MVP MUST NOT claim accurate physical garment size, fabric elasticity, or tailor-grade fit simulation on the user's body. The UI MUST display the Vietnamese label `Ảnh mặc thử AI` (for virtual try-on), `Ảnh minh họa AI` (for lookbook), or `Moodboard dự phòng` according to render kind.

## 2. Input Contract

- A persisted `outfit_id` owned by the requesting user, or a validated set of wardrobe item IDs.
- Primary item crops for 2–4 outfit items (`ItemMediaRole.PRIMARY`).
- User-confirmed garment metadata.
- Person body reference:
  - Preset standard model/mannequin (male or female), bundled in local assets.
  - User-uploaded full-body avatar (`tryon_avatars`).
- Avatar validation: Any uploaded user avatar MUST pass a person detection guard (e.g. YOLO-World detector detecting a clear `person`) before persistence. Uploading an avatar MUST require explicit user consent, and users MUST be able to delete their avatar at any time. The consent control MUST be unchecked by default and MUST state that the photo is sent to an external image-processing service; the API MUST reject an upload whose `consent` field is not `true` (see `../05_api/API_CONTRACT.md`, section 8.4).
- Garment categorization:
  - `tops`: Shirts, t-shirts, polos, hoodies, jackets, coats (`top`, `outerwear`).
  - `bottoms`: Pants, jeans, trousers, skirts, shorts (`bottom`).
  - `one-pieces`: Dresses, jumpsuits (`dress`).
  - `footwear` and `accessory` items MUST NOT be submitted to the diffusion inpainting model; they MUST be rendered as coordinated outfit item cards alongside the person image in the UI.

The Gemini image adapter uses the same `GEMINI_API_KEY` as Vision, with a separate `IMAGE_MODEL` identifier. Set `IMAGE_PROVIDER=gemini` to enable it. The adapter sends the outfit's private item crops as inline reference images and reads generated image bytes from the Gemini response. A provider error, invalid image response, or timeout follows the moodboard fallback path.

The FLUX VTO adapter (`TRYON_PROVIDER=flux`) calls `https://fal.run/<FLUX_VTO_MODEL>` (default `fal-ai/flux-pro/v1/vto`) with `FAL_KEY`. Startup of the try-on dependency MUST fail with a configuration error when `FAL_KEY` is missing. The key MUST be sent only to fal.ai, never to the CDN that serves the result image. Each HTTP call MUST be bounded by `TRYON_TIMEOUT_SECONDS`. An HTTP error, a response without an image, a non-image result or a transport error MUST raise a provider error with a fixed user-facing message (no provider response text), and a timeout MUST raise a timeout; both follow the moodboard fallback path. The adapter re-encodes the result as WebP.

The FASHN Try-On adapter (`TRYON_PROVIDER=fashn`) calls the Hugging Face Space endpoint (`FASHN_TRYON_SPACE=fashn-ai/fashn-vton-1.5`) with optional `HF_TOKEN`. Each provider pass MUST be bounded by `TRYON_TIMEOUT_SECONDS`; on expiry the adapter MUST cancel the remote job and raise a timeout, which follows the moodboard fallback path.

## 3. Pipeline

```text
authorize outfit and items
  -> check try-on cache by (user_id, avatar_id, provider model, sorted_item_ids)
  -> on cache hit: return cached render (HTTP 200)
  -> on cache miss:
     -> if async mode: create pending tryon_render, dispatch background task, return HTTP 202
     -> background task execution:
        -> resolve person image (preset or avatar source stream)
        -> load primary garment crops
        -> determine execution sequence:
           - provider supports whole-outfit rendering (FLUX VTO): 1 call with every chosen garment
           - otherwise, single item or one-piece: 1 pass
           - otherwise, top + bottom: 2-pass sequence (Pass 1: tops -> in-memory intermediate WebP -> Pass 2: bottoms)
        -> on provider error, quota exhaustion, or timeout:
           - generate deterministic moodboard from item crops with fallback_used=true
        -> persist final media asset to tryon-private bucket
        -> update tryon_render status to 'ready' (or 'failed' if fallback also fails)
```

## 4. Prompt and Resolution Requirements

For prompt-based providers (Gemini), the prompt SHOULD describe a standard adult mannequin/model, full-length catalog composition, neutral background, and each garment by slot. It MUST omit null/default attributes and MUST NOT add brands, accessories, or garments absent from the outfit.

The provider model is part of the render cache key, so changing provider or model never serves another model's render; `force_refresh` still bypasses the cache.

For FLUX VTO, the person image MUST be downscaled to at most 1 MP and the chosen garments MUST be placed left to right, upper body first, on a white canvas of at most about 0.5 MP; a one-piece is sent alone. The prompt MUST name each garment in that order using only its recorded color, non-plain pattern and sub-category, MUST ask to keep the person's face, hair, pose, body shape, footwear and background unchanged, and MUST NOT add brands, accessories or garments absent from the outfit.

For pixel-space diffusion providers (FASHN VTON), output resolution is determined by the model architecture ($576 \times 864$ or aspect-ratio adapted $576 \times 717$). Prompt-based targets SHOULD have at least 1024 pixels on the long edge or use the selected provider's documented limit.

## 5. Moodboard Fallback

- The fallback MUST use stored item crops and MUST NOT require the original upload to contain transparency.
- If a crop contains a mask or alpha channel, the renderer MAY use it; otherwise it MUST place the image on a neutral card.
- The output MUST show items by slot with name/color and the Vietnamese watermark `Moodboard dự phòng`.
- The fallback MUST NOT composite garments onto a person's body.

## 6. UI Contract

- The responsive modal MUST contain the main image, item list, and render-kind label.
- Available actions: switch avatar (preset model vs personal avatar), regenerate / try-on, before/after comparison slider, mark outfit as worn (`recordOutfitWorn`), and close.
- When an outfit contains both `top` and `outerwear`, the UI SHOULD provide a toggle to preview either the outer layer or inner top.
- Rating MUST NOT be forced inside the modal. It MAY appear when cadence allows or when the user opens it manually.
- Functional icons MUST have text or an accessible label. Decorative emoji MUST NOT appear in headings or button labels.

## 7. Reliability and Privacy

- Synchronous provider timeout MUST be 8 seconds (`IMAGE_TIMEOUT_SECONDS`).
- Asynchronous multi-pass VTON pipeline timeout SHOULD be configurable via `TRYON_TIMEOUT_SECONDS` (default 90 seconds).
- When fallback succeeds, the API MUST return HTTP 200 with `fallback_used=true`.
- Media MUST be stored in a private bucket (`tryon-private`) and guarded by ownership checks.
- User personal avatar images MUST NOT be shared with other users or exposed publicly.
- An uploaded avatar MUST be stored upright and without EXIF, GPS, or other metadata before person detection or any provider call (`../04_data/OBJECT_STORAGE_SPEC.md`, section 3).

## 8. Acceptance Criteria and Invariants

- **INVARIANT:** A user cannot render, retrieve, or delete another user's outfit, avatar, or try-on render.
- **INVARIANT:** Deleting a user avatar removes every try-on render made from it, including its stored image; a render still in progress when the avatar is deleted is discarded (see `../05_api/API_CONTRACT.md`, section 8.5).
- **INVARIANT:** Every garment described in the try-on belongs to the persisted outfit or the user's wardrobe.
- The moodboard fallback MUST work when the external provider key is absent, quota is exceeded, or the provider is mocked to fail.
- The UI MUST distinguish a generated try-on from a moodboard.
- User-facing copy MUST NOT claim exact body-fit accuracy.
