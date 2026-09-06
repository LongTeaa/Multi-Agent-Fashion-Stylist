from __future__ import annotations

import argparse
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Engine
from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import create_database_engine
from app.models import User, WardrobeCategory, WardrobeItem

GOLDEN_USER_ID = str(
    uuid5(NAMESPACE_URL, "https://multi-agent-fashion-stylist.local/fixtures/golden-user")
)


class SeedConflictError(RuntimeError):
    """Raised when fixture identifiers are already owned by different data."""


@dataclass(frozen=True)
class GoldenWardrobeItem:
    id: str
    category: WardrobeCategory
    sub_category: str
    primary_color: str
    pattern: str
    material: str
    style: str
    formality_level: int
    weather_suitability: tuple[str, ...]


@dataclass(frozen=True)
class SeedResult:
    user_created: bool
    items_created: int
    items_updated: int


GOLDEN_WARDROBE = (
    GoldenWardrobeItem(
        id="item-top-01",
        category=WardrobeCategory.TOP,
        sub_category="polo",
        primary_color="white",
        pattern="solid",
        material="cotton",
        style="smart_casual",
        formality_level=3,
        weather_suitability=("warm", "cool"),
    ),
    GoldenWardrobeItem(
        id="item-top-02",
        category=WardrobeCategory.TOP,
        sub_category="button_down_shirt",
        primary_color="black",
        pattern="unknown",
        material="unknown",
        style="smart_casual",
        formality_level=3,
        weather_suitability=("warm", "cool", "cold"),
    ),
    GoldenWardrobeItem(
        id="item-top-03",
        category=WardrobeCategory.TOP,
        sub_category="tee",
        primary_color="grey",
        pattern="graphic",
        material="unknown",
        style="streetwear",
        formality_level=1,
        weather_suitability=("hot", "warm"),
    ),
    GoldenWardrobeItem(
        id="item-bottom-01",
        category=WardrobeCategory.BOTTOM,
        sub_category="chinos",
        primary_color="navy",
        pattern="unknown",
        material="unknown",
        style="smart_casual",
        formality_level=3,
        weather_suitability=("warm", "cool"),
    ),
    GoldenWardrobeItem(
        id="item-bottom-02",
        category=WardrobeCategory.BOTTOM,
        sub_category="trousers",
        primary_color="black",
        pattern="unknown",
        material="wool",
        style="formal",
        formality_level=4,
        weather_suitability=("warm", "cool", "cold"),
    ),
    GoldenWardrobeItem(
        id="item-bottom-03",
        category=WardrobeCategory.BOTTOM,
        sub_category="shorts",
        primary_color="unknown",
        pattern="unknown",
        material="denim",
        style="casual",
        formality_level=1,
        weather_suitability=("hot", "warm"),
    ),
    GoldenWardrobeItem(
        id="item-shoes-01",
        category=WardrobeCategory.FOOTWEAR,
        sub_category="sneakers",
        primary_color="white",
        pattern="unknown",
        material="leather",
        style="minimalist",
        formality_level=2,
        weather_suitability=("hot", "warm", "cool"),
    ),
    GoldenWardrobeItem(
        id="item-shoes-02",
        category=WardrobeCategory.FOOTWEAR,
        sub_category="oxford_shoes",
        primary_color="brown",
        pattern="unknown",
        material="leather",
        style="formal",
        formality_level=4,
        weather_suitability=("warm", "cool", "cold"),
    ),
)


def _apply_spec(item: WardrobeItem, spec: GoldenWardrobeItem) -> None:
    item.user_id = GOLDEN_USER_ID
    item.ingestion_batch_id = None
    item.ingestion_detection_id = None
    item.category = spec.category
    item.sub_category = spec.sub_category
    item.primary_color = spec.primary_color
    item.secondary_color = None
    item.pattern = spec.pattern
    item.material = spec.material
    item.style = spec.style
    item.fit = "unknown"
    item.formality_level = spec.formality_level
    item.season = []
    item.weather_suitability = list(spec.weather_suitability)
    item.functional_flags = []
    item.free_text_tags = []
    item.field_confidence = {}
    item.is_active = True
    item.is_user_confirmed = True
    item.times_worn = 0
    item.last_worn_at = None
    item.deleted_at = None


def _new_item(spec: GoldenWardrobeItem) -> WardrobeItem:
    item = WardrobeItem(
        id=spec.id,
        user_id=GOLDEN_USER_ID,
        category=spec.category,
        sub_category=spec.sub_category,
        primary_color=spec.primary_color,
        pattern=spec.pattern,
        material=spec.material,
        style=spec.style,
        fit="unknown",
        formality_level=spec.formality_level,
    )
    _apply_spec(item, spec)
    return item


def seed_golden_wardrobe(engine: Engine) -> SeedResult:
    """Create or restore the deterministic Phase 1 golden wardrobe fixture."""

    with Session(engine) as session:
        user = session.get(User, GOLDEN_USER_ID)
        user_created = user is None
        if user is None:
            session.add(User(id=GOLDEN_USER_ID))
            session.flush()

        items_created = 0
        items_updated = 0
        for spec in GOLDEN_WARDROBE:
            item = session.get(WardrobeItem, spec.id)
            if item is None:
                session.add(_new_item(spec))
                items_created += 1
                continue
            if item.user_id != GOLDEN_USER_ID:
                raise SeedConflictError(
                    f"Golden wardrobe item {spec.id!r} is owned by another user."
                )
            _apply_spec(item, spec)
            items_updated += 1

        session.commit()
        return SeedResult(
            user_created=user_created,
            items_created=items_created,
            items_updated=items_updated,
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the deterministic Phase 1 golden wardrobe fixture."
    )
    parser.add_argument(
        "--database-url",
        help="Override DATABASE_URL for this command only.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    database_url = args.database_url or get_settings().database_url
    engine = create_database_engine(database_url)
    try:
        result = seed_golden_wardrobe(engine)
    finally:
        engine.dispose()

    print(
        "Golden wardrobe seed complete: "
        f"user_created={result.user_created}, "
        f"items_created={result.items_created}, "
        f"items_updated={result.items_updated}."
    )
    return 0
