# Real-image ingestion review — 2026-11-02

The review uses seven distinct original photos already uploaded to the local application: worn trousers, a matching white sneaker pair, a worn polo with hat and trousers, a single Derby shoe, jeans, and blue/red T-shirts. The images were read through ObjectStorage. The committed manifest pins image digests and coarse manually reviewed rectangles; private photos and run artifacts remain in the ignored `data/private-vision-review/` directory.

## Findings

1. The previous 30-image acceptance corpus is synthetic and uses fake provider outputs. Its passing results do not establish real-image detection quality.
2. Gemini was intermittently unavailable with HTTP 503 (high demand). The original detector exhausted three attempts on the sneaker image. This explains one route to the whole-image manual fallback seen in the reported UI; it is not evidence that every fallback has that cause.
3. A successful worn-polo response returned `[251, 298, 729, 692]` for the top. The adapter treated it as domain XYXY 0–1 even though it corresponds to native Gemini YXYX 0–1000. Other boxes also used this native scale. These values would fail the crop engine and could fail a batch.
4. The sneaker response returned `[0.27, 0.093, 0.86, 0.91]` under the old prompt. Its geometry agrees with normalized YXYX, despite the requested XYXY convention. Reading it as XYXY retains only about 71% of the coarse pair rectangle. This is strong evidence of an axis-order mismatch, but raw legacy arrays cannot be disambiguated reliably by a heuristic.

Google documents native detection coordinates as YXYX on a 0–1000 grid. The adapter now explicitly requests `box_2d` with a response schema and converts it to the existing domain contract. It validates range, ordering, and exactly one coordinate format. Invalid or ambiguous legacy arrays fail at the provider boundary; they are never guessed or clamped. [Google image understanding](https://ai.google.dev/gemini-api/docs/image-understanding), [structured output](https://ai.google.dev/gemini-api/docs/structured-output).

## Verification and limits

- Isolated annotation replay: seven real source images, ten manually annotated regions, ten crops. All sources survive review; each crop byte digest matches the correct original and rectangle. A crop on a later source can be changed, reloaded, and confirmed. No wardrobe item exists before confirmation; repeated confirmation returns the same item set. Temporary database and storage are disposed afterward.
- Regression tests use the observed asymmetric polo coordinates and sneaker geometry. They cover range/ordering ambiguity and ensure canonical legacy boxes are not transposed. One-to-one localization matching prevents a single whole-image fallback from counting as several detected garments.
- Live requests before the fix obtained three valid responses out of seven attempts; the worn-polo response contained incompatible coordinates. After the fix, a run encountered two consecutive HTTP 503 responses and stopped, recording remaining cases as skipped. No complete post-fix live accuracy claim is made. Attribute classification, segmentation quality, multiple distinct shoe pairs, blur/clutter robustness, and representative model accuracy remain unmeasured by this seven-photo corpus.

## Follow-up live measurement after the coordinate fix

The configured `gemini-3.6-flash` service returned six successful requests and six
provider errors over twelve attempts across five bounded runs. Six of seven unique
photos eventually returned a response; worn-polo remained unavailable. This is
pooled evidence across retries, not a single complete corpus run or representative
accuracy estimate. The sanitized per-case boxes, metrics, crop digests and request
outcomes are recorded in `data/fixtures/vision_real_review_v1_followup_20261102.json`.

| Case | Matched annotated regions | Exact count | Visual inspection |
| :--- | :--- | :--- | :--- |
| Worn trousers | 0/2 | Not scored (partial extra top allowed) | Pants geometry is plausible; also returns a partial top and shoes. Strict retention on coarse references fails; retain this result and review reference bounds independently. |
| Matching sneaker pair | 1/1 | Pass: one item | Crop visibly includes both shoes, including their soles. |
| Worn polo | Unmeasured | Unmeasured | HTTP 503/connection failures; no post-fix crop to inspect. |
| Single Derby | 0/1 | Pass: one item | Crop is tight at the bottom and clips part of the sole; manual adjustment remains necessary. |
| Jeans | 1/1 | Pass: one item | Garment is fully represented in the crop. |
| Blue T-shirt | 1/1 | Pass: one item | Garment is fully represented in the crop. |
| Red T-shirt | 1/1 | Pass: one item | Garment is fully represented in the crop. |

Matching requires both IoU >= 0.5 and rectangle retention >= 0.9. A successful
response is not itself a passing localization result. No threshold or annotation
was changed to turn failures into passes. Saved crops were generated with the same
crop engine as ingestion and inspected locally. Private run directories contain
the original reports and crop PNGs; photos remain excluded from Git.

The runner now accepts repeatable `--case` selectors and saves predicted crops,
dimensions, and digests automatically. Subset denominators, selected IDs, manifest
digest and adapter contract are explicit in reports. For example:

```powershell
python backend/scripts/evaluate_real_ingestion.py --live --case matching-sneaker-pair --case worn-polo
```

Next: address tight crop boundaries using the observed Derby case, verify that
any margin does not introduce adjacent garments/faces, and independently review
coarse references before expanding the corpus. Provider instability still prevents
a complete live measurement of the worn-polo case.

## Reproduction

From the repository root, with the private files retained locally:

```powershell
python backend/scripts/evaluate_real_ingestion.py
python backend/scripts/evaluate_real_ingestion.py --live
```

The default run never calls an external model. Live mode uses the existing configured provider/key/model and does not change `.env`. Reports distinguish annotated replay from live localization and preserve provider-unavailable/skipped cases. Each run writes a new ignored output directory. Next: repeat the live evaluation when the configured service is stable, inspect the resulting crops, and expand the annotated corpus before treating model-quality targets as satisfied.
