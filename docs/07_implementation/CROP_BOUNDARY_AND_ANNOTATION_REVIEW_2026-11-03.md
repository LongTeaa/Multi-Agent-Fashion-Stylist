# Crop boundaries and annotation review — 2026-11-03

This follow-up rechecks the worn-trousers reference on the original 469×654 photo
and adds a fixed boundary corpus. It makes no new external model calls and does
not change the production crop policy or existing wardrobe media.

## Annotation versioning

`vision_real_review_v1.json` remains unchanged. The new
`vision_real_review_v2.json` keeps the same seven source digests, thresholds and
six other cases; only the worn-trousers reference rectangles change. The runner
defaults to v2. Pass `--manifest data/fixtures/vision_real_review_v1.json` to
reproduce a historical v1 run.

The review used the source image without prediction overlays, plus source pixel
row inspection to check visible navy garment extents. This was the same coding
agent, with knowledge of earlier predictions: it is not blinded annotation or an
independent human/inter-rater review. Rectangles remain coarse rather than masks.

| Reference | v1 normalized XYXY | v2 half-open source pixels |
| :--- | :--- | :--- |
| Trousers | `[0.24, 0.08, 0.84, 0.96]` | `[136, 51, 392, 624]` |
| Visible shoe pair | `[0.31, 0.91, 0.98, 1]` | `[150, 603, 456, 654]` |

The old trouser left edge was at pixel 112.56 and included substantial background
and hand area. The revised left edge encloses the visible garment extent. The
shoe reference is restricted to the visible pair, whose lower boundary is already
truncated by the original image edge. Reference crops were inspected locally.

Reassessing the **same frozen predictions**, with unchanged IoU >= 0.5 and
retention >= 0.9, changes matched regions from 0/2 to 2/2. This is an annotation
effect, not improved model accuracy. Independently shifting each of four pixel
edges by -3/0/+3 gives 81 variants per reference: trousers pass 81/81 and shoes
76/81. The small visible shoe region remains sensitive to annotation uncertainty.
`vision_annotation_review_20261103.json` records manifest digests and these results;
unit tests recompute the comparison and all perturbations.

## Boundary corpus

`crop_boundary_v1.json` contains three private real-photo crop cases and six
deterministic marker cases. Real cases cover a polo near a face rectangle,
partially visible shoes next to trousers, and the isolated Derby correction.
Synthetic cases use red bands as protected source pixels; they are not actual
faces or evidence of face detection. They cover worn scenes, multiple candidates
despite a `single_item` label, an inferred scene, low confidence, image-edge
clipping, and a deliberately confidently wrong singleton report.

The evaluator runs the same scene normalization, crop policy and crop engine as
the application. It counts protected source pixels before/after, retaining any
baseline overlap instead of claiming every crop starts face/neighbor free. Source
photos and crop PNGs remain in the ignored private directory.

| Outcome | Result |
| :--- | :--- |
| Fixture/policy conformance | 9/9 cases |
| Cases with protected regions and no additional protected pixels | 6/6 |
| Positive controls (Derby margin and image-edge clipping) | 2/2 |
| Negative control with added protected pixels | 1/1; 1,680 added pixels |

**Conformance is not universal safety.** If a detector confidently labels a scene
as one shoe while omitting a nearby person/garment, the current 2% margin can
include that unreported region. The negative control explicitly fails the
protected-region guard and remains recorded as a known limitation; its inclusion
does not turn it into a successful safety case. The CLI returns success for the
documented policy/guard fixtures while reporting this limitation separately.

The runtime remains `isolated-footwear-margin-v1`; no broader garment expansion
is justified by this corpus. Manual crop coordinates remain exact. A useful next
improvement is retaining the raw detector rectangle alongside the effective crop
and making the unexpanded rectangle easy to restore during review. That improves
user control but does not solve missed-scene detection by itself.

## Reproduction and verification

From the repository root:

```powershell
python backend/scripts/evaluate_crop_boundaries.py --report data/fixtures/crop_boundary_results_20261103.json
python backend/scripts/evaluate_real_ingestion.py
```

Both commands are offline. The boundary command needs the retained private photos;
synthetic cases run in the unit suite without those files. Results are checked in
as `crop_boundary_results_20261103.json`. The real-image replay passed seven photos,
ten crops, later-source editing/reload, explicit confirmation and idempotency.

Backend verification: 26 tests passed across boundary pixels, annotation versions,
crop policy, geometry metrics, evaluation runner and crop API integration. The
Windows sandbox's long Temp paths initially prevented ObjectStorage writes; the
same replay and test commands passed outside that sandbox. Private paths and
source photo bytes are not included in committed artifacts.
