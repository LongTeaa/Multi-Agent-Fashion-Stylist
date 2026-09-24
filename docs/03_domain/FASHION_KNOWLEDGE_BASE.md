# Fashion Knowledge Base and Scoring Rules

## 1. Purpose

This document defines deterministic data and algorithms for unit-testing the Fashion Agent. These weights are an engineering baseline. A fashion-domain reviewer SHOULD validate them before they are presented as academic findings.

## 2. Taxonomy

### 2.1 Category

`top`, `bottom`, `dress`, `footwear`, `outerwear`, `accessory`.

### 2.2 Style

`casual`, `smart_casual`, `formal`, `streetwear`, `minimalist`, `vintage`.

### 2.3 Pattern

`solid`, `striped`, `checkered`, `graphic`, `floral`, `other`.

### 2.4 Color Families

| Family | Canonical values |
| :--- | :--- |
| neutral | white, black, grey, beige, cream, khaki, navy, brown, tan |
| red | red, burgundy, pink, coral |
| orange | orange, terracotta |
| yellow | yellow, mustard |
| green | green, olive, mint |
| blue | blue, light_blue, denim_blue, teal, navy |
| purple | purple, lavender |

`navy` MUST behave as a practical neutral for neutral combinations and as a blue-family shade for monochromatic evaluation.

## 3. Color Score

The score MUST use primary colors of major items. Accessories MUST NOT count toward the three-color rule.

| First matching condition | Score |
| :--- | :---: |
| All colors are neutral | 1.00 |
| Neutral base plus exactly one accent family | 0.95 |
| One non-neutral family with multiple shades | 0.90 |
| Two analogous families: red–orange, orange–yellow, yellow–green, green–blue, blue–purple | 0.85 |
| Two complementary families: red–green, orange–blue, yellow–purple, with at least one neutral anchor | 0.80 |
| No rule above matches | 0.55 |
| Three or more saturated families without a neutral anchor | 0.20 |

After selecting the base score, the implementation MUST apply:

`max(0, base_score - 0.20 * max(0, distinct_major_colors - 3))`.

## 4. Style Score

Pair scores MUST be symmetric. Outfit style score MUST be the mean of every major-item pair.

| Pair | Score |
| :--- | :---: |
| Identical style | 1.00 |
| casual–streetwear, casual–minimalist | 0.95 |
| smart_casual–minimalist, smart_casual–casual | 0.95 |
| smart_casual–formal | 0.85 |
| minimalist–vintage | 0.85 |
| casual–vintage, smart_casual–vintage | 0.80 |
| formal–minimalist | 0.75 |
| formal–casual | 0.55 |
| formal–streetwear | 0.20 |
| Unlisted pair | 0.60 |

## 5. Formality Score

Every item MUST have an integer formality level from 1 to 5. Let `average` be the mean formality of major items and `[minimum, maximum]` be the target range:

- If `average` is inside the range, score is `1.0`.
- Otherwise, let `distance` be the distance to the nearest boundary; score is `max(0, 1 - distance / 4)`.
- If the target range spans more than two levels, the Context Agent MUST lower confidence or request clarification.

## 6. Weather and Environment Score

The base score MUST be the proportion of major items whose `weather_suitability` contains the target weather condition.

| Rule | Adjustment |
| :--- | :---: |
| Hot weather with heavy outerwear | -0.40 |
| Cool weather without outerwear | -0.10; do not hard-reject |
| Cold weather without suitable outerwear | -0.40 |
| Rainy weather with light suede/canvas footwear | -0.25 |
| Outdoor + rainy without a water-resistant item | -0.20 |
| Indoor environment | Outerwear is optional |

The final score MUST be clamped to `[0,1]`. Material capabilities such as `breathable`, `heavy`, and `water_resistant` MUST be explicit metadata flags; a scoring function MUST NOT infer them arbitrarily from a display name.

## 7. Pattern and Proportion Score

Start at `1.0`, then apply:

- Each heavily patterned major item beyond the first: `-0.30`.
- Patterned top plus patterned bottom: additional `-0.20`.
- Oversized top plus oversized/wide bottom: `-0.15`, unless the target style is `streetwear`.
- Missing fit metadata: no penalty, but emit `fit_unknown`.

The result MUST be clamped to `[0,1]`.

## 8. Composite Fashion Score

```text
fashion_score =
  0.30 * color_score
  + 0.20 * style_score
  + 0.20 * formality_score
  + 0.20 * weather_environment_score
  + 0.10 * pattern_proportion_score
```

Ties MUST be resolved in this order: higher weather score, fewer recently worn items, then ascending `combo_id` for deterministic tests.

## 9. Combination Limits

The implementation MUST NOT materialize an unbounded Cartesian product. It SHOULD pre-rank each category, retain at most 15 items per category, generate no more than 500 combinations, and use bounded top-k selection.

Two branches are valid:

- `top + bottom + footwear`, with optional outerwear/accessory.
- `dress + footwear`, with optional outerwear/accessory.

## 10. Domain Validation

A fashion-domain reviewer SHOULD score at least 50 outfits from 1 to 5 for color harmony, context/formality, and overall quality. The thesis evaluation SHOULD report Spearman correlation between heuristic ranking and expert ranking and MUST record the rule-set version used.

## 11. Scoring Invariants

- **INVARIANT:** Every component score and composite score remains within `[0,1]`.
- **INVARIANT:** Identical input, rule version, and context produce identical ranking.
- **INVARIANT:** Accessories cannot make an otherwise incomplete outfit complete.
