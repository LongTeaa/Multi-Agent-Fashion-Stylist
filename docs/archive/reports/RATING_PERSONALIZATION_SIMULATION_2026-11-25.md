# Rating-based personalization: offline simulation — 2026-11-25

Thesis criterion 6.1 "Độ sát với gu riêng của người dùng" asks whether recommendations
follow a user's taste as they rate outfits. The benchmark measures onboarding preferences
(profile differentiation 5/5) but not learning from 1–5 star ratings, which
`PERSONALIZATION_AND_FEEDBACK_SPEC.md` section 6 asks to evaluate ("compare average
rating before and after preference updates"). This report measures it with simulated
users. No application code was changed.

## 1. Method

- **Path.** `backend/scripts/simulate_rating_personalization.py` drives the real API in a
  temporary migrated SQLite database: `POST /api/v1/stylist/chat` for recommendations,
  `PUT /api/v1/outfits/{id}/rating` (source `manual`) for feedback,
  `GET /api/v1/user/profile` for the learned weights. Providers are deterministic and
  offline (rule context parser, no weather, no LLM explanation). The learning rule is the
  application's: per-feature EMA (alpha 0.30) over style, colour, pattern and formality
  band, used once five ratings exist.
- **Users.** Two benchmark wardrobes (`female_realistic_30`, `male_realistic_27`) × three
  hidden tastes = 6 rated users, each with a twin control user that receives the same
  requests but never rates. All start with empty onboarding choices, so ratings are the
  only preference signal.
- **Hidden tastes** (defined before the run, in the script): `dark_minimal` (black, navy,
  grey; minimalist), `light_casual` (white, cream, beige, khaki, light blue, pink, yellow;
  casual, streetwear), `earthy` (brown, beige, olive, khaki, camel, burgundy; vintage).
  Each major item (top, bottom, dress, outerwear, footwear) scores the mean of its colour
  and style preference in [-1, 1]; an outfit's stars are
  `clamp(round(3 + 2 × mean item score), 1, 5)`.
- **Protocol.** The benchmark's `ok` cases for each wardrobe are split by id into
  training (alternate cases) and evaluation queries. The rated user rates the rank-1
  outfit of each training request with its hidden stars. After 0, 5, 10, 15 and 20
  ratings, both users run every evaluation query and the returned outfits are scored
  with the hidden taste. 75 evaluation requests per checkpoint, of which 63 return
  outfits (the rest ask for clarification), identical for both conditions.
- **Metrics.** Mean stars of the rank-1 outfit; Hit@1 (rank 1 has >= 4 stars); MRR@3
  (first outfit with >= 4 stars); share of liked outfits in the top 3. Paired exact sign
  test on rank-1 stars, rated minus control, at 20 ratings.

Two runs gave identical results.

## 2. Results

Pooled over the 6 users (63 answered evaluation requests per checkpoint):

| Ratings given | Rated: top-1 stars | Rated: Hit@1 | Rated: MRR@3 | Rated: liked in top 3 | Control: top-1 stars |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 0 | 3.17 | 36.5% | 0.458 | 32.8% | 3.17 |
| 5 | 3.25 | 41.3% | 0.482 | 34.9% | 3.17 |
| 10 | 3.25 | 41.3% | 0.482 | 34.4% | 3.17 |
| 20 | 3.24 | 39.7% | 0.476 | 33.9% | 3.17 |

At 20 ratings the rated user's rank-1 outfit was better than the control's on 4 of 63
requests, worse on 0 and equal on 59 (sign test p = 0.125). The control stayed constant,
so repeated requests alone do not change the ranking. Per user, only
`male_realistic_27/dark_minimal` changed (top-1 stars 2.91 → 3.27, Hit@1 9% → 27%); the
other five users received the same rank-1 outfits as their controls.

**The learning step works.** After 20 ratings every rated user had learned weights that
match its hidden taste, for example `light_casual` on the female wardrobe:
`color:khaki` +1.00, `color:pink` +1.00, `style:casual` +0.68, `color:beige` +0.62; and
`earthy`: `color:brown` +0.50, `style:formal` −0.50 (full weights in the JSON summary).

## 3. Why the ranking barely moves

The learned signal is deliberately small in the composite score:

`composite share of learned affinity = w_pers × 0.20 × (affinity − 0.5)`, with
affinity in [0, 1] and `w_pers` 0.10 (formal, active), 0.15 (comfort) or 0.20 (balanced),
so the largest possible shift is **±0.01 to ±0.02** of a composite score in [0, 1]
(`PERSONALIZATION_AND_FEEDBACK_SPEC.md` section 3, `context_scoring.py`). Context
differences between candidate outfits (formality fit, weather, function) are usually
larger, so ratings only reorder near-ties. This matches the specification's intent that
one rating "MUST NOT cause an unbounded preference change", but at this size twenty
ratings are also not enough to change most recommendations.

## 4. What the thesis can claim

- Ratings are stored, turned into explainable per-feature weights that move in the
  direction of the user's taste, and never break constraints or grounding.
- Their effect on what is recommended is small by design: in this simulation, rank-1
  quality rose from 3.17 to 3.24 stars with no request made worse, not a significant
  difference. Onboarding choices (profile differentiation 5/5) are the stronger
  personalization signal.

## 5. Limitations

- Simulated tastes use only the features the learner sees (colour and style), which
  favours the learner; real users also weigh fit, comfort and context.
- One feedback policy (rate rank 1 only); rating more outfits per request, or rating
  outfits the system did not rank first, would give the learner more varied evidence.
- Small wardrobes (27–30 items) and 12–13 evaluation queries per wardrobe.
- Deterministic offline context; the live LLM context path was not used.

## 6. Reproduce

```powershell
python backend/scripts/simulate_rating_personalization.py --out data/private-rating-simulation/summary.json
```

Summary of this run: `RATING_PERSONALIZATION_SIMULATION_2026-11-25.json`.
