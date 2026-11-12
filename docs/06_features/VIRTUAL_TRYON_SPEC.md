# Virtual Try-On / Lookbook Specification — MVP

## 1. Scope Terminology

The application supports two visual presentation modes for a selected outfit:
1. **Illustrative Lookbook / Moodboard Fallback:** Produces a catalog lookbook image or structured item moodboard.
2. **2D Photorealistic Virtual Try-On (VTON):** Inpaints garments onto a full-body person or standard preset model using a pixel-space diffusion model (such as `fashn-ai/fashn-vton-1.5`).

The MVP MUST NOT claim accurate physical garment size, fabric elasticity, or tailor-grade fit simulation on the user's body. The UI MUST display the Vietnamese label `Ảnh mặc thử AI` (for virtual try-on), `Ảnh minh họa AI` (for lookbook), or `Moodboard dự phòng` according to render kind.

## 2. Input Contract

- A persisted `outfit_id` owned by the requesting user, or a validated set of wardrobe item IDs.
- Primary item crops for 2–4 outfit items (`ItemMediaRole.PRIMARY`).
- User-confirmed garment metadata.
- Person body reference:
  - Preset standard model/mannequin (male or female), bundled in local assets.
  - User-uploaded full-body avatar (`tryon_avatars`).
- Avatar validation: Any uploaded user avatar MUST pass a person detection guard (e.g. YOLO-World detector detecting a clear `person`) before persistence. Uploading an avatar MUST require explicit user consent, and users MUST be able to delete their avatar at any time.
- Garment categorization:
  - `tops`: Shirts, t-shirts, polos, hoodies, jackets, coats (`top`, `outerwear`).
  - `bottoms`: Pants, jeans, trousers, skirts, shorts (`bottom`).
  - `one-pieces`: Dresses, jumpsuits (`dress`).
  - `footwear` and `accessory` items MUST NOT be submitted to the diffusion inpainting model; they MUST be rendered as coordinated outfit item cards alongside the person image in the UI.

The Gemini image adapter uses the same `GEMINI_API_KEY` as Vision, with a separate `IMAGE_MODEL` identifier. Set `IMAGE_PROVIDER=gemini` to enable it. The adapter sends the outfit's private item crops as inline reference images and reads generated image bytes from the Gemini response. A provider error, invalid image response, or timeout follows the moodboard fallback path.

The FASHN Try-On adapter (`TRYON_PROVIDER=fashn`) calls the Hugging Face Space endpoint (`FASHN_TRYON_SPACE=fashn-ai/fashn-vton-1.5`) with optional `HF_TOKEN`.

## 3. Pipeline

```text
authorize outfit and items
  -> check try-on cache by (user_id, avatar_id, sorted_item_ids)
  -> on cache hit: return cached render (HTTP 200)
  -> on cache miss:
     -> if async mode: create pending tryon_render, dispatch background task, return HTTP 202
     -> background task execution:
        -> resolve person image (preset or avatar source stream)
        -> load primary garment crops
        -> determine execution sequence:
           - single item or one-piece: 1 pass
           - top + bottom: 2-pass sequence (Pass 1: tops -> in-memory intermediate WebP -> Pass 2: bottoms)
        -> on provider error, quota exhaustion, or timeout:
           - generate deterministic moodboard from item crops with fallback_used=true
        -> persist final media asset to tryon-private bucket
        -> update tryon_render status to 'ready' (or 'failed' if fallback also fails)
```

## 4. Prompt and Resolution Requirements

For prompt-based providers (Gemini), the prompt SHOULD describe a standard adult mannequin/model, full-length catalog composition, neutral background, and each garment by slot. It MUST omit null/default attributes and MUST NOT add brands, accessories, or garments absent from the outfit.

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

## 8. Acceptance Criteria and Invariants

- **INVARIANT:** A user cannot render, retrieve, or delete another user's outfit, avatar, or try-on render.
- **INVARIANT:** Every garment described in the try-on belongs to the persisted outfit or the user's wardrobe.
- The moodboard fallback MUST work when the external provider key is absent, quota is exceeded, or the provider is mocked to fail.
- The UI MUST distinguish a generated try-on from a moodboard.
- User-facing copy MUST NOT claim exact body-fit accuracy.
