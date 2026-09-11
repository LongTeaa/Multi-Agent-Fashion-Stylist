from __future__ import annotations

from typing import Any
from sqlmodel import Session, select

from app.agents.state import (
    GarmentConstraint,
    OutfitItemSlot,
    StylistContext,
    StylistGraphState,
)
from app.core.database import get_engine
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    OutfitSlotRole,
    WardrobeCategory,
    WardrobeItem,
)
from app.schemas.retrieval import WardrobeRetrievalQuery
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
    "sneaker": "sneakers",
    "sneakers": "sneakers",
    "giày da": "leather",
    "giày tây": "oxford",
    "giày lười": "loafers",
    "giày": "shoes",
    "dép": "sandals",
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
    "polo": "Áo polo",
    "shirt": "Áo sơ mi",
    "t-shirt": "Áo thun",
    "chinos": "Quần chinos",
    "jeans": "Quần jean",
    "jean": "Quần jean",
    "trousers": "Quần tây",
    "shorts": "Quần short",
    "sneakers": "Giày sneaker",
    "sneaker": "Giày sneaker",
    "jacket": "Áo khoác",
    "blazer": "Áo blazer",
    "cardigan": "Áo cardigan",
    "hoodie": "Áo hoodie",
    "belt": "Thắt lưng",
    "dress": "Váy đầm",
    "floral dress": "Váy hoa",
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
    sub = item.sub_category.lower().strip()
    color = item.primary_color.lower().strip()

    sub_vi = SUB_CATEGORY_VI_MAP.get(sub)
    if not sub_vi:
        cat_prefixes = {
            WardrobeCategory.TOP: "Áo",
            WardrobeCategory.BOTTOM: "Quần",
            WardrobeCategory.DRESS: "Đầm",
            WardrobeCategory.FOOTWEAR: "Giày",
            WardrobeCategory.OUTERWEAR: "Áo khoác",
            WardrobeCategory.ACCESSORY: "Phụ kiện",
        }
        prefix = cat_prefixes.get(item.category, "")
        sub_vi = f"{prefix} {sub}".strip().title()

    color_vi = COLOR_VI_MAP.get(color, color)
    return f"{sub_vi} {color_vi}".strip()


def _get_primary_media_id(session: Session, item_id: str, user_id: str) -> str | None:
    """Find the highest-priority media asset id for a wardrobe item."""
    links = session.exec(
        select(ItemMedia).where(
            ItemMedia.wardrobe_item_id == item_id,
            ItemMedia.user_id == user_id,
        )
    ).all()
    if not links:
        return None
    priority = {
        ItemMediaRole.PRIMARY: 0,
        ItemMediaRole.THUMBNAIL: 1,
        ItemMediaRole.ALTERNATE: 2,
    }
    return min(links, key=lambda link: priority[link.role]).media_asset_id


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


def _is_constraint_for_category(token: str, category: WardrobeCategory) -> bool:
    """Check whether a constraint belongs to a specific wardrobe category."""
    token_lower = token.lower()
    for cat, kws in CATEGORY_KEYWORD_MAP.items():
        if cat != category and any(kw in token_lower for kw in kws):
            return False
    return True


def retrieve_candidate_pool(
    session: Session,
    user_id: str,
    context: StylistContext,
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
    targeted_must_avoid: dict[WardrobeCategory, list[str]] = {cat: [] for cat in WardrobeCategory}
    general_color_hints: list[str] = []
    required_colors: list[str] = []
    required_garment_colors: list[tuple[WardrobeCategory, str, str]] = []
    compound_exclusions: list[GarmentConstraint] = []

    # Category-only generic tokens that must NOT filter full-text searchable text
    category_only_tokens = {"shoes", "áo", "quần", "giày", "dép", "top", "bottom", "footwear"}

    if context.structured_must_have:
        for c in context.structured_must_have:
            if c.is_category_only:
                # Slot existence is guaranteed by category retrieval; do not filter text
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
                for cat in WardrobeCategory:
                    targeted_must_have[cat].append(norm)

    if context.structured_must_avoid:
        for c in context.structured_must_avoid:
            # Compound exclusion (garment + color e.g. "áo polo đen"): filter post-retrieval
            if (c.category is not None or c.sub_category is not None) and c.color is not None:
                compound_exclusions.append(c)
            elif c.category is not None and c.sub_category is not None:
                targeted_must_avoid[c.category].append(c.sub_category)
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
            else:
                for cat in WardrobeCategory:
                    targeted_must_avoid[cat].append(norm)

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

        # Post-retrieval filtering for compound exclusions
        if compound_exclusions:
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
            matches = filtered_matches

        slots: list[OutfitItemSlot] = []

        for match in matches[:15]:  # Capped at 15 items per slot
            item = match.item
            if match.relaxed_constraints:
                for rel in match.relaxed_constraints:
                    rel_name = "thời tiết" if rel == "weather" else "độ trang trọng"
                    detailed_relaxations.append(f"{rel_name} ({cat.value})")

            media_id = _get_primary_media_id(session, item.id, user_id)
            image_url = f"/api/v1/media/{media_id}" if media_id else None
            name = format_localized_item_name(item)

            slot = OutfitItemSlot(
                item_id=item.id,
                slot_role=OutfitSlotRole(cat.value),
                name=name,
                primary_color=item.primary_color,
                secondary_color=item.secondary_color,
                style=item.style,
                category=cat,
                formality_level=item.formality_level,
                weather_suitability=list(item.weather_suitability),
                pattern=item.pattern,
                material=item.material,
                fit=item.fit,
                functional_flags=list(item.functional_flags),
                image_url=image_url,
            )
            slots.append(slot)
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

    return candidate_pool, errors, warnings


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

    if session is not None:
        pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)
    else:
        with Session(get_engine()) as db_session:
            pool, errors, warnings = retrieve_candidate_pool(db_session, user_id, context)

    return {
        "candidate_pool": pool,
        "errors": existing_errors + errors,
        "warnings": existing_warnings + warnings,
    }
