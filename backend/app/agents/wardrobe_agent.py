from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from sqlmodel import Session, select

from app.agents.state import (
    AgentTraceEvent,
    ConstraintRelaxationPlan,
    GarmentConstraint,
    MAX_RELAXATION_ROUNDS,
    OutfitItemSlot,
    RelaxationRequest,
    RelaxationStep,
    SlotName,
    StylistContext,
    StylistGraphState,
    normalize_relax_token,
)
from app.core.database import get_engine
from app.models.entities import (
    OutfitSlotRole,
    WardrobeCategory,
    WardrobeItem,
    UserPreference,
)
from app.schemas.retrieval import WardrobeRetrievalQuery
from app.services.item_media import primary_media_ids
from app.services.retrieval_service import retrieve_wardrobe_items

EMPTY_WARDROBE_ERROR = "WARDROBE_EMPTY"
EMPTY_WARDROBE_WARNING = "Tủ đồ của bạn chưa có trang phục. Hãy thêm quần áo trước nhé."

CATEGORY_TO_SLOT: dict[WardrobeCategory, str] = {
    WardrobeCategory.TOP: "tops",
    WardrobeCategory.BOTTOM: "bottoms",
    WardrobeCategory.DRESS: "dresses",
    WardrobeCategory.FOOTWEAR: "footwear",
    WardrobeCategory.OUTERWEAR: "outerwear",
    WardrobeCategory.ACCESSORY: "accessories",
}

SLOT_TO_CATEGORY: dict[str, WardrobeCategory] = {
    v: k for k, v in CATEGORY_TO_SLOT.items()
}

CANONICAL_SLOTS: list[str] = [
    "tops",
    "bottoms",
    "dresses",
    "footwear",
    "outerwear",
    "accessories",
]

SLOT_VI_LABELS: dict[str, str] = {
    "tops": "áo",
    "bottoms": "quần",
    "dresses": "đầm",
    "footwear": "giày dép",
    "outerwear": "áo khoác",
    "accessories": "phụ kiện",
}

# Tier 1: shade expansion within the same requested color family
RELAX_COLOR_FAMILIES: dict[str, list[str]] = {
    "black": ["charcoal", "grey", "gray", "navy"],
    "white": ["cream", "beige"],
    "navy": ["black", "blue", "grey", "gray"],
    "grey": ["black", "navy", "beige"],
    "gray": ["black", "navy", "beige"],
    "beige": ["cream", "white", "khaki", "brown", "tan"],
    "cream": ["white", "beige"],
    "brown": ["tan", "beige", "khaki", "black"],
    "blue": ["navy", "light_blue", "denim_blue"],
}

# Tier 2: equivalent sub-categories strictly within the same WardrobeCategory
# NEVER map across categories (e.g. TOP -> DRESS is forbidden).
SUBCATEGORY_EQUIVALENTS: dict[tuple[WardrobeCategory, str], list[str]] = {
    (WardrobeCategory.BOTTOM, "trousers"): ["chinos", "slacks", "kaki"],
    (WardrobeCategory.BOTTOM, "chinos"): ["trousers", "kaki", "jeans"],
    (WardrobeCategory.BOTTOM, "jeans"): ["chinos", "kaki"],
    (WardrobeCategory.TOP, "shirt"): ["polo", "blouse"],
    (WardrobeCategory.TOP, "polo"): ["shirt", "t-shirt", "t_shirt"],
    (WardrobeCategory.TOP, "t_shirt"): ["polo"],
    (WardrobeCategory.TOP, "t-shirt"): ["polo"],
    (WardrobeCategory.FOOTWEAR, "oxford"): ["loafers", "derby", "boots"],
    (WardrobeCategory.FOOTWEAR, "loafers"): ["oxford", "sneakers"],
    (WardrobeCategory.FOOTWEAR, "sneakers"): ["loafers"],
    (WardrobeCategory.OUTERWEAR, "blazer"): ["jacket", "cardigan", "coat"],
    (WardrobeCategory.OUTERWEAR, "jacket"): ["blazer", "cardigan", "coat"],
    (WardrobeCategory.DRESS, "shirt_dress"): ["casual_dress", "dress", "midi_dress"],
    (WardrobeCategory.DRESS, "formal_dress"): ["midi_dress", "maxi_dress", "dress"],
    (WardrobeCategory.DRESS, "midi_dress"): ["casual_dress", "shirt_dress", "dress"],
    (WardrobeCategory.DRESS, "maxi_dress"): ["midi_dress", "casual_dress", "dress"],
}

# Keywords identifying which category a garment constraint belongs to
CATEGORY_KEYWORD_MAP: dict[WardrobeCategory, list[str]] = {
    WardrobeCategory.TOP: ["polo", "shirt", "t-shirt", "thun", "sơ mi", "áo"],
    WardrobeCategory.BOTTOM: ["chinos", "jean", "jeans", "trousers", "shorts", "quần", "kaki", "bò"],
    WardrobeCategory.DRESS: ["dress", "đầm", "váy"],
    WardrobeCategory.FOOTWEAR: ["sneakers", "sneaker", "giày", "dép", "boots", "sandal", "oxford", "loafers"],
    WardrobeCategory.OUTERWEAR: ["jacket", "blazer", "cardigan", "hoodie", "khoác", "vest", "áo vest"],
    WardrobeCategory.ACCESSORY: ["belt", "thắt lưng", "kính", "túi"],
}

# Bilingual mappings to bridge Vietnamese query constraints with database values
BILINGUAL_CONSTRAINT_MAP: dict[str, str] = {
    # Colors
    "màu đen": "black",
    "đen": "black",
    "màu trắng": "white",
    "trắng": "white",
    "màu đỏ": "red",
    "đỏ": "red",
    "màu xanh": "blue",
    "xanh": "blue",
    "xanh navy": "navy",
    "màu xanh navy": "navy",
    "màu vàng": "yellow",
    "vàng": "yellow",
    "màu xám": "grey",
    "xám": "grey",
    "màu be": "beige",
    "be": "beige",
    "màu nâu": "brown",
    "nâu": "brown",
    "màu hồng": "pink",
    "hồng": "pink",
    "màu cam": "orange",
    "cam": "orange",
    "màu tím": "purple",
    "tím": "purple",
    # Tops
    "áo polo": "polo",
    "polo": "polo",
    "áo sơ mi": "shirt",
    "sơ mi": "shirt",
    "áo thun": "t-shirt",
    "áo phông": "t-shirt",
    "t-shirt": "t-shirt",
    # Bottoms
    "quần jean": "jean",
    "quần jeans": "jean",
    "quần bò": "jean",
    "jean": "jean",
    "jeans": "jean",
    "quần chinos": "chinos",
    "quần kaki": "chinos",
    "quần tây": "chinos",
    "chinos": "chinos",
    "trousers": "chinos",
    "quần short": "shorts",
    "quần soóc": "shorts",
    "shorts": "shorts",
    "chân váy": "skirt",
    "chân váy chữ a": "skirt",
    "chân váy xếp ly": "skirt",
    "chân váy bút chì": "skirt",
    "chân váy ngắn": "skirt",
    "chân váy dài": "skirt",
    "skirt": "skirt",
    "skirts": "skirt",
    # Outerwear
    "áo khoác": "jacket",
    "khoác": "jacket",
    "jacket": "jacket",
    "áo blazer": "blazer",
    "blazer": "blazer",
    "áo vest": "blazer",
    "vest": "blazer",
    "veston": "blazer",
    "suit jacket": "blazer",
    "áo cardigan": "cardigan",
    "cardigan": "cardigan",
    "áo hoodie": "hoodie",
    "hoodie": "hoodie",
    # Dresses
    "váy đầm": "dress",
    "váy": "dress",
    "đầm": "dress",
    "đầm hoa": "dress",
    "váy hoa": "dress",
    "dress": "dress",
    # Footwear
    "giày sneaker": "sneakers",
    "giày thể thao": "sneakers",
    "sneaker": "sneakers",
    "sneakers": "sneakers",
    "giày da": "leather_shoes",
    "giày tây da": "leather_shoes",
    "giày tây": "oxford",
    "giày oxford": "oxford",
    "oxford": "oxford",
    "giày lười": "loafers",
    "giày loafer": "loafers",
    "loafer": "loafers",
    "loafers": "loafers",
    "giày sandal": "sandals",
    "dép sandal": "sandals",
    "sandal": "sandals",
    "sandals": "sandals",
    "dép": "slides",
    "dép quai ngang": "slides",
    "slides": "slides",
    "slide": "slides",
    "giày boots": "boots",
    "giày bốt": "boots",
    "boots": "boots",
    "boot": "boots",
    "bốt": "boots",
    "giày cao gót": "heels",
    "cao gót": "heels",
    "heels": "heels",
    "giày": "shoes",
}

# Localization dictionaries for natural Vietnamese item names
COLOR_VI_MAP: dict[str, str] = {
    "white": "trắng",
    "black": "đen",
    "navy": "xanh navy",
    "blue": "xanh dương",
    "grey": "xám",
    "gray": "xám",
    "brown": "nâu",
    "beige": "be",
    "cream": "kem",
    "red": "đỏ",
    "yellow": "vàng",
    "green": "xanh lá",
    "pink": "hồng",
    "orange": "cam",
    "purple": "tím",
}

SUB_CATEGORY_VI_MAP: dict[str, str] = {
    # Tops
    "polo": "Áo polo",
    "shirt": "Áo sơ mi",
    "t-shirt": "Áo thun",
    "tshirt": "Áo thun",
    "tee": "Áo thun",
    "sweater": "Áo len",
    "knitwear": "Áo dệt kim",
    # Bottoms
    "chinos": "Quần chinos",
    "jeans": "Quần jean",
    "jean": "Quần jean",
    "trousers": "Quần tây",
    "pants": "Quần dài",
    "shorts": "Quần short",
    "khakis": "Quần kaki",
    "joggers": "Quần jogger",
    "sweatpants": "Quần jogger",
    "skirt": "Chân váy",
    "skirts": "Chân váy",
    "mini_skirt": "Chân váy ngắn",
    "midi_skirt": "Chân váy midi",
    "pleated_skirt": "Chân váy xếp ly",
    "pencil_skirt": "Chân váy bút chì",
    "a_line_skirt": "Chân váy chữ A",
    # Footwear
    "sneakers": "Giày sneaker",
    "sneaker": "Giày sneaker",
    "oxford": "Giày tây Oxford",
    "oxford_shoes": "Giày tây Oxford",
    "oxfords": "Giày tây Oxford",
    "loafers": "Giày lười Loafers",
    "loafer": "Giày lười Loafers",
    "leather_shoes": "Giày tây da",
    "sandals": "Sandal",
    "sandal": "Sandal",
    "slides": "Dép quai ngang",
    "slide": "Dép quai ngang",
    "slippers": "Dép",
    "boots": "Giày boots",
    "boot": "Giày boots",
    "chelsea_boots": "Giày Chelsea boots",
    "heels": "Giày cao gót",
    "high_heels": "Giày cao gót",
    "flats": "Giày búp bê",
    # Outerwear
    "jacket": "Áo khoác",
    "coat": "Áo khoác dạ",
    "blazer": "Áo blazer",
    "cardigan": "Áo cardigan",
    "hoodie": "Áo hoodie",
    "vest": "Áo gile vest",
    # Accessories
    "belt": "Thắt lưng",
    "bag": "Túi xách",
    "watch": "Đồng hồ",
    "glasses": "Kính mắt",
    "hat": "Mũ",
    # Dresses
    "dress": "Đầm",
    "floral dress": "Đầm hoa",
    "maxi dress": "Đầm maxi",
    "maxi_dress": "Đầm maxi",
    "midi dress": "Đầm midi",
    "midi_dress": "Đầm midi",
    "slip dress": "Đầm hai dây",
    "slip_dress": "Đầm hai dây",
    "shirt dress": "Đầm sơ mi",
    "shirt_dress": "Đầm sơ mi",
}

GENERIC_SUB_CATEGORY_TOKENS: set[str] = {
    "clothing",
    "garment",
    "apparel",
    "item",
    "unknown",
    "none",
    "",
    "footwear",
    "top",
    "bottom",
    "dress",
    "outerwear",
    "accessory",
    "shoes",
    "clothes",
    "outfit",
    "wear",
}


def normalize_constraint_token(token: str) -> str:
    """Normalize a Vietnamese constraint term into database canonical keyword."""
    t = token.strip().lower()
    if t in BILINGUAL_CONSTRAINT_MAP:
        return BILINGUAL_CONSTRAINT_MAP[t]

    for prefix in ("màu ", "áo ", "quần ", "giày "):
        if t.startswith(prefix):
            cleaned = t[len(prefix):].strip()
            if cleaned in BILINGUAL_CONSTRAINT_MAP:
                return BILINGUAL_CONSTRAINT_MAP[cleaned]
            return cleaned
    return t


def format_localized_item_name(item: WardrobeItem) -> str:
    """Produce a natural, user-friendly Vietnamese name for a wardrobe item."""
    cat_prefixes = {
        WardrobeCategory.TOP: "Áo",
        WardrobeCategory.BOTTOM: "Quần",
        WardrobeCategory.DRESS: "Đầm",
        WardrobeCategory.FOOTWEAR: "Giày",
        WardrobeCategory.OUTERWEAR: "Áo khoác",
        WardrobeCategory.ACCESSORY: "Phụ kiện",
    }
    prefix = cat_prefixes.get(item.category, "Trang phục")

    sub = item.sub_category.lower().strip()
    color = item.primary_color.lower().strip()

    if sub in GENERIC_SUB_CATEGORY_TOKENS or sub == item.category.value:
        sub_vi = prefix
    else:
        from app.services.garment_taxonomy import classify
        _, garment_type = classify(item.category, item.sub_category)
        sub_vi = garment_type.label if garment_type else SUB_CATEGORY_VI_MAP.get(sub)
        if not sub_vi:
            if sub.startswith(prefix.lower()):
                sub_vi = sub.capitalize()
            else:
                sub_vi = f"{prefix} {sub}".strip().title()

    if color in ("", "unknown", "none", "n/a", "chưa xác định"):
        color_vi = ""
    else:
        color_vi = COLOR_VI_MAP.get(color, color)

    return f"{sub_vi} {color_vi}".strip()


def is_wardrobe_empty(session: Session, user_id: str) -> bool:
    """Check whether the user has any active, confirmed, non-deleted wardrobe items."""
    item = session.exec(
        select(WardrobeItem.id)
        .where(
            WardrobeItem.user_id == user_id,
            WardrobeItem.is_active.is_(True),
            WardrobeItem.is_user_confirmed.is_(True),
            WardrobeItem.deleted_at.is_(None),
        )
        .limit(1)
    ).first()
    return item is None


ALL_COLOR_TOKENS = {
    "white", "black", "navy", "blue", "red", "yellow", "green", "pink",
    "brown", "beige", "cream", "grey", "gray", "orange", "purple",
}


def get_category_for_raw_token(token: str) -> WardrobeCategory | None:
    """Identify which wardrobe category a raw constraint token is associated with, using strict precedence."""
    t = token.lower().strip()

    # 1. Outerwear takes precedence over generic 'áo' (e.g. "áo khoác", "áo blazer", "áo cardigan", "áo hoodie", "áo vest")
    if any(kw in t for kw in ["jacket", "blazer", "cardigan", "hoodie", "khoác", "áo khoác", "vest", "áo vest"]):
        return WardrobeCategory.OUTERWEAR

    # 2. Dress takes precedence (e.g. "váy", "đầm", "váy đầm", "dress")
    if any(kw in t for kw in ["dress", "đầm", "váy"]):
        return WardrobeCategory.DRESS

    # 3. Footwear (e.g. "giày", "dép", "sneaker", "sneakers", "boots", "sandal", "sandals")
    if any(kw in t for kw in ["sneakers", "sneaker", "giày", "dép", "boots", "sandal", "oxford", "loafers"]):
        return WardrobeCategory.FOOTWEAR

    # 4. Bottom (e.g. "quần", "chinos", "jean", "jeans", "trousers", "shorts", "kaki", "bò")
    if any(kw in t for kw in ["chinos", "jean", "jeans", "trousers", "shorts", "quần", "kaki", "bò"]):
        return WardrobeCategory.BOTTOM

    # 5. Accessory (e.g. "belt", "thắt lưng", "kính", "túi")
    if any(kw in t for kw in ["belt", "thắt lưng", "kính", "túi"]):
        return WardrobeCategory.ACCESSORY

    # 6. Top (e.g. "áo polo", "áo sơ mi", "áo thun", "polo", "shirt", or generic "áo")
    if any(kw in t for kw in ["polo", "shirt", "t-shirt", "thun", "sơ mi", "áo"]):
        return WardrobeCategory.TOP

    return None


def _extract_avoid_filters(
    context: StylistContext,
) -> tuple[dict[WardrobeCategory, list[str]], list[GarmentConstraint]]:
    """Extract per-category must_avoid tokens and compound exclusions (never relaxed)."""
    targeted_must_avoid: dict[WardrobeCategory, list[str]] = {cat: [] for cat in WardrobeCategory}
    compound_exclusions: list[GarmentConstraint] = []

    if context.structured_must_avoid:
        for c in context.structured_must_avoid:
            if (c.category is not None or c.sub_category is not None) and c.color is not None:
                compound_exclusions.append(c)
            elif c.category is not None and c.sub_category is not None:
                targeted_must_avoid[c.category].append(c.sub_category)
            elif c.category is not None and c.is_category_only:
                compound_exclusions.append(c)
            elif c.color is not None:
                for cat in WardrobeCategory:
                    targeted_must_avoid[cat].append(c.color)
    else:
        for raw_a in context.must_avoid:
            a = raw_a.strip()
            if not a:
                continue
            norm = normalize_constraint_token(a)
            target_cat = get_category_for_raw_token(a)
            if target_cat is not None:
                targeted_must_avoid[target_cat].append(norm)
            elif len(norm.split()) <= 2 and not any(
                kw in norm.lower() for kw in ["thời tiết", "phù hợp", "trang phục", "quần áo"]
            ):
                for cat in WardrobeCategory:
                    targeted_must_avoid[cat].append(norm)

    return targeted_must_avoid, compound_exclusions


def _filter_compound_exclusions(
    matches: list[Any],
    compound_exclusions: list[GarmentConstraint],
) -> list[Any]:
    if not compound_exclusions:
        return matches
    filtered_matches = []
    for match in matches:
        item = match.item
        excluded = False
        for excl in compound_exclusions:
            cat_match = excl.category is None or item.category == excl.category
            sub_match = excl.sub_category is None or (excl.sub_category.lower() in item.sub_category.lower())
            color_match = excl.color is None or (
                item.primary_color.lower() == excl.color.lower()
                or (item.secondary_color and item.secondary_color.lower() == excl.color.lower())
            )
            if cat_match and sub_match and color_match:
                excluded = True
                break
        if not excluded:
            filtered_matches.append(match)
    return filtered_matches


def _build_outfit_item_slot(
    item: WardrobeItem,
    category: WardrobeCategory,
    media_id: str | None = None,
) -> OutfitItemSlot:
    """Build an OutfitItemSlot preserving nullable garment profile attributes."""
    image_url = f"/api/v1/media/{media_id}" if media_id else None
    return OutfitItemSlot(
        item_id=item.id,
        slot_role=OutfitSlotRole(category.value),
        name=format_localized_item_name(item),
        sub_category=item.sub_category,
        primary_color=item.primary_color,
        secondary_color=item.secondary_color,
        style=item.style,
        category=category,
        formality_level=getattr(item, "formality_level", 3),
        comfort_level=getattr(item, "comfort_level", 3),
        silhouette_level=getattr(item, "silhouette_level", None),
        length=getattr(item, "length", None),
        weather_suitability=list(item.weather_suitability),
        pattern=item.pattern,
        material=item.material,
        fit=item.fit,
        functional_flags=list(item.functional_flags),
        image_url=image_url,
        times_worn=item.times_worn or 0,
        last_worn_at=item.last_worn_at.isoformat() if item.last_worn_at else None,
    )


def _apply_saved_avoid_filter(
    session: Session,
    user_id: str,
    candidate_pool: dict[str, list[OutfitItemSlot]],
    context: StylistContext,
    active_relaxations: Sequence[RelaxationStep] | None = None,
) -> dict[str, list[OutfitItemSlot]]:
    preferences = session.get(UserPreference, user_id)
    if preferences and (preferences.avoid_colors or preferences.avoid_styles):
        from app.agents.personalization_agent import check_outfit_avoid_violations
        from app.agents.fashion_agent import constraint_matches_item

        clean = {
            slot: [
                item
                for item in items
                if not check_outfit_avoid_violations([item], preferences.avoid_colors, preferences.avoid_styles)
            ]
            for slot, items in candidate_pool.items()
        }
        complete = clean["footwear"] and (clean["dresses"] or (clean["tops"] and clean["bottoms"]))
        required_available = all(
            any(constraint_matches_item(constraint, item, active_relaxations) for items in clean.values() for item in items)
            for constraint in context.structured_must_have
        )
        if complete and required_available:
            return clean
    return candidate_pool


def retrieve_candidate_pool(
    session: Session,
    user_id: str,
    context: StylistContext,
    active_relaxations: Sequence[RelaxationStep] | None = None,
) -> tuple[dict[str, list[OutfitItemSlot]], list[str], list[str]]:
    """Retrieve active wardrobe items grouped into 6 canonical slots with category-scoped must_have."""
    errors: list[str] = []
    warnings: list[str] = []
    candidate_pool: dict[str, list[OutfitItemSlot]] = {slot: [] for slot in CANONICAL_SLOTS}

    # Empty wardrobe check
    if is_wardrobe_empty(session, user_id):
        errors.append(EMPTY_WARDROBE_ERROR)
        warnings.append(EMPTY_WARDROBE_WARNING)
        return candidate_pool, errors, warnings

    style_hints = list(dict.fromkeys(s.strip() for s in context.style_hints if s.strip()))[:10]

    # Process must_have and must_avoid using structured constraints if available
    targeted_must_have: dict[WardrobeCategory, list[str]] = {cat: [] for cat in WardrobeCategory}
    general_color_hints: list[str] = []
    required_colors: list[str] = []
    required_garment_colors: list[tuple[WardrobeCategory, str, str]] = []

    # Category-only generic tokens that must NOT filter full-text searchable text
    category_only_tokens = {"shoes", "áo", "quần", "giày", "dép", "top", "bottom", "footwear"}

    if context.structured_must_have:
        for c in context.structured_must_have:
            if c.is_category_only:
                # Slot existence is guaranteed by category retrieval; do not filter by category text,
                # but still retain explicit material/color hints (e.g. "đầm đỏ").
                if c.category is not None and c.material is not None:
                    targeted_must_have[c.category].append(c.material)
                if c.color is not None:
                    general_color_hints.append(c.color)
                    required_colors.append(c.color)
                continue
            if c.category is not None:
                if c.sub_category is not None:
                    targeted_must_have[c.category].append(c.sub_category)
                if c.material is not None:
                    targeted_must_have[c.category].append(c.material)
            if c.color is not None:
                general_color_hints.append(c.color)
                if c.category is not None and c.sub_category is not None:
                    required_garment_colors.append((c.category, c.sub_category, c.color))
                else:
                    required_colors.append(c.color)
    else:
        for raw_m in context.must_have:
            m = raw_m.strip()
            if not m:
                continue
            norm = normalize_constraint_token(m)
            if norm in category_only_tokens or m.lower() in category_only_tokens:
                continue
            target_cat = get_category_for_raw_token(m)
            if target_cat is not None:
                targeted_must_have[target_cat].append(norm)
            elif norm in ALL_COLOR_TOKENS:
                general_color_hints.append(norm)
                required_colors.append(norm)
            else:
                if len(norm.split()) <= 2 and not any(kw in norm.lower() for kw in ["thời tiết", "phù hợp", "trang phục", "quần áo"]):
                    for cat in WardrobeCategory:
                        targeted_must_have[cat].append(norm)

    targeted_must_avoid, compound_exclusions = _extract_avoid_filters(context)

    formality_min = context.target_formality_range[0] if len(context.target_formality_range) >= 1 else 1
    formality_max = context.target_formality_range[1] if len(context.target_formality_range) >= 2 else 5

    text_query = " ".join(context.vibe_keywords).strip() if context.vibe_keywords else None
    enable_full_text = bool(text_query)

    detailed_relaxations: list[str] = []

    # Retrieve per category with category-scoped must_have
    for cat in [
        WardrobeCategory.TOP,
        WardrobeCategory.BOTTOM,
        WardrobeCategory.DRESS,
        WardrobeCategory.FOOTWEAR,
        WardrobeCategory.OUTERWEAR,
        WardrobeCategory.ACCESSORY,
    ]:
        cat_must_have = list(dict.fromkeys(targeted_must_have[cat]))[:10]
        cat_must_avoid = list(dict.fromkeys(targeted_must_avoid[cat]))[:10]
        cat_color_hints = list(dict.fromkeys(general_color_hints))[:10]

        cat_query = WardrobeRetrievalQuery(
            categories=[cat],
            color_hints=cat_color_hints,
            style_hints=style_hints,
            weather_condition=context.weather_condition,
            formality_min=formality_min,
            formality_max=formality_max,
            must_have=cat_must_have,
            must_avoid=cat_must_avoid,
            text_query=text_query,
            enable_full_text=enable_full_text,
            limit_per_category=15,
        )

        cat_results = retrieve_wardrobe_items(
            session=session,
            user_id=user_id,
            query=cat_query,
        )

        slot_name = CATEGORY_TO_SLOT[cat]
        matches = cat_results.get(cat, [])
        if cat in {WardrobeCategory.OUTERWEAR, WardrobeCategory.ACCESSORY} and not any(
            constraint.category == cat for constraint in context.structured_must_have
        ):
            # Optional layers should not become available by relaxing the weather:
            # omitting an unsuitable winter coat is better than adding it for a tag.
            matches = [match for match in matches if "weather" not in match.relaxed_constraints]

        # Post-retrieval filtering for compound exclusions
        matches = _filter_compound_exclusions(matches, compound_exclusions)

        slots: list[OutfitItemSlot] = []
        capped_matches = matches[:15]  # Capped at 15 items per slot
        media_ids = primary_media_ids(session, user_id, [match.item.id for match in capped_matches])

        for match in capped_matches:
            item = match.item
            if match.relaxed_constraints:
                for rel in match.relaxed_constraints:
                    rel_name = "thời tiết" if rel == "weather" else "độ trang trọng"
                    detailed_relaxations.append(f"{rel_name} ({cat.value})")
            slots.append(_build_outfit_item_slot(item, cat, media_id=media_ids.get(item.id)))
        candidate_pool[slot_name] = slots

    # Pre-flight Outfit Feasibility Check
    has_branch_1 = (
        len(candidate_pool["tops"]) > 0
        and len(candidate_pool["bottoms"]) > 0
        and len(candidate_pool["footwear"]) > 0
    )
    has_branch_2 = (
        len(candidate_pool["dresses"]) > 0
        and len(candidate_pool["footwear"]) > 0
    )
    if not (has_branch_1 or has_branch_2):
        missing = []
        if len(candidate_pool["footwear"]) == 0:
            missing.append("giày/dép")
        if len(candidate_pool["tops"]) == 0 and len(candidate_pool["dresses"]) == 0:
            missing.append("áo hoặc đầm")
        if len(candidate_pool["bottoms"]) == 0 and len(candidate_pool["dresses"]) == 0:
            missing.append("quần hoặc đầm")
        warnings.append(
            f"Tủ đồ chưa có đủ trang phục cho các danh mục bắt buộc để tạo thành bộ đồ hoàn chỉnh (thiếu: {', '.join(missing)})."
        )

    # Must-have Color Warning Verification
    if required_colors:
        all_pool_items = [slot for slots in candidate_pool.values() for slot in slots]
        for col in list(dict.fromkeys(required_colors)):
            has_matching_color = any(
                item.primary_color.lower() == col.lower()
                or (item.secondary_color and item.secondary_color.lower() == col.lower())
                for item in all_pool_items
            )
            if not has_matching_color:
                col_vi = COLOR_VI_MAP.get(col, col)
                warnings.append(
                    f"Tủ đồ không có trang phục màu {col_vi} phù hợp với yêu cầu bắt buộc."
                )

    if required_garment_colors:
        for cat, sub_cat, col in required_garment_colors:
            slot_name = CATEGORY_TO_SLOT[cat]
            slot_items = candidate_pool[slot_name]
            if not any(
                col.lower() == item.primary_color.lower()
                or (item.secondary_color and col.lower() == item.secondary_color.lower())
                for item in slot_items
            ):
                col_vi = COLOR_VI_MAP.get(col, col)
                sub_vi = SUB_CATEGORY_VI_MAP.get(sub_cat, sub_cat)
                warnings.append(
                    f"Tủ đồ không có {sub_vi} màu {col_vi} phù hợp với yêu cầu."
                )

    if detailed_relaxations:
        unique_relaxations = list(dict.fromkeys(detailed_relaxations))
        warnings.append(
            f"Đã nới lỏng điều kiện tìm kiếm: {', '.join(unique_relaxations)}."
        )

    # Apply saved exclusions before the bounded combinatorial search. Retain the
    # original pool only when no complete clean branch can satisfy required items.
    candidate_pool = _apply_saved_avoid_filter(
        session, user_id, candidate_pool, context, active_relaxations=active_relaxations
    )
    return candidate_pool, errors, warnings


def _merge_slot_items(
    existing: list[OutfitItemSlot],
    new_slots: list[OutfitItemSlot],
    limit: int = 15,
) -> list[OutfitItemSlot]:
    """Merge newly relaxed items ahead of existing candidates so a full slot never starves relaxation."""
    existing_ids = {item.item_id for item in existing}
    seen_ids: set[str] = set()
    prioritized: list[OutfitItemSlot] = []
    for slot in new_slots:
        if slot.item_id not in existing_ids and slot.item_id not in seen_ids:
            seen_ids.add(slot.item_id)
            prioritized.append(slot)
    for slot in existing:
        if slot.item_id not in seen_ids:
            seen_ids.add(slot.item_id)
            prioritized.append(slot)
    return prioritized[: max(limit, len(existing))]


def apply_relaxation_request(
    session: Session,
    user_id: str,
    context: StylistContext,
    current_pool: dict[str, list[OutfitItemSlot]],
    request: RelaxationRequest,
    relaxation_round: int,
    active_relaxations: Sequence[RelaxationStep] | None = None,
) -> tuple[dict[str, list[OutfitItemSlot]], list[RelaxationStep], int, list[str]]:
    """Execute one targeted relaxation round preserving category boundaries and must_avoid invariants."""
    next_round = relaxation_round + 1
    updated_pool: dict[str, list[OutfitItemSlot]] = {
        slot: list(current_pool.get(slot, [])) for slot in CANONICAL_SLOTS
    }
    updated_steps: list[RelaxationStep] = list(active_relaxations or ())
    applied_keys = {
        (step.category, step.action, normalize_relax_token(step.original_value))
        for step in updated_steps
    }
    new_warnings: list[str] = []

    targeted_must_avoid, compound_exclusions = _extract_avoid_filters(context)
    style_hints = list(dict.fromkeys(s.strip() for s in context.style_hints if s.strip()))[:10]
    formality_min = context.target_formality_range[0] if len(context.target_formality_range) >= 1 else 1
    formality_max = context.target_formality_range[1] if len(context.target_formality_range) >= 2 else 5
    text_query = " ".join(context.vibe_keywords).strip() if context.vibe_keywords else None
    enable_full_text = bool(text_query)

    def _query_category(
        cat: WardrobeCategory,
        must_have_tokens: list[str],
        color_hints: list[str],
    ) -> list[OutfitItemSlot]:
        cat_query = WardrobeRetrievalQuery(
            categories=[cat],
            color_hints=list(dict.fromkeys(color_hints))[:10],
            style_hints=style_hints,
            weather_condition=context.weather_condition,
            formality_min=formality_min,
            formality_max=formality_max,
            must_have=list(dict.fromkeys(must_have_tokens))[:10],
            must_avoid=list(dict.fromkeys(targeted_must_avoid[cat]))[:10],
            text_query=text_query,
            enable_full_text=enable_full_text,
            limit_per_category=15,
        )
        matches = retrieve_wardrobe_items(session=session, user_id=user_id, query=cat_query).get(cat, [])
        matches = _filter_compound_exclusions(matches, compound_exclusions)
        capped_matches = matches[:15]
        media_ids = primary_media_ids(session, user_id, [m.item.id for m in capped_matches])
        return [_build_outfit_item_slot(m.item, cat, media_id=media_ids.get(m.item.id)) for m in capped_matches]

    plans: list[ConstraintRelaxationPlan] = list(request.constraint_plans)
    if not plans:
        plans = [
            ConstraintRelaxationPlan(
                slot=CATEGORY_TO_SLOT[c.category],  # type: ignore[arg-type]
                constraint=c,
                allowed_actions=list(request.allowed_actions),
            )
            for c in request.blocked_constraints
            if c.category is not None
        ]

    for plan in plans:
        c = plan.constraint
        if c.category is None:
            continue
        slot_name: SlotName = plan.slot
        plan_actions = set(plan.allowed_actions)
        constraint_relax_material = "material_relax" in plan_actions

        if "color_family" in plan_actions and c.color is not None:
            norm_col = normalize_relax_token(c.color)
            relaxed_cols = RELAX_COLOR_FAMILIES.get(norm_col)
            key = (c.category, "color_family", norm_col)
            if relaxed_cols and key not in applied_keys:
                col_vi = COLOR_VI_MAP.get(norm_col, c.color)
                reason = f"Linh hoạt mở rộng màu '{col_vi}' sang các sắc độ cùng nhóm."
                step = RelaxationStep(
                    round=next_round,
                    slot=slot_name,
                    action="color_family",
                    category=c.category,
                    original_value=c.color,
                    relaxed_values=list(relaxed_cols),
                    reason_vi=reason,
                )
                updated_steps.append(step)
                applied_keys.add(key)
                new_warnings.append(reason)
                mh: list[str] = []
                if c.sub_category is not None:
                    mh.append(c.sub_category)
                if c.material is not None and not constraint_relax_material:
                    mh.append(c.material)
                new_slots = _query_category(c.category, mh, [c.color, *relaxed_cols])
                updated_pool[slot_name] = _merge_slot_items(updated_pool[slot_name], new_slots)

        if "material_relax" in plan_actions and c.material is not None:
            norm_mat = normalize_relax_token(c.material)
            key = (c.category, "material_relax", norm_mat)
            if key not in applied_keys:
                reason = f"Linh hoạt bỏ ràng buộc chất liệu '{c.material}' trong nhóm {c.category.value}."
                step = RelaxationStep(
                    round=next_round,
                    slot=slot_name,
                    action="material_relax",
                    category=c.category,
                    original_value=c.material,
                    relaxed_values=[],
                    reason_vi=reason,
                )
                updated_steps.append(step)
                applied_keys.add(key)
                new_warnings.append(reason)
                mh = [c.sub_category] if c.sub_category is not None else []
                hints = [c.color] if c.color is not None else []
                new_slots = _query_category(c.category, mh, hints)
                updated_pool[slot_name] = _merge_slot_items(updated_pool[slot_name], new_slots)

        if "subcategory_equivalent" in plan_actions and c.sub_category is not None:
            norm_sub = normalize_relax_token(c.sub_category)
            equiv_subs = SUBCATEGORY_EQUIVALENTS.get((c.category, norm_sub)) or SUBCATEGORY_EQUIVALENTS.get(
                (c.category, c.sub_category.strip().lower())
            )
            key = (c.category, "subcategory_equivalent", norm_sub)
            if equiv_subs and key not in applied_keys:
                sub_vi = SUB_CATEGORY_VI_MAP.get(c.sub_category.lower(), c.sub_category)
                reason = f"Linh hoạt mở rộng kiểu '{sub_vi}' sang kiểu tương đương trong cùng danh mục."
                step = RelaxationStep(
                    round=next_round,
                    slot=slot_name,
                    action="subcategory_equivalent",
                    category=c.category,
                    original_value=c.sub_category,
                    relaxed_values=list(equiv_subs),
                    reason_vi=reason,
                )
                updated_steps.append(step)
                applied_keys.add(key)
                new_warnings.append(reason)
                hints = [c.color] if c.color is not None else []
                for eq_sub in equiv_subs:
                    mh = [eq_sub]
                    if c.material is not None and not constraint_relax_material:
                        mh.append(c.material)
                    new_slots = _query_category(c.category, mh, hints)
                    updated_pool[slot_name] = _merge_slot_items(updated_pool[slot_name], new_slots)

    updated_pool = _apply_saved_avoid_filter(
        session, user_id, updated_pool, context, active_relaxations=updated_steps
    )
    return updated_pool, updated_steps, next_round, new_warnings


def wardrobe_agent_node(
    state: StylistGraphState,
    session: Session | None = None,
) -> dict[str, Any]:
    """LangGraph node execution function for the Wardrobe Agent."""
    user_id = state.get("user_id", "")
    context = state.get("context")

    candidate_pool: dict[str, list[OutfitItemSlot]] = {slot: [] for slot in CANONICAL_SLOTS}

    if context is None:
        return {
            "errors": list(state.get("errors", [])) + ["MISSING_CONTEXT"],
            "candidate_pool": candidate_pool,
        }

    # If clarification is needed, skip wardrobe retrieval
    if context.needs_clarification:
        return {
            "candidate_pool": candidate_pool,
        }

    existing_errors = list(state.get("errors", []))
    existing_warnings = list(state.get("warnings", []))
    existing_trace = list(state.get("agent_trace", []))
    relaxation_request = state.get("relaxation_request")
    relaxation_round = int(state.get("relaxation_round", 0))
    active_relaxations = list(state.get("active_relaxations", []))

    if relaxation_request is not None:
        current_pool = state.get("candidate_pool", candidate_pool)
        if session is not None:
            pool, updated_steps, next_round, relax_warnings = apply_relaxation_request(
                session, user_id, context, current_pool, relaxation_request, relaxation_round, active_relaxations
            )
        else:
            with Session(get_engine()) as db_session:
                pool, updated_steps, next_round, relax_warnings = apply_relaxation_request(
                    db_session, user_id, context, current_pool, relaxation_request, relaxation_round, active_relaxations
                )

        slot_labels = ", ".join(
            SLOT_VI_LABELS.get(slot, slot) for slot in relaxation_request.bottleneck_slots
        )
        trace_event = AgentTraceEvent(
            round=next_round,
            sender="wardrobe",
            receiver="fashion",
            event_type="RELAXATION_APPLIED",
            summary_vi=f"Đã nới lỏng có kiểm soát vòng {next_round} cho nhóm {slot_labels}.",
        )
        updated_warnings = list(dict.fromkeys(existing_warnings + relax_warnings))
        return {
            "candidate_pool": pool,
            "relaxation_round": next_round,
            "relaxation_request": None,
            "active_relaxations": updated_steps,
            "warnings": updated_warnings,
            "base_warnings": updated_warnings,
            "agent_trace": existing_trace + [trace_event],
        }

    if session is not None:
        pool, errors, warnings = retrieve_candidate_pool(
            session, user_id, context, active_relaxations=active_relaxations
        )
    else:
        with Session(get_engine()) as db_session:
            pool, errors, warnings = retrieve_candidate_pool(
                db_session, user_id, context, active_relaxations=active_relaxations
            )

    trace_event = AgentTraceEvent(
        round=relaxation_round,
        sender="wardrobe",
        receiver="end" if errors else "fashion",
        event_type="WARDROBE_EMPTY" if errors else "CANDIDATE_POOL_BUILT",
        summary_vi="Tủ đồ trống." if errors else "Đã truy vấn kho ứng viên gồm 6 nhóm trang phục.",
    )
    updated_warnings = list(dict.fromkeys(existing_warnings + warnings))
    return {
        "candidate_pool": pool,
        "errors": existing_errors + errors,
        "warnings": updated_warnings,
        "base_warnings": updated_warnings,
        "relaxation_request": None,
        "agent_trace": existing_trace + [trace_event],
    }
