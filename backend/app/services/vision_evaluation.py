"""Metrics for opt-in real-image evaluation, independent of providers.

Geometry helpers measure localization. Attribute helpers compare normalized
provider proposals with a gold set whose fields list every accepted value.
"""
from __future__ import annotations

from collections import Counter
from statistics import median
from typing import Any

from pydantic import BaseModel, Field

from app.models.entities import BoundingBox, WardrobeCategory
from app.services.garment_taxonomy import COLORS, classify, normalize


def box_iou(left: BoundingBox, right: BoundingBox) -> float:
    intersection = max(0.0, min(left[2], right[2]) - max(left[0], right[0])) * max(
        0.0, min(left[3], right[3]) - max(left[1], right[1])
    )
    union = (left[2] - left[0]) * (left[3] - left[1]) + (
        right[2] - right[0]
    ) * (right[3] - right[1]) - intersection
    return intersection / union if union > 0 else 0.0


def region_retention(expected: BoundingBox, predicted: BoundingBox) -> float:
    """Fraction of the annotated garment rectangle retained by a crop."""
    area = (expected[2] - expected[0]) * (expected[3] - expected[1])
    intersection = max(0.0, min(expected[2], predicted[2]) - max(expected[0], predicted[0])) * max(
        0.0, min(expected[3], predicted[3]) - max(expected[1], predicted[1])
    )
    return intersection / area if area > 0 else 0.0


def region_coverage(
    expected: list[BoundingBox], predicted: list[BoundingBox], threshold: float = 0.5,
    min_retention: float = 0.0,
) -> dict[str, int | float]:
    """Maximum one-to-one match count, so one full-frame box cannot cover all items.

    This is localization coverage only, not semantic category/attribute accuracy.
    """
    choices = [[i for i, box in enumerate(predicted) if box_iou(region, box) >= threshold
                and region_retention(region, box) >= min_retention]
               for region in expected]
    assigned: dict[int, int] = {}

    def match(region: int, visited: set[int]) -> bool:
        for prediction in choices[region]:
            if prediction in visited:
                continue
            visited.add(prediction)
            if prediction not in assigned or match(assigned[prediction], visited):
                assigned[prediction] = region
                return True
        return False

    count = sum(match(index, set()) for index in range(len(expected)))
    return {"expected_regions": len(expected), "predicted_regions": len(predicted),
            "matched_regions": count, "coverage": count / len(expected) if expected else 0.0}


# --- Attribute normalization -------------------------------------------------

# Extra spellings seen in free-text provider output, mapped onto taxonomy colors.
# A two-color value means the shade sits between two canonical colors.
_COLOR_SHADES: dict[str, tuple[str, ...]] = {
    "light blue": ("blue",), "sky blue": ("blue",), "baby blue": ("blue",), "denim": ("blue",),
    "denim blue": ("blue",), "dark blue": ("blue", "navy blue"), "royal blue": ("blue",),
    "indigo": ("blue", "navy blue"), "navy": ("navy blue",), "midnight blue": ("navy blue",),
    "teal": ("blue", "green"), "turquoise": ("blue", "green"), "aqua": ("blue", "green"),
    "mint": ("green",), "olive": ("green",), "khaki green": ("green",), "dark green": ("green",),
    "sage": ("green", "grey"), "charcoal": ("grey",), "dark grey": ("grey",), "light grey": ("grey",),
    "silver": ("grey",), "heather grey": ("grey",), "cream": ("beige", "white"),
    "ivory": ("white", "beige"), "off white": ("white", "beige"), "nude": ("beige", "pink"),
    "tan": ("beige", "brown"), "camel": ("beige", "brown"), "khaki": ("beige",),
    "taupe": ("beige", "brown"), "sand": ("beige",), "burgundy": ("red", "purple"),
    "maroon": ("red",), "wine": ("red", "purple"), "coral": ("orange", "pink"),
    "magenta": ("pink", "purple"), "fuchsia": ("pink", "purple"), "lavender": ("purple",),
    "lilac": ("purple",), "mustard": ("yellow",), "rust": ("orange", "brown"),
    "blush": ("pink",), "rose": ("pink",),
}

PATTERN_CLASSES = ("solid", "striped", "plaid", "floral", "animal", "graphic", "print", "lace", "embellished")

_PATTERN_ALIASES: dict[str, str] = {
    "plain": "solid", "none": "solid", "textured": "solid", "quilted": "solid", "ribbed": "solid",
    "knit": "solid", "cable knit": "solid", "perforated": "solid", "mesh": "solid",
    "solid color": "solid", "heathered": "solid", "melange": "solid",
    "stripes": "striped", "stripe": "striped", "pinstripe": "striped", "pinstriped": "striped",
    "check": "plaid", "checked": "plaid", "checkered": "plaid", "tartan": "plaid",
    "gingham": "plaid", "flannel": "plaid",
    "flower": "floral", "botanical": "floral", "tropical": "floral", "leaf": "floral",
    "leopard": "animal", "animal print": "animal", "snake": "animal", "snakeskin": "animal",
    "zebra": "animal",
    "logo": "graphic", "text": "graphic", "lettering": "graphic", "graphic print": "graphic",
    "printed": "print", "abstract": "print", "geometric": "print", "polka dot": "print",
    "polka dots": "print", "dotted": "print", "paisley": "print", "camouflage": "print",
    "camo": "print", "space dye": "print", "multicolor": "print", "star": "print", "stars": "print",
    "crochet": "lace", "eyelet": "lace",
    "sequin": "embellished", "sequined": "embellished", "sequins": "embellished",
    "beaded": "embellished", "fringe": "embellished", "embroidered": "embellished",
}

MATERIAL_FAMILIES = ("cotton", "denim", "linen", "wool", "silk", "synthetic", "leather", "knit")

_MATERIAL_ALIASES: dict[str, tuple[str, ...]] = {
    "jersey": ("cotton",), "cotton blend": ("cotton",), "canvas": ("cotton",),
    "corduroy": ("cotton",), "chambray": ("cotton", "denim"), "twill": ("cotton",),
    "poplin": ("cotton",), "oxford": ("cotton",), "pique": ("cotton",), "terry": ("cotton",),
    "flannel": ("cotton", "wool"), "chino": ("cotton",),
    "cashmere": ("wool",), "merino": ("wool",), "tweed": ("wool",),
    "acrylic": ("synthetic", "knit"), "polyester": ("synthetic",), "nylon": ("synthetic",),
    "spandex": ("synthetic",), "elastane": ("synthetic",), "fleece": ("synthetic",),
    "viscose": ("synthetic",), "rayon": ("synthetic",), "chiffon": ("synthetic", "silk"),
    "satin": ("silk", "synthetic"), "mesh": ("synthetic",), "lycra": ("synthetic",),
    "polyamide": ("synthetic",), "rubber": ("synthetic",), "textile": ("synthetic",),
    "synthetic leather": ("leather", "synthetic"), "faux leather": ("leather", "synthetic"),
    "patent leather": ("leather",), "suede": ("leather",), "nubuck": ("leather",),
    "knitted": ("knit",), "knitwear": ("knit",),
}


def _phrases(value: Any) -> list[str]:
    """The whole normalized value first, then each word, so a two-word name wins over one word."""
    text = normalize(str(value or "").replace("_", " ").replace("-", " "))
    return [text, *text.split()] if text else []


def _canonical_colors() -> dict[str, str]:
    names = {normalize(color): color for color in COLORS}
    for color, variants in COLORS.items():
        names.update({normalize(variant): color for variant in variants})
    return names


def normalize_color(value: Any) -> set[str]:
    """Canonical taxonomy colors that a free-text color name can stand for."""
    canonical = _canonical_colors()
    for phrase in _phrases(value):
        if phrase in canonical:
            return {canonical[phrase]}
        if phrase in _COLOR_SHADES:
            return set(_COLOR_SHADES[phrase])
    return set()


def normalize_pattern(value: Any) -> str | None:
    for phrase in _phrases(value):
        if phrase in PATTERN_CLASSES:
            return phrase
        if phrase in _PATTERN_ALIASES:
            return _PATTERN_ALIASES[phrase]
    return None


def normalize_material(value: Any) -> set[str]:
    for phrase in _phrases(value):
        if phrase in MATERIAL_FAMILIES:
            return {phrase}
        if phrase in _MATERIAL_ALIASES:
            return set(_MATERIAL_ALIASES[phrase])
    return set()


def _category(value: Any) -> WardrobeCategory | None:
    try:
        return WardrobeCategory(str(value).strip().lower())
    except ValueError:
        return None


def item_group_of(category: Any, sub_category: Any) -> str | None:
    """Taxonomy group the application itself would assign to this proposal."""
    parsed = _category(category)
    if parsed is None:
        return None
    group, _ = classify(parsed, str(sub_category or ""))
    return str(group.value) if group else None


def garment_type_of(category: Any, sub_category: Any) -> str | None:
    parsed = _category(category)
    if parsed is not None:
        _, garment = classify(parsed, str(sub_category or ""))
        if garment is not None:
            return garment.value
    text = normalize(str(sub_category or "")).replace(" ", "_")
    return text or None


# --- Attribute gold set and scoring ------------------------------------------

class AcceptedField(BaseModel):
    accepted: list[str] = Field(min_length=1)
    provenance: str


class FormalityField(BaseModel):
    value: int = Field(ge=1, le=5)
    provenance: str


class AttributeGoldItem(BaseModel):
    id: str
    file: str
    sha256: str
    source_label: str
    category: AcceptedField
    item_group: AcceptedField
    garment_type: AcceptedField
    primary_color: AcceptedField
    pattern: AcceptedField
    material: AcceptedField
    formality_level: FormalityField
    note: str = ""
    owner_reviewed: bool = False


SCORED_FIELDS = (
    "category", "category_strict", "item_group", "garment_type", "primary_color", "pattern",
    "pattern_solid_vs_patterned", "material", "formality_exact", "formality_within_one",
)


def judge_attributes(gold: AttributeGoldItem, proposal: dict[str, Any]) -> dict[str, Any]:
    """Per-field verdicts for one proposal; each verdict is True, False or None (no usable answer)."""
    raw_category = str(proposal.get("category") or "").strip().lower()
    category = raw_category if raw_category and raw_category != "unknown" else None
    group = item_group_of(category, proposal.get("sub_category"))
    garment = garment_type_of(category, proposal.get("sub_category"))
    colors = normalize_color(proposal.get("primary_color"))
    pattern = normalize_pattern(proposal.get("pattern"))
    materials = normalize_material(proposal.get("material"))
    verdict: dict[str, Any] = {
        "category": None if category is None else category in gold.category.accepted,
        "category_strict": None if category is None else category == gold.category.accepted[0],
        "item_group": None if group is None else group in gold.item_group.accepted,
        "garment_type": None if garment is None else garment in gold.garment_type.accepted,
        "primary_color": None if not colors else bool(colors & set(gold.primary_color.accepted)),
        "pattern": None if pattern is None else pattern in gold.pattern.accepted,
        "pattern_solid_vs_patterned": None if pattern is None
        else (pattern == "solid") == (gold.pattern.accepted[0] == "solid"),
        "material": None if not materials else bool(materials & set(gold.material.accepted)),
    }
    try:
        level: int | None = int(proposal.get("formality_level"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        level = None
    if level is not None and 1 <= level <= 5:
        error = level - gold.formality_level.value
        verdict.update(formality_exact=error == 0, formality_within_one=abs(error) <= 1,
                       formality_error=error)
    else:
        verdict.update(formality_exact=None, formality_within_one=None, formality_error=None)
    verdict["normalized"] = dict(
        category=category, item_group=group, garment_type=garment, primary_color=sorted(colors),
        pattern=pattern, material=sorted(materials), formality_level=level)
    return verdict


def _rate(values: list[bool | None], total: int) -> dict[str, Any]:
    answered = [value for value in values if value is not None]
    correct = sum(1 for value in answered if value)
    return {"correct": correct, "answered": len(answered), "total": total,
            "accuracy": round(correct / total, 4) if total else None,
            "accuracy_when_answered": round(correct / len(answered), 4) if answered else None}


def score_attribute_run(
    gold_items: list[AttributeGoldItem], verdicts: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    """Aggregate verdicts. A missing verdict or field counts as wrong in `accuracy`."""
    total = len(gold_items)
    rows = [verdicts.get(item.id) for item in gold_items]

    def column(key: str) -> list[bool | None]:
        return [row.get(key) if row else None for row in rows]

    metrics: dict[str, Any] = {key: _rate(column(key), total) for key in SCORED_FIELDS}
    errors = [row["formality_error"] for row in rows if row and row.get("formality_error") is not None]
    metrics["formality_mae"] = round(sum(abs(e) for e in errors) / len(errors), 4) if errors else None
    metrics["formality_mean_signed_error"] = round(sum(errors) / len(errors), 4) if errors else None

    confusion: Counter[tuple[str, str]] = Counter()
    per_class: dict[str, dict[str, int]] = {}
    for item, row in zip(gold_items, rows):
        expected = item.category.accepted[0]
        predicted = (row or {}).get("normalized", {}).get("category") or "no_answer"
        confusion[(expected, predicted)] += 1
        bucket = per_class.setdefault(expected, {"total": 0, "correct": 0})
        bucket["total"] += 1
        bucket["correct"] += int(bool(row and row.get("category")))
    metrics["category_confusion"] = [
        {"expected": e, "predicted": p, "count": n} for (e, p), n in sorted(confusion.items())]
    metrics["category_per_class"] = {
        key: {**value, "recall": round(value["correct"] / value["total"], 4)}
        for key, value in sorted(per_class.items())}
    return metrics


def latency_summary(seconds: list[float]) -> dict[str, float | int | None]:
    if not seconds:
        return {"count": 0, "median": None, "p90": None, "max": None}
    ordered = sorted(seconds)
    p90 = ordered[min(len(ordered) - 1, max(0, round(0.9 * len(ordered)) - 1))]
    return {"count": len(ordered), "median": round(median(ordered), 3),
            "p90": round(p90, 3), "max": round(ordered[-1], 3)}
