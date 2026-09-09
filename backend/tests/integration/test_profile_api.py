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
