# Live-provider ingestion evaluation — 2026-11-19

Roadmap Phase 1. This report measures the deployed wardrobe digitization pipeline
(detector → crop policy → Gemini Vision attributes) on real photos. It resolves the
measurement part of `ALIGNMENT_BACKLOG.md` item T-2. The planned comparison between
the YOLO-World and Gemini detectors is **incomplete**: every Gemini-detector request in
the localization runs, and 54 of 58 in the attribute run, failed on provider quota or
availability (section 6). All YOLO-World figures below come from complete runs.

## 1. Setup

| Item | Value |
| :--- | :--- |
| Code | `main` at `38e971f` plus the Phase 1 working tree |
| Pipeline | `create_ingestion_batch` → `process_ingestion_batch` (real service), isolated temporary SQLite and local object store, one batch per photo |
| Detector A | YOLO-World `yolov8s-worldv2.onnx`, confidence 0.25, IoU 0.45, padding 0.05, crop policy `AUTO_CROP_POLICY_VERSION` |
| Detector B | Gemini `gemini-3.6-flash` native detection (failed; section 6) |
| Vision | Gemini `gemini-3.6-flash`, fallback `gemini-3.5-flash-lite`, 30 s timeout |
| Runner | `backend/scripts/evaluate_live_ingestion.py` (`--live`, then `--score` offline) |
| Runs | Start times 2026-11-19 UTC: attributes 07:54 (YOLO-World) and 08:01 (Gemini); localization 08:04 (YOLO-World) and 08:32–08:35 (Gemini). One run per configuration; no retries were pooled. |

Each provider call is wrapped and recorded (output, latency, exception). The ingestion
service converts provider failures into warnings and a full-frame fallback crop; the
wrapper makes those failures visible. Raw provider outputs are frozen in
`data/fixtures/live_ingestion_*.json`; every number here is recomputed from them by
`--score`.

## 2. Datasets

| Set | Photos | Gold | Provenance |
| :--- | :--- | :--- | :--- |
| A. Attributes `vision_attribute_gold_v1.json` | 58 CC0 single-garment photos (`demo_wardrobe_v1`), flat or on a hanger | category, garment group, garment type, primary color, pattern, material, formality 1–5 | Category from the source dataset (57) plus one owner correction (`demo-21`, source label Dress, relabelled top). Other fields drafted by an AI assistant, then reviewed item by item by the owner (58/58 reviewed; 7 field values changed). |
| B. Localization `vision_real_review_v3.json` | 14 web photos: 5 flat-lay multi-item, 5 worn outfits, 4 hanger | 47 rectangles, expected box count per photo | Drawn by the owner in `scripts/annotation_tool.html`; 7 category labels corrected to the taxonomy by the assistant with owner approval (`category_corrections`). |
| C. Localization `vision_real_review_v2.json` | 7 private photos | 10 rectangles, 5 count targets | Existing coarse rectangles (2026-11-02/03). |

Item confirmations stored in the app were rejected as gold: they equal the provider
proposal on 59 of 60 demo items, so they would measure the provider against itself.

Gold fields list every acceptable value (for example teal = blue or green). Free-text
provider output is normalized onto the 13 taxonomy colors, 9 pattern classes and 8
fiber families (`backend/app/services/vision_evaluation.py`). Garment group and type
use the application's own `garment_taxonomy.classify`, so they measure what the app
would display, not only what the model said.

## 3. Attribute results (set A, YOLO-World + Gemini Vision)

A provider failure counts as wrong. 95% Wilson intervals in brackets.

| Field | Correct | Accuracy |
| :--- | :--- | :--- |
| Category (6 classes) | 56/58 | 96.6% [88.3, 99.0] |
| Garment group (8 app groups) | 54/58 | 93.1% [83.6, 97.3] |
| Garment type | 46/58 | 79.3% [67.2, 87.7] |
| Primary color | 51/58 | 87.9% [77.1, 94.0] |
| Pattern (9 classes) | 54/58 | 93.1% [83.6, 97.3] |
| Solid vs patterned | 55/58 | 94.8% |
| Material, visual plausibility | 53/58 | 91.4% [81.4, 96.3] |
| Formality exact | 33/58 | 56.9% [44.1, 68.8] |
| Formality within one level | 57/58 | 98.3% [90.9, 99.7] |

Formality MAE 0.42; mean signed error −0.35, so the provider rates garments about a
third of a level less formal than the gold. Per-class category recall: bottom 12/12,
dress 4/4, footwear 8/8, outerwear 9/9, top 20/21, accessory 3/4. The two category
errors are one provider failure (`demo-31`, connection reset) and `demo-21`, which the
provider called a dress while the owner labelled it a top.

Detection on single-item photos: exactly one proposed item on 57/58; YOLO-World found
nothing on 11/58, so the app used the whole photo. Attribute accuracy on those 11 was
comparable (category 11/11, color 10/11), so on single-item photos the fallback hides
detector misses. Median end-to-end time 5.6 s per photo (p90 13.9 s, max 20.3 s),
dominated by the vision call; YOLO-World itself takes about 0.2–0.3 s.

### Error analysis

- **Taxonomy alias gaps (integration defect, not model error).** 8 of the 12 garment-type
  misses are plausible names the taxonomy does not map: `camisole`, `culottes`,
  `leggings`, `evening_dress`, `sheath_dress`, `tunic`, `cap`, `beanie`. For bottoms this
  also loses the group: `culottes` and `leggings` resolve to no group, so the app cannot
  place them under Quần. Fixed after the run; see section 3.1.
- **Color.** 7 misses, mostly dark/desaturated shades: olive-grey read as beige, navy
  read as blue, blue-grey parka read as purple, light-blue dress shirt read as grey, a
  multicolor knit sneaker with no single color.
- **Pattern.** A lace shirt read as floral, a sequin-and-fringe dress read as floral, a
  micro-patterned shirt read as graphic.
- **Material.** Misses are wool blazers and a knit sweater proposed as synthetic or
  cotton; material is not reliably observable from a photo and is reported as
  plausibility only.

### 3.1 After adding taxonomy aliases (offline re-score)

The observed names were added as aliases of existing types in
`backend/app/services/garment_taxonomy.py`: camisole → tanktop, tunic → blouse,
culottes and leggings → trousers, sheath dress → dress, evening dress (and gown) →
formal_dress, cap, baseball cap, beanie and beret → hat. No gold label, normalization
table or provider output was changed; the frozen raw file was re-scored offline, so the
model proposals are identical and only the application's mapping differs.

| Field (YOLO-World run) | As measured | With aliases |
| :--- | :--- | :--- |
| Garment group | 54/58 = 93.1% | 56/58 = 96.6% [88.3, 99.0] |
| Garment type | 46/58 = 79.3% | 53/58 = 91.4% [81.4, 96.3] |

Other fields are unchanged. The aliases fix 7 of the 8 alias cases; `demo-21` stays wrong
because the provider chose category dress (subtype tunic) while the gold is top. The
remaining garment-type misses are real recognition errors (a printed skirt read as
shorts, a half-zip fleece read as a jacket, perforated loafers read as sneakers) and the
`demo-31` provider failure. In the Gemini-detector run, garment type also rises from
46/58 to 53/58 and garment group from 53/58 to 54/58. Because items store the provider
subtype and the app resolves groups at read time, existing wardrobe items with these
subtypes are grouped correctly without a data migration. Scores:
`data/fixtures/live_ingestion_attributes_v1_scores_taxonomy_aliases.json`.

## 4. Localization results (YOLO-World)

Primary rule (as in `TEST_STRATEGY.md` 3.2): one-to-one matching with IoU ≥ 0.5 and
≥ 90% of the annotated rectangle retained by the crop. The IoU-only column drops the
retention condition.

| Set | Regions matched | IoU-only | Exact box count |
| :--- | :--- | :--- | :--- |
| B, all 14 photos | 17/47 = 36.2% [24.0, 50.5] | 26/47 = 55.3% [41.2, 68.6] | 5/14 |
| B, flat-lay multi-item (5) | 8/27 = 29.6% | 9/27 = 33.3% | 1/5 |
| B, worn outfit (5) | 8/15 = 53.3% | 13/15 = 86.7% | 1/5 |
| B, hanger (4) | 1/5 = 20.0% | 4/5 = 80.0% | 3/4 |
| C, all 7 photos | 5/10 = 50.0% | 6/10 = 60.0% | 2/5 |

By annotated category on set B (any-match, retention rule): bottom 8/10, top 5/13,
outerwear 1/4, accessory 2/8, footwear 1/11, dress 0/1.

- **Worn and hanger photos:** YOLO-World usually finds the garment (IoU-only 87% and 80%)
  but its box is tighter than the annotation, so the crop drops part of the garment
  (hems, soles, sleeves). Shoes on a wearer are found on 4 of 5 photos but fail
  retention.
- **Flat-lay multi-item photos are the weak point:** 2 boxes for 6 items, 1 box for 9
  items. Open-vocabulary labels are noisy (loafers and a T-shirt labelled `bag`, jeans
  labelled `coat`); the label only guides the vision prompt, which assigns the category.
- Three isolated garments in set C (a sneaker pair, two T-shirts) and one hanger T-shirt
  in set B produced no box at all.

## 5. What the numbers mean for the thesis

Attribute extraction by Gemini Vision is strong on single-item photos (category ≈ 97%,
color ≈ 88%, formality within one level ≈ 98%). The weak stage is splitting a multi-item
or worn photo into garments: YOLO-World keeps about one in three annotated garments at
crop quality, about half when only overlap is required. The user-confirmation step of
the ingestion flow (no item is saved before review, crops are editable) is therefore a
necessary part of the design, not a formality.

## 6. Gemini detector run (incomplete)

| Run | Requests | Failures |
| :--- | :--- | :--- |
| Attributes, set A | 58 detector calls | 54: 36 × HTTP 429, 7 × HTTP 503, 11 × timeout |
| Localization, set B | 14 | 14 × HTTP 429 |
| Localization, set C | 7 | 7 × HTTP 429/provider error |

The 429 responses report a quota of 20 requests per day for `gemini-3.6-flash` with a
retry delay of about 23 hours. Detector errors fell back to full-frame crops, so the
attribute run is effectively a full-frame-crop condition for 54 photos; its scores
(category 55/58, color 50/58, pattern 53/58, formality within one 56/58, median 26.7 s
because of failed detector calls) are within about one item of the YOLO-World run. This
is consistent with section 3 (crops matter little on single-item photos) but it is not a
designed ablation and **must not be reported as Gemini-detector accuracy**. Vision calls
in the same run failed only twice, so quota exhaustion affected detector requests most.
The provider log counter recorded no model-fallback events; it observes only the vision
provider's fallback log line, so it does not prove that no fallback occurred.

## 7. Limitations

- Gold attributes other than category were AI-drafted and reviewed by one person who
  knew the draft; this is not blind or inter-rater ground truth. Accepted-value lists
  and normalization tables were written before the scored run and were not changed after.
- Set B uses web/stock photos (some watermarked), not photos from real users, and is
  small (14 photos, 47 regions). Some visible items remain unannotated (for example a
  cap and belt in `images_bayra3`, jeans in `images_bayra4`, a bag and a jacket carried
  by wearers), and one rectangle in `images_bayra3` covers two stacked tops. There is no
  precision metric: extra predicted boxes are not penalized, and box counts for those
  photos exclude the unannotated items.
- One run per configuration; provider latency and availability vary by time and quota.
- Set A has single garments only; set A results do not transfer to worn photos.

## 8. Follow-ups

1. Done: taxonomy aliases added and re-scored (section 3.1).
2. Rerun the Gemini detector on sets A, B and C after the daily quota resets or with a
   paid key, to complete the detector comparison.
3. Consider a small margin for worn and hanger crops, and investigate why isolated
   T-shirts produce no YOLO-World box.

## 9. Reproduce

```powershell
cd backend
python scripts/evaluate_live_ingestion.py --score ../data/fixtures/live_ingestion_attributes_v1_yolo_world.json ../data/fixtures/live_ingestion_attributes_v1_gemini.json
python scripts/evaluate_live_ingestion.py --score ../data/fixtures/live_ingestion_localization_v3_yolo_world.json --localization-manifest ../data/fixtures/vision_real_review_v3.json
python scripts/evaluate_live_ingestion.py --score ../data/fixtures/live_ingestion_localization_v2_yolo_world.json
```

Score summaries: `data/fixtures/live_ingestion_attributes_v1_scores.json`,
`live_ingestion_localization_v3_scores.json`, `live_ingestion_localization_v2_scores.json`.
Private photos stay in the git-ignored `data/private-vision-review/`.
