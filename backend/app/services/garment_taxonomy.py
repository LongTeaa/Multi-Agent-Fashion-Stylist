"""Shared display taxonomy and deterministic, accent-insensitive inventory search.

Composition roles remain unchanged. Unknown subtypes are never guessed into a
specific group; they remain searchable by their original metadata.
"""
from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from functools import lru_cache

from pydantic import BaseModel

from app.models.entities import WardrobeCategory, WardrobeItem


class ItemGroup(StrEnum):
    TOP = "top"
    PANTS = "pants"
    SKIRT = "skirt"
    DRESS = "dress"
    SHOES = "shoes"
    SANDALS = "sandals"
    OUTERWEAR = "outerwear"
    ACCESSORY = "accessory"


class GarmentType(BaseModel):
    value: str
    label: str
    aliases: tuple[str, ...] = ()


class GarmentGroup(BaseModel):
    value: ItemGroup
    label: str
    category: WardrobeCategory
    aliases: tuple[str, ...] = ()
    types: tuple[GarmentType, ...]


class GarmentTaxonomy(BaseModel):
    groups: tuple[GarmentGroup, ...]


def normalize(value: str) -> str:
    folded = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    return " ".join(re.findall(r"[a-z0-9]+", "".join(
        char for char in folded if not unicodedata.combining(char)
    )))


def _type(value: str, label: str, *aliases: str) -> GarmentType:
    return GarmentType(value=value, label=label, aliases=aliases)


@lru_cache(maxsize=1)
def get_taxonomy() -> GarmentTaxonomy:
    return GarmentTaxonomy(groups=(
        GarmentGroup(value=ItemGroup.TOP, label="Áo", category=WardrobeCategory.TOP,
                     aliases=("top", "tops"), types=(
            _type("t-shirt", "Áo thun", "tshirt", "tee", "t shirt", "áo phông"),
            _type("polo", "Áo Polo", "polo shirt"), _type("shirt", "Áo sơ mi", "button_down_shirt", "dress shirt"),
            _type("blouse", "Áo kiểu"), _type("sweater", "Áo len"),
            _type("tanktop", "Áo ba lỗ", "tank top"))),
        GarmentGroup(value=ItemGroup.PANTS, label="Quần", category=WardrobeCategory.BOTTOM,
                     aliases=("pants", "pant", "quần dài"), types=(
            _type("trousers", "Quần tây", "trouser", "dress pants"),
            _type("jeans", "Quần jeans", "jean", "quần bò"),
            _type("chinos", "Quần Chinos", "chino"),
            _type("shorts", "Quần short", "quần đùi"),
            _type("joggers", "Quần jogger", "jogger"))),
        GarmentGroup(value=ItemGroup.SKIRT, label="Chân váy", category=WardrobeCategory.BOTTOM,
                     aliases=("skirt", "skirts"), types=(
            _type("skirt", "Chân váy"), _type("pleated_skirt", "Chân váy xếp ly"),
            _type("pencil_skirt", "Chân váy bút chì"), _type("a_line_skirt", "Chân váy chữ A"),
            _type("mini_skirt", "Chân váy ngắn"), _type("midi_skirt", "Chân váy midi"))),
        GarmentGroup(value=ItemGroup.DRESS, label="Váy liền", category=WardrobeCategory.DRESS,
                     aliases=("đầm", "dress", "dresses", "váy liền thân"), types=(
            _type("dress", "Váy liền"), _type("casual_dress", "Đầm thường ngày"),
            _type("formal_dress", "Đầm dạ hội"), _type("shirt_dress", "Đầm sơ mi"),
            _type("maxi_dress", "Đầm maxi"), _type("midi_dress", "Đầm midi"))),
        GarmentGroup(value=ItemGroup.SHOES, label="Giày", category=WardrobeCategory.FOOTWEAR,
                     aliases=("shoe", "shoes"), types=(
            _type("sneakers", "Giày sneaker", "sneaker", "giày thể thao"),
            _type("derby", "Giày Derby", "derby shoes"), _type("oxford", "Giày Oxford", "oxford_shoes"),
            _type("loafers", "Giày lười", "loafer"), _type("leather_shoes", "Giày da"),
            _type("boots", "Giày boots", "boot", "bốt"),
            _type("chelsea_boots", "Giày Chelsea boots"),
            _type("heels", "Giày cao gót", "high heels"), _type("flats", "Giày bệt"))),
        GarmentGroup(value=ItemGroup.SANDALS, label="Dép", category=WardrobeCategory.FOOTWEAR,
                     aliases=("sandals", "sandal"), types=(
            _type("sandals", "Dép sandal", "sandal"), _type("slides", "Dép quai ngang"),
            _type("slippers", "Dép đi trong nhà", "slipper"),
            _type("flip_flops", "Dép xỏ ngón", "flip flop"))),
        GarmentGroup(value=ItemGroup.OUTERWEAR, label="Áo khoác", category=WardrobeCategory.OUTERWEAR,
                     aliases=("outerwear",), types=(
            _type("jacket", "Áo khoác jacket"), _type("coat", "Áo măng tô"),
            _type("blazer", "Áo Blazer"), _type("cardigan", "Áo cardigan"),
            _type("hoodie", "Áo Hoodie"), _type("vest", "Áo gile"))),
        GarmentGroup(value=ItemGroup.ACCESSORY, label="Phụ kiện", category=WardrobeCategory.ACCESSORY,
                     aliases=("accessory", "accessories"), types=(
            _type("belt", "Thắt lưng"), _type("watch", "Đồng hồ"),
            _type("bag", "Túi xách"), _type("hat", "Mũ", "nón"),
            _type("glasses", "Kính mắt"))),
    ))


def classify(category: WardrobeCategory, subtype: str) -> tuple[GarmentGroup | None, GarmentType | None]:
    value = normalize(subtype)
    groups = [group for group in get_taxonomy().groups if group.category == category]
    for group in groups:
        for item_type in group.types:
            if value in {normalize(alias) for alias in
                         (item_type.value, item_type.label, *item_type.aliases)}:
                return group, item_type
    for group in groups:
        if value in {normalize(alias) for alias in (group.value, group.label, *group.aliases)}:
            return group, None
    # Single-group roles are unambiguous even for user-defined subtypes.
    return (groups[0], None) if len(groups) == 1 else (None, None)


COLORS = {
    "black": ("đen",), "white": ("trắng",), "blue": ("xanh dương", "xanh biển"),
    "navy blue": ("navy", "xanh navy", "xanh đen"), "green": ("xanh lá", "xanh lá cây"),
    "grey": ("gray", "xám"), "red": ("đỏ",), "brown": ("nâu",),
    "beige": ("be" , "kem"), "yellow": ("vàng",), "pink": ("hồng",),
    "purple": ("tím",), "orange": ("cam",),
}


@lru_cache(maxsize=1)
def _search_aliases() -> dict[tuple[str, ...], tuple[str, str]]:
    aliases: dict[tuple[str, ...], tuple[str, str]] = {}
    for group in get_taxonomy().groups:
        for item_type in group.types:
            for alias in (item_type.value, item_type.label, *item_type.aliases):
                aliases[tuple(normalize(alias).split())] = ("type", item_type.value)
        # Generic families intentionally win over their generic subtype (skirt/dress).
        for alias in (group.value, group.label, *group.aliases):
            aliases[tuple(normalize(alias).split())] = ("group", group.value)
    for color, variants in COLORS.items():
        for alias in (color, *variants):
            aliases[tuple(normalize(alias).split())] = ("color", color)
    aliases[("giay", "dep")] = ("category", "footwear")
    aliases[("vay",)] = ("category", "skirt_or_dress")
    return aliases


def parse_search(query: str) -> list[tuple[str, str]]:
    tokens = normalize(query).split()
    terms: list[tuple[str, str]] = []
    aliases = _search_aliases()
    index = 0
    while index < len(tokens):
        for end in range(len(tokens), index, -1):
            match = aliases.get(tuple(tokens[index:end]))
            if match:
                terms.append(match)
                index = end
                break
        else:
            terms.append(("text", tokens[index]))
            index += 1
    return terms


def matches_search(item: WardrobeItem, terms: list[tuple[str, str]]) -> bool:
    if not terms:
        return False
    group, item_type = classify(item.category, item.sub_category)
    words = set(normalize(" ".join(str(value or "") for value in (
        item.sub_category, item.primary_color, item.secondary_color, item.pattern,
        item.material, item.style, item.fit, *item.free_text_tags,
    ))).split())
    colors = {normalize(value) for value in (item.primary_color, item.secondary_color) if value}
    for kind, value in terms:
        if kind == "group" and (group is None or group.value != value):
            return False
        if kind == "type" and (item_type is None or item_type.value != value):
            return False
        if kind == "category":
            if value == "skirt_or_dress":
                if item.category != WardrobeCategory.DRESS and (group is None or group.value != "skirt"):
                    return False
            elif item.category.value != value:
                return False
        if kind == "color" and not colors.intersection(
            normalize(alias) for alias in (value, *COLORS[value])
        ):
            return False
        if kind == "text" and not any(
            word == value or (len(value) >= 2 and word.startswith(value)) for word in words
        ):
            return False
    return True
