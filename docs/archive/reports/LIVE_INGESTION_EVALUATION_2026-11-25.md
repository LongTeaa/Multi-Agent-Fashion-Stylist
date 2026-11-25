# Live-provider ingestion evaluation: detector comparison — 2026-11-25

Roadmap Phase 1, last checklist item. This report completes the detector comparison that
`LIVE_INGESTION_EVALUATION_2026-11-19.md` could not finish because every Gemini-detector
request hit the free-tier quota. It also adds two runs the first report did not have: a
same-day repeat of the YOLO-World configuration, to measure run-to-run variation, and a
smaller vision model as a baseline for attribute extraction. Datasets, gold labels,
matching rules, crop policy and scoring code are unchanged from the 2026-11-19 report;
read that report for definitions.

## 1. Setup

| Item | Value |
| :--- | :--- |
| Code | `main` at `f0bddfa`, branch `feat/gemini-detector-evaluation` (no application change) |
| Provider account | Gemini API, paid Tier 1 (prepaid credit), one key; key rotation disabled |
| Detectors | YOLO-World `yolov8s-worldv2.onnx` (local); Gemini `gemini-3.6-flash` native `box_2d` detection |
| Vision models | `gemini-3.6-flash` (application default, fallback `gemini-3.5-flash-lite`); `gemini-3.5-flash-lite` (baseline, fallback the same model) |
| Crop policy | `isolated-footwear-margin-v1`, identical to the 2026-11-19 runs |
| Gold | `vision_attribute_gold_v1.json` (58 photos, owner reviewed), `vision_real_review_v3.json` (14 photos, 47 rectangles), `vision_real_review_v2.json` (7 private photos, 10 rectangles); none edited since 2026-11-19 |
| Runner | `backend/scripts/evaluate_live_ingestion.py --live`, then `--score` offline |

The raw files record a different `gold_sha256` for the 2026-11-19 runs. The difference is
line endings only: the committed gold file hashes to the 2026-11-19 digest, and its CRLF
checkout on Windows (`core.autocrlf=true`) hashes to the 2026-11-25 digest. Labels are
identical.

### Runs

| ID | Configuration | Set | Start (UTC) | Raw file (`data/fixtures/`) |
| :--- | :--- | :--- | :--- | :--- |
| Y-19 | YOLO-World + `3.6-flash` | A | 2026-11-19 07:54 | `live_ingestion_attributes_v1_yolo_world.json` (from the first report) |
| Y-25 | YOLO-World + `3.6-flash` | A | 2026-11-25 02:45 | `live_ingestion_attributes_v1_yolo_world_20261125.json` |
| G-25 | Gemini detector + `3.6-flash` | A | 2026-11-25 02:20 | `live_ingestion_attributes_v1_gemini_20261125.json` |
| L-25 | YOLO-World + `3.5-flash-lite` | A | 2026-11-25 02:33 | `live_ingestion_attributes_v1_yolo_world_flash_lite_20261125.json` |
| GB-25 | Gemini detector | B | 2026-11-25 02:35 | `live_ingestion_localization_v3_gemini_20261125.json` |
| GC-25 | Gemini detector | C | 2026-11-25 02:32 | `live_ingestion_localization_v2_gemini_20261125.json` |

One run per configuration. The first launch of GB-25 stopped before any provider call
because the image folder argument was wrong (`--localization-dir` must point to
`data/private-vision-review/real_img`); it was rerun with the correct folder and is not a
retry of failed calls.

**Provider failures: none.** Across 258 Gemini calls (58 detector + 61 vision in G-25,
59 vision in each of Y-25 and L-25, 21 detector calls in GB-25 and GC-25) there were
0 HTTP 429, 0 HTTP 503, 0 timeouts and 0 model-fallback events. Calls counted by the wrapper exceed one
per photo when the ingestion service asks for attributes of more than one detection.

**Cost.** Not measured per call. The prepaid balance was ₫150,000 before the runs; the
actual spend is read from the AI Studio Spend page and is not recorded here yet.

## 2. Localization: YOLO-World vs Gemini detector

Primary rule: one-to-one matching, IoU >= 0.5 and >= 90% of the annotated rectangle
retained. The IoU-only column drops the retention condition. 95% Wilson intervals in
brackets. YOLO-World figures are the 2026-11-19 runs; YOLO-World is deterministic for a
fixed model file and input, so it was not rerun.

| Set | YOLO-World | Gemini `3.6-flash` |
| :--- | :--- | :--- |
| B, all 14 photos | 17/47 = 36.2% [24.0, 50.5] | **25/47 = 53.2% [39.2, 66.7]** |
| B, IoU-only | 26/47 = 55.3% | **44/47 = 93.6% [82.8, 97.8]** |
| B, flat-lay multi-item (5) | 8/27 = 29.6% | **16/27 = 59.3% [40.7, 75.5]** |
| B, worn outfit (5) | 8/15 | 8/15 |
| B, hanger (4) | 1/5 | 1/5 |
| B, exact box count | 5/14 | 7/14 |
| C, all 7 photos | 5/10 | **9/10 [59.6, 98.2]** |
| C, exact box count | 2/5 | 5/5 |
| Predicted boxes, B / C | 32 / 9 | 60 / 11 |
| Median detector latency, B | 0.24 s | 5.3 s (p90 6.9 s) |

Per photo over sets B and C (21 photos), the Gemini detector matched more regions on 9,
fewer on 1, and the same number on 11. Exact two-sided sign test: p = 0.021.

- **Flat-lay multi-item photos, the weak point of the first report, double from 30% to
  59%.** Gemini proposes one box per garment where YOLO-World proposed 2 boxes for 6
  items and 1 box for 9 items.
- **Gemini finds almost every annotated garment (IoU-only 44/47).** Most remaining misses
  under the primary rule are retention failures: the box overlaps the garment but is
  tighter than the annotation, so the crop drops hems, soles or sleeves. Worn and hanger
  photos gain nothing under the primary rule for this reason.
- **Gemini proposes more boxes than annotated**, for example 5 to 6 boxes on worn photos
  annotated with 3 regions. Some extra boxes are real but unannotated items (section 7 of
  the first report); others are duplicates or parts. Precision is not measured, so this
  cost is not in the scores. In the application each extra box becomes a candidate the
  user must reject during review.

## 3. Attribute extraction (set A, 58 single-garment photos)

A provider failure counts as wrong. Garment group and type use the taxonomy aliases
added on 2026-11-19.

| Field | Y-19 | Y-25 | G-25 | L-25 |
| :--- | :--- | :--- | :--- | :--- |
| Category | 56/58 | 57/58 | 57/58 | 57/58 |
| Garment group | 56/58 | 54/58 | 57/58 | 56/58 |
| Garment type | 53/58 | 50/58 | 52/58 | 53/58 |
| Primary color | 51/58 | 53/58 | 54/58 | 52/58 |
| Pattern (9 classes) | 54/58 | 55/58 | 56/58 | 55/58 |
| Material, plausibility | 53/58 | 56/58 | 54/58 | 54/58 |
| Formality exact | 33/58 = 56.9% | 39/58 = 67.2% | 44/58 = 75.9% | 34/58 = 58.6% |
| Formality within one level | 57/58 | 58/58 | 58/58 | 57/58 |
| Formality MAE | 0.42 | 0.33 | 0.24 | 0.43 |
| Exactly one detection | 57/58 | 57/58 | 55/58 | 57/58 |
| Full-frame fallback box | 11/58 | 11/58 | 0/58 | 11/58 |
| Images with a vision error | 1 | 0 | 0 | 0 |
| Median end-to-end latency | 5.6 s | 7.7 s | 11.6 s | **2.5 s** |

Paired exact McNemar tests on the same 58 photos (discordant counts in brackets):

| Comparison | What it isolates | Largest difference | p |
| :--- | :--- | :--- | :--- |
| Y-19 vs Y-25 | Run-to-run variation (same configuration, 6 days apart) | Formality exact 33 vs 39 (3 vs 9) | 0.146 |
| Y-25 vs G-25 | Detector, same day | Formality exact 39 vs 44 (2 vs 7) | 0.180 |
| Y-25 vs L-25 | Vision model, same day | Formality exact 39 vs 34 (8 vs 3) | 0.227 |

All other fields have p >= 0.25. Y-19 and Y-25 assign the same formality level to only
46 of 58 photos.

- **On single-garment photos no difference between configurations is statistically
  significant.** The same configuration moves by up to 6 items between two days, which is
  as large as the differences between detectors or vision models. The 2026-11-19 figures
  are therefore one sample of a varying provider, not a fixed property of the pipeline.
- **The detector barely matters for one garment per photo.** Gemini always returns a box,
  YOLO-World falls back to the full frame on 11 photos, and attributes are equally good
  either way. This repeats the finding of the first report.
- **`gemini-3.5-flash-lite` is a usable baseline.** It matches `3.6-flash` within run
  variation on every field at about a third of the latency (2.5 s vs 7.7 s median).
  Formality is its weakest field (8 vs 3 discordant photos in favour of `3.6-flash`,
  not significant).

## 4. What the numbers mean for the thesis

1. Splitting a multi-item photo into garments is the stage where the detector choice
   matters. The Gemini detector localizes 53% of annotated garments at crop quality
   against 36% for YOLO-World, and 59% against 30% on flat-lay photos (sign test over
   photos p = 0.021). It costs about 5 s more per photo, a paid provider call, and extra
   candidate boxes to reject.
2. Attribute extraction from a single garment is strong for every configuration tested
   (category >= 96%, formality within one level >= 98%). Differences between models are
   smaller than the variation of one model between days, so a cheaper or faster model
   such as `gemini-3.5-flash-lite` is a defensible choice for this step.
3. Even with the better detector, about half of the garments in multi-item photos need a
   manual crop correction, so the review step before saving stays necessary.

The application default is unchanged (`DETECTOR_BACKEND=yolo_world`, `VISION_MODEL=gemini-3.6-flash`).
Switching either is an owner decision.

## 5. Limitations

- One run per configuration. The Y-19/Y-25 repeat shows that differences of a few items
  on set A are within run variation; set B and C runs of the Gemini detector were not
  repeated, so their variation is unknown.
- Sets B and C are small (21 photos, 57 regions) and set B uses web photos. There is no
  precision metric, and some visible items are unannotated.
- Gold limitations of the first report apply unchanged: attributes other than category
  were AI-drafted and reviewed by one person who saw the draft.
- `gemini-3.6-flash` and `gemini-3.5-flash-lite` are hosted models that can change
  without notice; the run dates above identify the versions measured.

## 6. Reproduce

```powershell
cd backend
python scripts/evaluate_live_ingestion.py --score ../data/fixtures/live_ingestion_attributes_v1_yolo_world.json ../data/fixtures/live_ingestion_attributes_v1_yolo_world_20261125.json ../data/fixtures/live_ingestion_attributes_v1_gemini_20261125.json ../data/fixtures/live_ingestion_attributes_v1_yolo_world_flash_lite_20261125.json
python scripts/evaluate_live_ingestion.py --score ../data/fixtures/live_ingestion_localization_v3_yolo_world.json ../data/fixtures/live_ingestion_localization_v3_gemini_20261125.json --localization-manifest ../data/fixtures/vision_real_review_v3.json
python scripts/evaluate_live_ingestion.py --score ../data/fixtures/live_ingestion_localization_v2_yolo_world.json ../data/fixtures/live_ingestion_localization_v2_gemini_20261125.json
```

Score summaries: `data/fixtures/live_ingestion_attributes_v1_scores_20261125.json`,
`live_ingestion_localization_v3_scores_20261125.json`,
`live_ingestion_localization_v2_scores_20261125.json`. The McNemar, sign-test, IoU-only and
per-group figures are computed from these per-item and per-case scores and from the raw
files; they are not printed by `--score`.

Live commands used (they call the paid Gemini API and are opt-in):

```powershell
python backend/scripts/evaluate_live_ingestion.py --live --detector gemini --out data/fixtures/live_ingestion_attributes_v1_gemini_20261125.json
python backend/scripts/evaluate_live_ingestion.py --live --detector gemini --skip-attributes --localization --localization-manifest data/fixtures/vision_real_review_v3.json --localization-dir data/private-vision-review/real_img --out data/fixtures/live_ingestion_localization_v3_gemini_20261125.json
python backend/scripts/evaluate_live_ingestion.py --live --detector gemini --skip-attributes --localization --localization-manifest data/fixtures/vision_real_review_v2.json --out data/fixtures/live_ingestion_localization_v2_gemini_20261125.json
python backend/scripts/evaluate_live_ingestion.py --live --detector yolo_world --out data/fixtures/live_ingestion_attributes_v1_yolo_world_20261125.json
# baseline: VISION_MODEL=gemini-3.5-flash-lite and VISION_FALLBACK_MODEL=gemini-3.5-flash-lite in the environment
python backend/scripts/evaluate_live_ingestion.py --live --detector yolo_world --out data/fixtures/live_ingestion_attributes_v1_yolo_world_flash_lite_20261125.json
```
