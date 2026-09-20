# Virtual Try-On / Lookbook Specification — MVP

## 1. Scope Terminology

The MVP produces an **illustrative lookbook image** for a selected outfit. It MUST NOT claim accurate garment size, fit, drape, or simulation on the user's body. The UI MUST display the Vietnamese label `Ảnh minh họa AI` or `Moodboard dự phòng` according to render kind.

## 2. Input Contract

- A persisted `outfit_id` owned by the requesting user.
- Primary item crops for 2–4 outfit items.
- User-confirmed garment metadata.
- A standard model/mannequin preset; the MVP does not require a user body image.

If the configured provider supports multiple reference images, the service SHOULD provide item crops with the prompt. If the provider does not support reference images, the result MUST NOT be described as preserving the exact garments.

The Gemini image adapter uses the same `GEMINI_API_KEY` as Vision, with a separate `IMAGE_MODEL` identifier. Set `IMAGE_PROVIDER=gemini` to enable it. The adapter sends the outfit's private item crops as inline reference images and reads generated image bytes from the Gemini response. A provider error, invalid image response, or timeout follows the moodboard fallback path.

Gemini image-generation models may require a paid API tier. A free-tier key can still run Vision where the selected Vision model is available, while image-generation requests can fail and use the moodboard fallback. Check the provider's current model availability and pricing before enabling the image provider.

## 3. Pipeline

```text
authorize outfit
  -> load item metadata and internal asset streams
  -> validate reference-image quality
  -> build a null-safe prompt
  -> call configured image model with an 8-second timeout
  -> persist generated media asset
  -> on failure: generate a vertical moodboard from item crops
  -> persist tryon_render
  -> return an authenticated media URL
```

## 4. Prompt Requirements

The prompt SHOULD describe a standard adult mannequin/model, full-length catalog composition, neutral background, and each garment by slot. It MUST omit null/default attributes and MUST NOT add brands, accessories, or garments absent from the outfit.

`8K` MUST NOT be an acceptance criterion. The target output SHOULD have at least 1024 pixels on the long edge or use the selected provider's documented limit.

## 5. Moodboard Fallback

- The fallback MUST use stored item crops and MUST NOT require the original upload to contain transparency.
- If a crop contains a mask or alpha channel, the renderer MAY use it; otherwise it MUST place the image on a neutral card.
- The output MUST show items by slot with name/color and the Vietnamese watermark `Moodboard dự phòng`.
- The fallback MUST NOT composite garments onto a person's body.

## 6. UI Contract

- The responsive modal MUST contain the main image, item list, and render-kind label.
- Available actions: regenerate, save/unsave outfit, and close.
- Rating MUST NOT be forced inside the modal. It MAY appear when cadence allows or when the user opens it manually.
- Functional icons MUST have text or an accessible label. Decorative emoji MUST NOT appear in headings or button labels.

## 7. Reliability and Privacy

- Provider timeout MUST be 8 seconds.
- Generated output or fallback SHOULD complete within a total target of 10 seconds.
- When fallback succeeds, the API MUST return HTTP 200 with `fallback_used=true`.
- Media MUST be stored in a private bucket and guarded by ownership checks.
- Provider/model/duration SHOULD be stored for benchmarking, but prompts MUST NOT contain unnecessary personal information.

## 8. Acceptance Criteria and Invariants

- **INVARIANT:** A user cannot render or retrieve another user's outfit.
- **INVARIANT:** Every garment described in the prompt belongs to the persisted outfit.
- The moodboard fallback MUST work when the image-provider key is absent or the provider is mocked to fail.
- The UI MUST distinguish a generated lookbook from a moodboard.
- User-facing copy MUST NOT claim exact body-fit accuracy.
