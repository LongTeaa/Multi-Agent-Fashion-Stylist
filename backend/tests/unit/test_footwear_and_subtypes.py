from __future__ import annotations

import pytest
from app.agents.context_agent import extract_context, SPECIFIC_GARMENT_DEFS
from app.agents.wardrobe_agent import format_localized_item_name, SUB_CATEGORY_VI_MAP
from app.models.entities import WardrobeCategory, WardrobeItem


def _make_item(
    category: WardrobeCategory,
    sub_category: str,
    primary_color: str = "black",
) -> WardrobeItem:
    return WardrobeItem(
        id="test-item-1",
        user_id="test-user-1",
        category=category,
        sub_category=sub_category,
        primary_color=primary_color,
        pattern="solid",
        material="cotton",
        style="casual",
        fit="regular",
        formality_level=3,
        season=[],
        weather_suitability=[],
        functional_flags=[],
        free_text_tags=[],
        field_confidence={},
        is_active=True,
        is_user_confirmed=True,
    )


def test_format_localized_item_name_prevents_clothing_fallback_in_name():
    """LT-08: Shoes with generic sub_category='clothing' should render 'Giày đen', never 'Giày Clothing đen'."""
    item = _make_item(WardrobeCategory.FOOTWEAR, "clothing", "black")
    name = format_localized_item_name(item)
    assert name == "Giày đen"
    assert "clothing" not in name.lower()


def test_format_localized_item_name_generic_tokens():
    """Generic category or unknown tokens should cleanly render category prefix + color."""
    item_footwear = _make_item(WardrobeCategory.FOOTWEAR, "footwear", "white")
    assert format_localized_item_name(item_footwear) == "Giày trắng"

    item_top = _make_item(WardrobeCategory.TOP, "clothing", "white")
    assert format_localized_item_name(item_top) == "Áo trắng"

    item_bottom = _make_item(WardrobeCategory.BOTTOM, "garment", "black")
    assert format_localized_item_name(item_bottom) == "Quần đen"

    item_dress = _make_item(WardrobeCategory.DRESS, "dress", "red")
    assert format_localized_item_name(item_dress) == "Đầm đỏ"


def test_format_localized_item_name_unknown_color():
    """Unknown or empty color should not append 'unknown' or 'none' to name."""
    item = _make_item(WardrobeCategory.FOOTWEAR, "clothing", "unknown")
    assert format_localized_item_name(item) == "Giày"

    item_sneaker = _make_item(WardrobeCategory.FOOTWEAR, "sneakers", "none")
    assert format_localized_item_name(item_sneaker) == "Giày sneaker"


def test_format_localized_item_name_footwear_subtypes():
    """Footwear subtypes like sneakers, loafers, oxford, sandals, slides, boots render natural Vietnamese."""
    assert format_localized_item_name(_make_item(WardrobeCategory.FOOTWEAR, "sneakers", "white")) == "Giày sneaker trắng"
    assert format_localized_item_name(_make_item(WardrobeCategory.FOOTWEAR, "loafers", "brown")) == "Giày lười Loafers nâu"
    assert format_localized_item_name(_make_item(WardrobeCategory.FOOTWEAR, "oxford", "black")) == "Giày tây Oxford đen"
    assert format_localized_item_name(_make_item(WardrobeCategory.FOOTWEAR, "sandals", "black")) == "Sandal đen"
    assert format_localized_item_name(_make_item(WardrobeCategory.FOOTWEAR, "slides", "black")) == "Dép quai ngang đen"
    assert format_localized_item_name(_make_item(WardrobeCategory.FOOTWEAR, "boots", "brown")) == "Giày boots nâu"
    assert format_localized_item_name(_make_item(WardrobeCategory.FOOTWEAR, "heels", "red")) == "Giày cao gót đỏ"
    assert format_localized_item_name(_make_item(WardrobeCategory.FOOTWEAR, "leather_shoes", "black")) == "Giày tây da đen"


def test_format_localized_item_name_skirt_and_bottoms():
    """LT-10: Skirts render 'Chân váy', distinguishing clearly from dresses."""
    assert format_localized_item_name(_make_item(WardrobeCategory.BOTTOM, "skirt", "black")) == "Chân váy đen"
    assert format_localized_item_name(_make_item(WardrobeCategory.BOTTOM, "pleated_skirt", "grey")) == "Chân váy xếp ly xám"
    assert format_localized_item_name(_make_item(WardrobeCategory.BOTTOM, "jeans", "blue")) == "Quần jean xanh dương"
    assert format_localized_item_name(_make_item(WardrobeCategory.BOTTOM, "trousers", "grey")) == "Quần tây xám"


def test_context_agent_distinguishes_skirt_from_dress():
    """LT-10: 'chân váy' must be extracted as BOTTOM (skirt), not as DRESS."""
    ctx_skirt = extract_context("Đi làm ngày mai, tôi muốn mặc chân váy và áo sơ mi")
    assert "chân váy" in ctx_skirt.must_have

    # Ensure SPECIFIC_GARMENT_DEFS maps 'chân váy' to BOTTOM
    matched_bottom = False
    for keywords, category, subcat, _ in SPECIFIC_GARMENT_DEFS:
        if "chân váy" in keywords:
            assert category == WardrobeCategory.BOTTOM
            assert subcat == "skirt"
            matched_bottom = True
            break
    assert matched_bottom, "'chân váy' was not found in SPECIFIC_GARMENT_DEFS for BOTTOM"


def test_context_agent_footwear_subtypes():
    """LT-08: Footwear subtypes like 'giày lười', 'dép quai ngang' are extracted into must_have."""
    ctx = extract_context("Hôm nay đi dạo phố, phải đi giày lười hoặc dép quai ngang")
    assert any("giày lười" in item or "dép quai ngang" in item for item in ctx.must_have)
