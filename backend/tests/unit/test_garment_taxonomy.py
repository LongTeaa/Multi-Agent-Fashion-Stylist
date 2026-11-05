from __future__ import annotations

import pytest

from app.models.entities import WardrobeCategory, WardrobeItem
from app.services.garment_taxonomy import classify, matches_search, parse_search


def item(category: str, subtype: str, color: str = "black") -> WardrobeItem:
    return WardrobeItem(user_id="test", category=WardrobeCategory(category),
                        sub_category=subtype, primary_color=color, pattern="solid",
                        material="cotton", style="casual", fit="regular", formality_level=2)


@pytest.mark.parametrize("query,category,subtype,color,expected", [
    ("giày", "footwear", "sneakers", "white", True),
    ("giay", "footwear", "derby", "black", True),
    ("giày đen", "footwear", "derby", "black", True),
    ("GIAY DEN", "footwear", "sneaker", "đen", True),
    ("giày đen", "footwear", "sneakers", "white", False),
    ("giày", "footwear", "sandals", "black", False),
    ("giày dép", "footwear", "sandals", "black", True),
    ("dép", "footwear", "slides", "black", True),
    ("quần", "bottom", "jeans", "blue", True),
    ("quan", "bottom", "skirt", "blue", False),
    ("chân váy", "bottom", "pleated_skirt", "blue", True),
    ("chan vay", "dress", "dress", "blue", False),
    ("váy liền", "dress", "shirt_dress", "blue", True),
    ("váy", "bottom", "skirt", "blue", True),
    ("váy", "dress", "dress", "blue", True),
    ("quần tây", "bottom", "trousers", "blue", True),
    ("quần tây", "bottom", "jeans", "blue", False),
    ("áo phông trắng", "top", "tshirt", "white", True),
    ("a", "top", "polo", "black", False),
    ("%_", "top", "polo", "black", False),
    ("cust", "bottom", "custom garment", "black", True),
    ("giày", "bottom", "derby", "black", False),
])
def test_search(query: str, category: str, subtype: str, color: str, expected: bool) -> None:
    assert matches_search(item(category, subtype, color), parse_search(query)) is expected


def test_unknown_bottom_is_not_assumed_to_be_pants() -> None:
    assert classify(WardrobeCategory.BOTTOM, "unknown custom item") == (None, None)


def test_aliases_are_category_scoped() -> None:
    group, subtype = classify(WardrobeCategory.TOP, "áo phông")
    assert group is not None and group.value == "top"
    assert subtype is not None and subtype.value == "t-shirt"
    assert classify(WardrobeCategory.BOTTOM, "sneakers") == (None, None)
