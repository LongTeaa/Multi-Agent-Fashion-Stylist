# Try-On Extras Check: Footwear, Headwear and Layers with FLUX VTO (2026-11-22)

Roadmap: `docs/07_implementation/ROADMAP.md`, Phase 4. Follows `TRYON_PROVIDER_SPIKE_2026-11-22.md`.

## 1. Question

After switching to FLUX VTO, the application still rendered only one upper garment (outerwear over a top) plus the bottom, or a dress alone, and showed footwear and accessories as cards beside the image. That rule came from FASHN, which accepts only tops, bottoms and one-pieces. Black Forest Labs' documentation shows a 2×2 garment grid with a cap, a sweater, shorts and sandals rendered in one call, but publishes no list of supported item types and nothing about layering. This check asks whether FLUX VTO renders footwear, headwear, an inner top under outerwear and outerwear over a dress without degrading the main garments.

## 2. Method

Six demo outfits, each rendered twice with the application's adapter (`backend/app/services/flux_vto_provider.py`) by `backend/scripts/spike_tryon_extras.py`, call order alternating per case:

- **current:** today's rule and layout (left-to-right composite, one upper garment).
- **extended:** every wearable item with a role, laid out as an equal-cell grid and named in the provider's multi-garment prompt form.

| Case | Avatar | Extended garments |
| :--- | :--- | :--- |
| x1-shoes | male | grey sweater, black trousers, black sneakers |
| x2-layers-boots | male | black vest over grey sweater, blue jeans, black boots |
| x3-layers-sneakers | male | black vest over shirt (recorded "beige", photographed plaid), blue jeans, black sneakers |
| x4-beanie | male | grey sweater, black trousers, black sneakers, grey beanie |
| x5-dress-jacket-flats | female | teal jacket over magenta cocktail dress, beige flats |
| x6-sandals-hat | female | maroon blouse, blue skirt, brown sandals, pink hat |

The review is a side-by-side visual inspection (agent and owner), not a blind rating.

## 3. Results

All 12 renders succeeded on 2026-11-22. Median latency was 10.0 s for current and 9.9 s for extended, so the larger grid did not slow rendering. Estimated cost $0.57.

| Case | Current | Extended |
| :--- | :--- | :--- |
| x1 | Avatar's own white sneakers | Black sneakers as in the wardrobe |
| x2 | Avatar's white t-shirt under the vest | Grey sweater under the vest; black shoes close to the boots |
| x3 | Avatar's white t-shirt under the vest | Plaid shirt under the vest, pattern kept; black sneakers |
| x4 | No headwear | Grey beanie and black sneakers |
| x5 | Dress only, avatar's white sneakers | Quilted teal jacket over the dress; beige flats |
| x6 | No headwear, avatar's white sneakers | Pink hat and brown sandals |

In every case the main garments looked as faithful as in the current render. Footwear was recognisable but less exact where the crop was small or dark (x2 boots, x6 sandals). In x3 the shirt was rendered from its photo (plaid), not from the recorded attribute "beige", which shows that the prompt's attribute words do not override the image.

## 4. Decision

On 2026-11-22 the owner chose to render layers, footwear and headwear for whole-outfit providers. Bags, watches, jewelry and other accessories stay as cards. The API reports worn items in `rendered_item_ids`, and the modal offers the outer/inner choice only when a render did not wear both layers.

## 5. Limitations

- Six cases, one render each, visual inspection only; no blind rating or quantitative fidelity score.
- Preset avatars only.
- Footwear and headwear crops are small in the demo wardrobes, so these results understate what clean product photos would give.

## 6. Reproduction

Raw results without payloads, user identifiers or keys: `data/fixtures/tryon_extras_raw_v1_20261122.json`. Images and the side-by-side page stay in the git-ignored `data/private-tryon-spike/extras/`.

```powershell
python backend/scripts/spike_tryon_extras.py --live --user female=<uuid> --user male=<uuid>
```
