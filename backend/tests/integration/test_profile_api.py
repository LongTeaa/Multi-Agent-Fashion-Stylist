from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.dependencies import get_db_session
from app.main import app
from app.models.entities import UserPreference


def test_profile_onboarding_options_replace_and_user_isolation(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_a, user_b = str(uuid4()), str(uuid4())

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        headers_a = {"X-User-Id": user_a}
        headers_b = {"X-User-Id": user_b}
        options_response = client.get(
            "/api/v1/user/profile/preference-options", headers=headers_a
        )
        assert options_response.status_code == 200
        options = options_response.json()["data"]
        assert options["version"] == 1
        assert options["styles"]["selection_limit"] == 3
        assert "minimalist" in options["styles"]["values"]
        assert options["fit_preferences"]["selection_limit"] == 1

        empty_profile = client.get("/api/v1/user/profile", headers=headers_a)
        assert empty_profile.status_code == 200
        assert empty_profile.json()["data"]["preferences"]["styles"] == []

        payload = {
            "styles": ["minimalist", "smart_casual"],
            "color_palettes": ["neutral"],
            "priorities": ["comfort", "polished"],
            "avoid_colors": ["orange"],
            "avoid_styles": ["streetwear"],
            "fit_preferences": ["regular"],
        }
        updated = client.put(
            "/api/v1/user/profile/preferences", headers=headers_a, json=payload
        )
        assert updated.status_code == 200
        profile = updated.json()["data"]
        assert profile["user_id"] == user_a
        assert profile["preferences"] == payload
        assert profile["feature_weights"]["version"] == 1
        assert profile["feature_weights"]["weights"] == {
            "formality:medium": 0.5,
            "palette:neutral": 1.0,
            "pattern:solid": 0.6,
            "priority:comfort": 1.0,
            "priority:polished": 1.0,
            "style:minimalist": 1.0,
            "style:smart_casual": 1.0,
        }

        profile_b = client.get("/api/v1/user/profile", headers=headers_b)
        assert profile_b.status_code == 200
        assert profile_b.json()["data"]["preferences"]["styles"] == []

        replacement = {**payload, "styles": ["formal"], "priorities": []}
        replaced = client.put(
            "/api/v1/user/profile/preferences", headers=headers_a, json=replacement
        )
        assert replaced.status_code == 200
        assert replaced.json()["data"]["preferences"]["styles"] == ["formal"]
        assert "style:minimalist" not in replaced.json()["data"]["feature_weights"]["weights"]

        with Session(engine) as session:
            assert session.get(UserPreference, user_a).styles == ["formal"]
            assert session.get(UserPreference, user_b).styles == []
    finally:
        app.dependency_overrides.clear()


def test_profile_rejects_invalid_or_excessive_options(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        headers = {"X-User-Id": str(uuid4())}
        invalid_cases = (
            {"styles": ["minimalist", "minimalist"]},
            {"styles": ["casual", "minimalist", "formal", "vintage"]},
            {"styles": ["invented_style"]},
            {"color_palettes": ["sensitive_personality_inference"]},
            {"fit_preferences": ["regular", "relaxed"]},
            {"avoid_colors": ["not-a-canonical-color"]},
        )
        for payload in invalid_cases:
            response = client.put(
                "/api/v1/user/profile/preferences", headers=headers, json=payload
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


def test_profile_update_preserves_learned_weights_when_user_has_ratings(
    migrated_database: tuple[object, object],
) -> None:
    """4.4 Test: Updating profile preferences must rebuild learned rating weights from history instead of wiping them."""
    from app.models.entities import (
        OutfitItem,
        OutfitRecommendation,
        OutfitSlotRole,
        User,
        WardrobeCategory,
        WardrobeItem,
    )

    _, engine = migrated_database
    user_id = str(uuid4())

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    try:
        client = TestClient(app)
        headers = {"X-User-Id": user_id}

        # 1. Setup user with wardrobe items and outfit
        top_id, bot_id, shoes_id, outfit_id = str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4())
        with Session(engine) as session:
            session.add(User(id=user_id))
            session.add(UserPreference(user_id=user_id, styles=["casual"], ratings_count=0))
            session.flush()
            session.add(
                WardrobeItem(
                    id=top_id,
                    user_id=user_id,
                    category=WardrobeCategory.TOP,
                    sub_category="t-shirt",
                    style="casual",
                    fit="regular",
                    primary_color="white",
                    pattern="solid",
                    material="cotton",
                    formality_level=1,
                )
            )
            session.add(
                WardrobeItem(
                    id=bot_id,
                    user_id=user_id,
                    category=WardrobeCategory.BOTTOM,
                    sub_category="jeans",
                    style="casual",
                    fit="regular",
                    primary_color="blue",
                    pattern="solid",
                    material="denim",
                    formality_level=1,
                )
            )
            session.add(
                WardrobeItem(
                    id=shoes_id,
                    user_id=user_id,
                    category=WardrobeCategory.FOOTWEAR,
                    sub_category="sneaker",
                    style="casual",
                    fit="regular",
                    primary_color="white",
                    pattern="solid",
                    material="leather",
                    formality_level=1,
                )
            )
            rec = OutfitRecommendation(
                id=outfit_id,
                user_id=user_id,
                request_id=str(uuid4()),
                user_query="casual outfit",
                context_snapshot={"occasion": "casual"},
                explanation_vi="set do casual",
                fashion_score=0.9,
                personalization_score=0.9,
                composite_score=0.9,
                rank=1,
                rule_version="v1",
            )
            session.add(rec)
            session.flush()
            session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
            session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=bot_id, user_id=user_id, slot_role=OutfitSlotRole.BOTTOM))
            session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=shoes_id, user_id=user_id, slot_role=OutfitSlotRole.FOOTWEAR))
            session.commit()

        # 2. Rate the outfit 5 stars
        rate_res = client.put(
            f"/api/v1/outfits/{outfit_id}/rating",
            headers=headers,
            json={"stars": 5, "source": "manual"},
        )
        assert rate_res.status_code == 200

        # Verify rating updated learned weights
        profile_before = client.get("/api/v1/user/profile", headers=headers).json()["data"]
        assert profile_before["ratings_count"] == 1
        assert "style:casual" in profile_before["feature_weights"]["weights"]
        casual_weight = profile_before["feature_weights"]["weights"]["style:casual"]
        assert casual_weight > 0

        # 3. Update profile preferences with completely different styles
        update_res = client.put(
            "/api/v1/user/profile/preferences",
            headers=headers,
            json={
                "styles": ["formal"],
                "color_palettes": ["neutral"],
                "priorities": ["polished"],
                "avoid_colors": [],
                "avoid_styles": [],
                "fit_preferences": ["slim"],
            },
        )
        assert update_res.status_code == 200
        profile_after = update_res.json()["data"]

        # Invariant 4.4: Profile update does NOT wipe learned rating weights back to onboarding weights
        assert profile_after["ratings_count"] == 1
        assert "style:casual" in profile_after["feature_weights"]["weights"]
        assert profile_after["feature_weights"]["weights"]["style:casual"] == casual_weight
    finally:
        app.dependency_overrides.clear()
