# Try-On Provider Spike: FASHN Try-On v1.6 vs FLUX VTO (2026-11-22)

Roadmap: `docs/07_implementation/ROADMAP.md`, Phase 3. Decision: switch virtual try-on to FLUX VTO (Phase 4).

## 1. Question

The application rendered try-on with FASHN VTON v1.5 on a Hugging Face ZeroGPU Space. It took about 37 s per garment pass, and the second pass of an outfit usually failed under the anonymous ZeroGPU quota (`FASHN_VTON_SPIKE_REPORT.md`). Neither candidate vendor publishes quantitative quality results, so the two paid replacements were measured on the project's own outfits.

| Arm | Model (host) | Calls per outfit |
| :--- | :--- | :--- |
| FASHN | `fal-ai/fashn/tryon/v1.6` (fal.ai) | One per garment, chained: the bottom pass wears the top pass output, as `tryon_service` does |
| FLUX | `fal-ai/flux-pro/v1/vto` (fal.ai) | One: garments merged left to right into one composite, with a prompt built only from recorded attributes |

## 2. Method

- **Cases:** ten outfits from the two demo wardrobes, selected deterministically by `spike_tryon_providers.py plan`: the persisted outfits plus fills so each user has three upper + bottom cases and, when the wardrobe has dresses, three dress cases. Seven upper + bottom (four male, three female) and three dress.
- **Inputs:** both arms received the same preset avatar downscaled to at most 1 MP, and the same garment crops. Garments are chosen with the application rule: a dress alone, otherwise outerwear over a top, plus the bottom. Footwear and accessories are not rendered.
- **Run:** one repeat, 2026-11-20 08:11–08:16 UTC, call order alternating per case. Latency is end to end per outfit, including the final image download.
- **Rating:** a blind bundle labelled results A/B by a salted per-case permutation, and re-encoded every result as JPEG at 1024 px height so format or size could not identify the model. Three raters scored each of the 20 results 1–5 for garment fidelity (color, pattern, cut), person preservation (face, pose, background) and realism, and could flag a result as unacceptable.

| Rater | Role |
| :--- | :--- |
| R1 | Project owner. Designed and ran the spike and had seen one agent remark about case male-03, so **not blind** |
| R2, R3 | Friends of the owner, not fashion specialists, blind to the mapping |

## 3. Results

### 3.1 Operations (20 of 20 renders succeeded)

| | FASHN v1.6 | FLUX VTO |
| :--- | ---: | ---: |
| Succeeded | 10/10 | 10/10 |
| Outfit latency p50 / p95 / max | 20.4 s / 25.2 s / 25.2 s | 7.0 s / 17.8 s / 17.8 s |
| Upper + bottom median | 22.3 s | 7.0 s |
| Dress median | 10.4 s | 8.2 s |
| Model calls per outfit | 1.7 | 1.0 |
| Median model call | 9.0 s (first call of the run 20.8 s) | 6.1 s |
| Native output | PNG 864×1157 | JPEG 736×1024 |
| Estimated cost per outfit | $0.1275 | $0.0475 |

Total estimated cost $1.75 (FASHN 17 calls at $0.075; FLUX ten calls at $0.0475), using fal.ai prices read on 2026-11-20.

### 3.2 Blind quality ratings (3 raters × 20 results)

| | FASHN v1.6 | FLUX VTO |
| :--- | ---: | ---: |
| Garment fidelity (1–5) | 3.83 | **4.73** |
| Person preservation | 4.97 | 4.93 |
| Realism | 4.60 | **5.00** |
| Flagged unacceptable | 4/30 (13%) | 0/30 |

| Case | Branch | FASHN fidelity | FLUX fidelity | Unacceptable flags (FASHN / FLUX) |
| :--- | :--- | ---: | ---: | :--- |
| female-01 | dress | 4.67 | 4.33 | 0 / 0 |
| female-02 | dress | 4.67 | 5.00 | 0 / 0 |
| female-03 | upper + bottom | 4.33 | 5.00 | 0 / 0 |
| female-04 | upper + bottom | 3.33 | 5.00 | 0 / 0 |
| female-05 | upper + bottom | 3.00 | 5.00 | 2 / 0 |
| female-06 | dress | 3.33 | 4.67 | 0 / 0 |
| male-01 | upper + bottom | 3.67 | 4.67 | 2 / 0 |
| male-02 | upper + bottom | 4.67 | 4.33 | 0 / 0 |
| male-03 | upper + bottom | 3.00 | 5.00 | 0 / 0 |
| male-04 | upper + bottom | 3.67 | 4.33 | 0 / 0 |

- FLUX had the higher mean garment fidelity on 8 of 10 cases; FASHN led on two, by 0.33 each.
- The gap is largest on upper + bottom outfits (FASHN 3.67, FLUX 4.76, n = 21 ratings each) and smaller on dresses (4.22 vs 4.67, n = 9). This is consistent with the chained second pass degrading the first garment or rendering the bottom inaccurately (for example, blue jeans rendered as dark trousers in male-03).
- Each rater, separately, rated FLUX higher: R1 4.9 vs 4.2, R2 4.5 vs 3.5, R3 4.8 vs 3.8. Excluding the non-blind R1 does not change the direction.
- Agreement on garment fidelity: within one point on 90–100% of results for every rater pair; exact agreement 35–70%.
- A two-sided sign test on the ten case-level differences gives p = 0.109. The direction is consistent, but **the difference is not statistically significant at 5% with ten cases**.

## 4. Decision

Switch the application's virtual try-on to FLUX VTO through fal.ai. On the project's own outfits it was faster (p50 7.0 s vs 20.4 s), cheaper ($0.0475 vs $0.1275 per outfit), never flagged unacceptable, and rated higher on garment fidelity and realism, while person preservation was equal. FASHN remains selectable as an adapter; the moodboard fallback is unchanged.

## 5. Limitations

- Ten cases and three non-expert raters, one of them not blind; treat the result as a preliminary comparison, not a significance claim.
- Preset avatars only; no user-uploaded photos were rendered.
- Inputs are crops of real wardrobe photos, not product photos, which favours neither vendor's marketing examples.
- Both models were measured through fal.ai. fal serves FLUX VTO v1; Black Forest Labs recommends `vto-v2` (2026-07-17), available only on its own API, so FLUX may score below its latest version. FASHN may be faster on its own API.
- One repeat only; the p95 latency rests on ten outfits per arm.

## 6. Reproduction

Frozen inputs to scoring: `data/fixtures/tryon_spike_raw_v1_20261120.json` (no payloads, image URLs, user identifiers or keys) and the pseudonymized ratings `data/fixtures/tryon_spike_ratings_v1_R1.json`, `_R2.json`, `_R3.json`. From the repository root:

```powershell
python backend/scripts/spike_tryon_providers.py score --raw data/fixtures/tryon_spike_raw_v1_20261120.json --ratings data/fixtures/tryon_spike_ratings_v1_R1.json data/fixtures/tryon_spike_ratings_v1_R2.json data/fixtures/tryon_spike_ratings_v1_R3.json
```

Rendered images, the blind bundle and the case plan with demo user identifiers stay in the git-ignored `data/private-tryon-spike/`.
