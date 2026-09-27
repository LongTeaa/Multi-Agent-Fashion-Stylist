from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.dependencies import (
    get_context_llm_provider,
    get_db_session,
    get_utc_clock,
    get_weather_provider,
)
from app.main import app
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    User,
    WardrobeCategory,
    WardrobeItem,
    WardrobeRetrievalDocument,
)


def _seed_contrastive_demo_wardrobe(engine: object, user_id: str) -> dict[str, str]:
    """Seed a specialized wardrobe tailored for contrastive defense demonstration:
    
    Contains:
    1. Formal Suit Top: Blazer/Suit jacket, wool, formality=5, comfort=2, silhouette=3, length=hip
    2. Formal Trouser: Quần tây đen, wool/polyester, formality=5, comfort=2, silhouette=3, length=long
    3. Formal Leather Oxford: Giày da đen, leather, formality=5, comfort=2, silhouette=3
    4. Casual Cotton T-shirt: Áo thun cotton trắng mát, cotton, formality=2, comfort=5, silhouette=4, length=hip
    5. Casual Linen Shorts: Quần đũi/linen xám mát mẻ, linen, formality=2, comfort=5, silhouette=4, length=short
    6. Casual Minimalist Sneakers: Giày thể thao trắng mềm êm, canvas, formality=2, comfort=5, silhouette=3
    """
    now = datetime.now(timezone.utc)
    items_map: dict[str, str] = {}

    with Session(engine) as session:
        session.add(User(id=user_id, email=f"demo_{user_id[:8]}@example.com"))
        session.commit()

        def _add_complete_item(
            key: str,
            category: WardrobeCategory,
            sub_category: str,
            primary_color: str,
            material: str,
            style: str,
            formality_level: int,
            comfort_level: int,
            silhouette_level: int,
            length: str,
            weather: list[str],
            flags: list[str],
            searchable_text: str,
        ) -> str:
            item_id = str(uuid4())
            media_id = str(uuid4())

            session.add(
                MediaAsset(
                    id=media_id,
                    user_id=user_id,
                    kind=MediaKind.ORIGINAL,
                    bucket="wardrobe-private",
                    object_key=f"demo/{key}.jpg",
                    mime_type="image/jpeg",
                    width=600,
                    height=800,
                    size_bytes=10240,
                    sha256="a" * 64,
                    created_at=now,
                )
            )
            session.add(
                WardrobeItem(
                    id=item_id,
                    user_id=user_id,
                    category=category,
                    sub_category=sub_category,
                    primary_color=primary_color,
                    pattern="solid",
                    material=material,
                    style=style,
                    fit="regular",
                    formality_level=formality_level,
                    comfort_level=comfort_level,
                    silhouette_level=silhouette_level,
                    length=length,
                    weather_suitability=weather,
                    functional_flags=flags,
                    is_active=True,
                    is_user_confirmed=True,
                    times_worn=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()

            session.add(
                ItemMedia(
                    user_id=user_id,
                    wardrobe_item_id=item_id,
                    media_asset_id=media_id,
                    role=ItemMediaRole.PRIMARY,
                    created_at=now,
                )
            )
            session.add(
                WardrobeRetrievalDocument(
                    wardrobe_item_id=item_id,
                    user_id=user_id,
                    searchable_text=searchable_text,
                    metadata_snapshot={
                        "category": category.value,
                        "sub_category": sub_category,
                        "primary_color": primary_color,
                        "material": material,
                        "style": style,
                        "formality_level": formality_level,
                        "comfort_level": comfort_level,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            items_map[key] = item_id
            return item_id

        # 1. Formal Suit Blazer (Top)
        _add_complete_item(
            key="suit_top",
            category=WardrobeCategory.TOP,
            sub_category="blazer",
            primary_color="black",
            material="wool",
            style="formal",
            formality_level=5,
            comfort_level=2,
            silhouette_level=3,
            length="hip",
            weather=["cool", "cold"],
            flags=["work"],
            searchable_text="áo blazer suit đen wool dạ hội trang trọng lịch lãm",
        )

        # 2. Formal Trousers (Bottom)
        _add_complete_item(
            key="trouser",
            category=WardrobeCategory.BOTTOM,
            sub_category="trousers",
            primary_color="black",
            material="wool",
            style="formal",
            formality_level=5,
            comfort_level=2,
            silhouette_level=3,
            length="long",
            weather=["cool", "cold"],
            flags=["work"],
            searchable_text="quần tây âu đen wool trang trọng lịch sự",
        )

        # 3. Formal Leather Oxford (Footwear)
        _add_complete_item(
            key="oxford",
            category=WardrobeCategory.FOOTWEAR,
            sub_category="oxford",
            primary_color="black",
            material="leather",
            style="formal",
            formality_level=5,
            comfort_level=2,
            silhouette_level=3,
            length="hip",
            weather=["cool", "cold", "warm"],
            flags=["work"],
            searchable_text="giày da tây oxford đen da bóng sang trọng",
        )

        # 4. Casual Cotton T-shirt (Top)
        _add_complete_item(
            key="tshirt",
            category=WardrobeCategory.TOP,
            sub_category="t-shirt",
            primary_color="white",
            material="cotton",
            style="casual",
            formality_level=2,
            comfort_level=5,
            silhouette_level=4,
            length="hip",
            weather=["hot", "warm"],
            flags=["movement"],
            searchable_text="áo thun phông trắng cotton mát mẻ thoải mái dạo phố",
        )

        # 5. Casual Linen Shorts (Bottom)
        _add_complete_item(
            key="shorts",
            category=WardrobeCategory.BOTTOM,
            sub_category="shorts",
            primary_color="grey",
            material="linen",
            style="casual",
            formality_level=2,
            comfort_level=5,
            silhouette_level=4,
            length="short",
            weather=["hot", "warm"],
            flags=["movement"],
            searchable_text="quần đũi lửng soóc xám linen thoáng khí mát mẻ",
        )

        # 6. Casual Canvas Sneakers (Footwear)
        _add_complete_item(
            key="sneakers",
            category=WardrobeCategory.FOOTWEAR,
            sub_category="sneakers",
            primary_color="white",
            material="canvas",
            style="casual",
            formality_level=2,
            comfort_level=5,
            silhouette_level=3,
            length="hip",
            weather=["hot", "warm", "cool"],
            flags=["movement", "outdoor"],
            searchable_text="giày thể thao sneaker trắng êm chân dễ vận động",
        )

        session.commit()

    return items_map


def test_contrastive_defense_demonstration_scenarios(
    migrated_database: tuple[object, object],
) -> None:
    """Rigorous end-to-end integration test demonstrating the Advisor's 3-Tier contrastive behavior:
    
    SCENARIO A (Formal Wedding Banquet):
    - User query: "Tối nay tôi đi dự tiệc cưới trang trọng ở khách sạn, cần chỉn chu lịch thiệp"
    - Triggers: weight_profile = "formal" (Formality: 30%, Aesthetic: 25%, Comfort: 15%)
    - Top 1 Outfit: Suit Blazer + Quần tây + Giày da Oxford (formality_level = 5)
    - Stylist explanation: Highlights elegance, formality, and polished appearance.

    SCENARIO B (Hot Weather Comfort Cafe):
    - User query: "Hôm nay trời nắng nóng 35 độ oi bức, tôi đi cà phê dạo phố ưu tiên thoải mái mát mẻ"
    - Triggers: weight_profile = "comfort" (Comfort: 30%, Weather: 25%, Aesthetic: 15%, Formality: 10%)
    - Top 1 Outfit: Áo thun cotton + Quần đũi linen + Giày thể thao (comfort_level = 5)
    - Mathematical Proof: The casual outfit beats the suit outfit due to the weather-comfort dynamic profile,
      even if the suit possesses high formal aesthetic harmony!
    - Stylist explanation: Highlights breathable materials, cooling comfort, and casual ease.
    """
    _, engine = migrated_database
    demo_user_id = str(uuid4())
    items = _seed_contrastive_demo_wardrobe(engine, demo_user_id)

    app.dependency_overrides[get_db_session] = lambda: Session(engine)
    app.dependency_overrides[get_context_llm_provider] = lambda: None
    app.dependency_overrides[get_weather_provider] = lambda: None

    client = TestClient(app)

    # =========================================================================
    # SCENARIO A: FORMAL PROFILE DEMONSTRATION
    # =========================================================================
    res_a = client.post(
        "/api/v1/stylist/chat",
        headers={"X-User-Id": demo_user_id},
        json={"query": "Tối nay tôi đi dự tiệc cưới trang trọng ở khách sạn, cần chỉn chu lịch thiệp"},
    )
    assert res_a.status_code == 200, res_a.text
    data_a = res_a.json()["data"]

    # Verify context extraction
    context_a = data_a["context"]
    assert context_a["occasion"] == "wedding"
    assert context_a["weight_profile"] == "formal"

    # Verify Top 1 outfit is the formal suit combination
    recs_a = data_a["recommendations"]
    assert len(recs_a) >= 1
    top1_a = recs_a[0]
    top1_a_item_ids = {item["item_id"] for item in top1_a["items"]}

    assert items["suit_top"] in top1_a_item_ids
    assert items["trouser"] in top1_a_item_ids
    assert items["oxford"] in top1_a_item_ids

    # Verify professional explanation
    exp_a = top1_a["explanation_vi"].lower()
    assert any(term in exp_a for term in ["trang trọng", "chỉn chu", "lịch thiệp", "thanh lịch"])

    # =========================================================================
    # SCENARIO B: COMFORT & WEATHER PROFILE DEMONSTRATION
    # =========================================================================
    res_b = client.post(
        "/api/v1/stylist/chat",
        headers={"X-User-Id": demo_user_id},
        json={"query": "Hôm nay trời nắng nóng 35 độ oi bức, tôi đi cà phê dạo phố ưu tiên thoải mái mát mẻ"},
    )
    assert res_b.status_code == 200, res_b.text
    data_b = res_b.json()["data"]

    # Verify context extraction
    context_b = data_b["context"]
    assert context_b["weather_condition"] == "hot"
    assert context_b["weight_profile"] == "comfort"

    # Verify Top 1 outfit is the breathable cotton/linen casual combination
    recs_b = data_b["recommendations"]
    assert len(recs_b) >= 1
    top1_b = recs_b[0]
    top1_b_item_ids = {item["item_id"] for item in top1_b["items"]}

    assert items["tshirt"] in top1_b_item_ids
    assert items["shorts"] in top1_b_item_ids
    assert items["sneakers"] in top1_b_item_ids

    # Verify professional explanation
    exp_b = top1_b["explanation_vi"].lower()
    assert any(term in exp_b for term in ["thoáng mát", "thoải mái", "mềm", "mát mẻ", "dễ chịu"])

    # =========================================================================
    # MATHEMATICAL CONTRAST VERIFICATION
    # =========================================================================
    # Under Scenario A: The formal suit outfit achieves high composite rank (Rank 1).
    # Under Scenario B: The casual outfit achieves high composite rank (Rank 1).
    assert top1_a["composite_score"] >= 0.70
    assert top1_b["composite_score"] >= 0.70
