# Personalization and Feedback Specification

## 1. Product Rules

- Users SHOULD select concise, visual options; they MUST NOT be required to write a long self-description.
- MVP feedback MUST use a 1–5 rating only. Like/Dislike MUST NOT be implemented.
- The application MUST NOT request a rating after every outfit.
- Personalization MUST be explainable reranking and MUST NOT infer sensitive traits.

## 2. Onboarding Options

Users MAY skip onboarding or select from these groups:

| Group | Canonical examples | Selection limit |
| :--- | :--- | :--- |
| Style | `casual`, `minimalist`, `smart_casual`, `streetwear`, `formal`, `vintage` | Maximum 3 |
| Color palette | `neutral`, `earth_tone`, `cool_tone`, `warm_tone`, `monochrome` | Maximum 3 |
| Priority | `comfort`, `polished`, `expressive`, `mobility`, `low_maintenance` | Maximum 3 |
| Explicit exclusions | Colors, patterns, or styles to avoid | Optional |
| Fit preference | `slim`, `regular`, `relaxed`, `oversized` | Optional |

Initial selections MUST map to versioned feature weights through a deterministic lookup. For example, `minimalist` may increase weights for solid patterns, neutral palettes, and clean silhouettes. An LLM MUST NOT assign personality traits.

## 3. Preference Model

MVP reranking MUST use this transparent baseline:

```text
preference_score =
  0.35 * style_match
  + 0.25 * color_palette_match
  + 0.20 * priority_match
  + 0.20 * learned_rating_affinity
  - explicit_avoid_penalty
  - recent_wear_penalty
```

`learned_rating_affinity` MUST be updated through an exponential moving average for features such as style, color family, pattern, and formality. Ratings map as follows: `1 -> -1.0`, `2 -> -0.5`, `3 -> 0`, `4 -> 0.5`, `5 -> 1.0`.

Before five ratings exist, onboarding weights MUST remain the primary signal and the UI MUST NOT claim that the system already understands the user's style. One rating MUST NOT cause an unbounded preference change; learned weights MUST be clamped to configured limits.

## 4. Feedback Cadence

The backend MUST maintain `eligible_outfit_count_since_prompt` and `next_feedback_threshold`. One count unit is a newly persisted outfit ID returned to the user, not one chat request.

- At initialization and after a valid rating, the service MUST choose a threshold in the inclusive range 5–10. Tests MUST inject or seed the chooser.
- After a successful response, the counter MUST increase by the number of new outfit IDs displayed, usually 1–3.
- Exact duplicate outfit IDs produced by regeneration MUST NOT increment the counter again.
- Errors, clarification responses, empty states, and responses without new outfits MUST NOT increment the counter.
- At the threshold, the API MUST return `feedback_prompt_eligible=true` and a `feedback_target_outfit_id` for the highest-ranked recent unrated outfit.
- The frontend SHOULD display the non-blocking Vietnamese prompt `Bạn chấm gợi ý vừa rồi mấy sao?`.
- If the user dismisses the prompt, a cooldown of at least three additional eligible outfits MUST apply.
- After a rating in the same session, proactive prompting MUST stop for the remainder of that session.

The user MAY manually rate an outfit from history at any time. Manual rating does not bypass validation or ownership checks.

## 5. Anti-Repetition

- An exact outfit confirmed as worn within the previous three days MUST receive a strong penalty.
- A major item confirmed as worn within 48 hours SHOULD receive a smaller penalty.
- A small wardrobe MUST NOT produce a hard rejection solely because of repetition; the response SHOULD explain the limited choice with Vietnamese user-facing copy.
- Only the explicit `worn` action creates wear history. Viewing or bookmarking an outfit does not mean it was worn.

## 6. Evaluation

- Offline ranking evaluation SHOULD report NDCG@3 and MRR over fixed synthetic or collected rating histories.
- Demonstration evaluation SHOULD compare average rating before and after preference updates.
- Grounding and context/formality correctness MUST NOT be weakened to optimize preference score.
- Cold-start tests MUST demonstrate reasonable ranking differences among at least three onboarding profiles.

## 7. Personalization Invariants

- **INVARIANT:** Rating stars are integers from 1 to 5.
- **INVARIANT:** Only ratings and wear events owned by the requesting user influence ranking.
- **INVARIANT:** A feedback prompt always references a persisted, unrated outfit owned by the same user.
- **INVARIANT:** Explicit exclusions take precedence over learned positive affinity unless satisfying them would make every valid outfit impossible; that relaxation MUST emit a warning.
