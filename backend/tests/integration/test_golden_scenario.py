from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.dependencies import get_db_session, get_utc_clock
from app.core.seed import (
    GOLDEN_USER_ID,
    GOLDEN_WARDROBE,
    seed_golden_wardrobe,
)
from app.main import app
from app.models.entities import (
    FeedbackSuppressedSession,
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    Rating,
    RatingSource,
    User,
    UserPreference,
    WardrobeCategory,
    WardrobeItem,
    WearLog,
)
from app.services.retrieval_document_service import refresh_retrieval_document


def _golden_fixed_clock() -> datetime:
    # 2026-09-12 12:00:00 UTC == 2026-09-12 19:00:00 ICT (unambiguous evening in Vietnam)
    return datetime(2026, 9, 12, 12, 0, 0, tzinfo=timezone.utc)


def _snapshot_user_b_rec(r: OutfitRecommendation) -> dict[str, Any]:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "request_id": r.request_id,
        "user_query": r.user_query,
        "context_snapshot": r.context_snapshot,
        "explanation_vi": r.explanation_vi,
        "fashion_score": r.fashion_score,
        "personalization_score": r.personalization_score,
        "composite_score": r.composite_score,
        "rank": r.rank,
        "is_bookmarked": r.is_bookmarked,
        "rule_version": r.rule_version,
    }


def _snapshot_user_b_outfit_item(i: OutfitItem) -> dict[str, Any]:
    return {
        "outfit_id": i.outfit_id,
        "wardrobe_item_id": i.wardrobe_item_id,
        "user_id": i.user_id,
        "slot_role": i.slot_role.value if hasattr(i.slot_role, "value") else str(i.slot_role),
    }


def _snapshot_user_b_wardrobe_item(w: WardrobeItem) -> dict[str, Any]:
    return {
        "id": w.id,
        "user_id": w.user_id,
        "category": w.category.value if hasattr(w.category, "value") else str(w.category),
        "sub_category": w.sub_category,
        "primary_color": w.primary_color,
        "secondary_color": w.secondary_color,
        "pattern": w.pattern,
        "material": w.material,
        "style": w.style,
        "fit": w.fit,
        "formality_level": w.formality_level,
        "season": list(w.season or []),
        "weather_suitability": list(w.weather_suitability or []),
        "functional_flags": list(w.functional_flags or []),
        "free_text_tags": list(w.free_text_tags or []),
        "is_active": w.is_active,
        "is_user_confirmed": w.is_user_confirmed,
        "times_worn": w.times_worn,
        "deleted_at": w.deleted_at,
    }


def test_golden_recommendation_scenario(
    migrated_database: tuple[object, object],
) -> None:
    """End-to-end golden scenario test for Phase 4.

    Validates that:
    1. The 8-item golden wardrobe runs through the public POST /api/v1/stylist/chat endpoint.
    2. For 'Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?', White Polo + Navy Chinos + White Sneakers
       (item-top-01, item-bottom-01, item-shoes-01) is returned in the top-3 ranked recommendations.
    3. 100% grounding, validity, and database persistence under GOLDEN_USER_ID are verified.
    4. Non-trivial cross-user isolation is enforced: a second seeded user (User B) with existing
       wardrobe items and recommendations is verified to be completely untouched and absent from response.
    """
    _, engine = migrated_database

    # Seed the canonical Phase 1 8-item golden wardrobe
    seed_result = seed_golden_wardrobe(engine)
    assert seed_result.items_created == 8 or seed_result.items_updated == 8

    # Seed User B with existing wardrobe, recommendation, and items to test cross-user isolation substantively
    user_b_id = f"user_b_control_{uuid4().hex[:8]}"
    user_b_outfit_id = f"rec_b_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_b_id))

        item_b_top = WardrobeItem(
            id="item-b-top",
            user_id=user_b_id,
            category=WardrobeCategory.TOP,
            sub_category="silk_shirt",
            primary_color="purple",
            pattern="solid",
            material="silk",
            style="luxury",
            fit="regular",
            formality_level=4,
            weather_suitability=["cool"],
            free_text_tags=["luxury", "purple"],
            is_user_confirmed=True,
            is_active=True,
        )
        item_b_bot = WardrobeItem(
            id="item-b-bot",
            user_id=user_b_id,
            category=WardrobeCategory.BOTTOM,
            sub_category="velvet_trousers",
            primary_color="gold",
            pattern="solid",
            material="velvet",
            style="luxury",
            fit="regular",
            formality_level=4,
            weather_suitability=["cool"],
            free_text_tags=["luxury", "gold"],
            is_user_confirmed=True,
            is_active=True,
        )
        item_b_shoe = WardrobeItem(
            id="item-b-shoe",
            user_id=user_b_id,
            category=WardrobeCategory.FOOTWEAR,
            sub_category="loafers",
            primary_color="burgundy",
            pattern="solid",
            material="leather",
            style="luxury",
            fit="regular",
            formality_level=4,
            weather_suitability=["cool"],
            free_text_tags=["luxury", "burgundy"],
            is_user_confirmed=True,
            is_active=True,
        )
        session.add_all([item_b_top, item_b_bot, item_b_shoe])
        session.flush()
        refresh_retrieval_document(session, item_b_top)
        refresh_retrieval_document(session, item_b_bot)
        refresh_retrieval_document(session, item_b_shoe)

        rec_b = OutfitRecommendation(
            id=user_b_outfit_id,
            user_id=user_b_id,
            request_id="req-user-b-existing",
            user_query="Đi tiệc sang trọng",
            context_snapshot={"occasion": "party"},
            explanation_vi="Set đồ tiệc sang trọng của User B.",
            fashion_score=0.95,
            personalization_score=0.95,
            composite_score=0.95,
            rank=1,
            rule_version="1.0.0",
        )
        session.add(rec_b)
        session.flush()

        session.add(OutfitItem(outfit_id=user_b_outfit_id, wardrobe_item_id="item-b-top", user_id=user_b_id, slot_role=OutfitSlotRole.TOP))
        session.add(OutfitItem(outfit_id=user_b_outfit_id, wardrobe_item_id="item-b-bot", user_id=user_b_id, slot_role=OutfitSlotRole.BOTTOM))
        session.add(OutfitItem(outfit_id=user_b_outfit_id, wardrobe_item_id="item-b-shoe", user_id=user_b_id, slot_role=OutfitSlotRole.FOOTWEAR))
        session.commit()

    # Snapshot User B's state using detached primitive structures before Golden User request
    with Session(engine) as session:
        b_recs_raw = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_b_id)).all()
        b_items_raw = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_b_id)).all()
        b_wardrobe_raw = session.exec(select(WardrobeItem).where(WardrobeItem.user_id == user_b_id)).all()

        b_recs_before = [_snapshot_user_b_rec(r) for r in b_recs_raw]
        b_items_before = sorted(
            [_snapshot_user_b_outfit_item(i) for i in b_items_raw],
            key=lambda x: (x["outfit_id"], x["wardrobe_item_id"]),
        )
        b_wardrobe_before = sorted(
            [_snapshot_user_b_wardrobe_item(w) for w in b_wardrobe_raw],
            key=lambda x: x["id"],
        )

        assert len(b_recs_before) == 1
        assert len(b_items_before) == 3
        assert len(b_wardrobe_before) == 3

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _golden_fixed_clock

    try:
        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": GOLDEN_USER_ID},
            json={
                "query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?",
                "location": None,
            },
        )

        # --------------------------------------------------------------------
        # 1. HTTP Status and Contract Envelope
        # --------------------------------------------------------------------
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        body = res.json()
        assert body["success"] is True
        data = body["data"]

        assert isinstance(data["request_id"], str) and len(data["request_id"]) > 0
        assert data["needs_clarification"] is False
        assert data["clarification_question"] is None
        assert data["feedback_prompt_eligible"] is False
        assert data["feedback_target_outfit_id"] is None

        # Safe serialization: no internal storage keys or raw state exposed
        raw_text = res.text
        assert "object_key" not in raw_text
        assert "user-media" not in raw_text
        assert "bucket" not in raw_text

        # --------------------------------------------------------------------
        # 2. Situational Context Extraction
        # --------------------------------------------------------------------
        ctx = data["context"]
        assert ctx["occasion"] == "cafe"
        assert ctx["time_of_day"] == "evening"
        assert ctx["weather_condition"] == "cool"
        assert ctx["target_formality_range"] == [2, 3]

        # --------------------------------------------------------------------
        # 3. Ranking, Bounded Count & Golden Combination
        # --------------------------------------------------------------------
        recs = data["recommendations"]
        assert 1 <= len(recs) <= 3, f"Expected 1 to 3 recommendations, got {len(recs)}"

        # Strictly consecutive ranks 1..n
        ranks = [r["rank"] for r in recs]
        assert ranks == list(range(1, len(recs) + 1))

        # Composite scores must be monotonically descending and bounded in [0, 1]
        scores = [r["composite_score"] for r in recs]
        for s in scores:
            assert 0.0 <= s <= 1.0
        assert scores == sorted(scores, reverse=True)

        golden_fixture_ids = {item.id for item in GOLDEN_WARDROBE}
        golden_target_ids = {"item-top-01", "item-bottom-01", "item-shoes-01"}

        golden_combo_found = False
        all_returned_outfit_ids: list[str] = []

        for r in recs:
            outfit_id = r["outfit_id"]
            assert outfit_id is not None and len(outfit_id) > 0
            all_returned_outfit_ids.append(outfit_id)

            item_ids = [item["item_id"] for item in r["items"]]
            # Unique items within the outfit
            assert len(item_ids) == len(set(item_ids))

            # 100% Grounding: all items belong to golden fixture
            for item in r["items"]:
                assert item["item_id"] in golden_fixture_ids
                assert item["slot"] in ["top", "bottom", "dress", "footwear", "outerwear", "accessory"]
                if item["image_url"] is not None:
                    assert item["image_url"].startswith("/api/v1/media/")

            # Check if this outfit is the golden combination (White Polo + Navy Chinos + White Sneakers)
            if set(item_ids) == golden_target_ids:
                golden_combo_found = True

        assert golden_combo_found, (
            f"Expected golden combination {golden_target_ids} in top recommendations, "
            f"got: {[[item['item_id'] for item in r['items']] for r in recs]}"
        )

        # --------------------------------------------------------------------
        # 4. Database Persistence and User Ownership
        # --------------------------------------------------------------------
        with Session(engine) as session:
            # All returned outfits must exist in database under GOLDEN_USER_ID
            db_recs = session.exec(
                select(OutfitRecommendation).where(
                    OutfitRecommendation.user_id == GOLDEN_USER_ID,
                    OutfitRecommendation.id.in_(all_returned_outfit_ids),
                )
            ).all()
            assert len(db_recs) == len(recs)
            db_rec_map = {r.id: r for r in db_recs}

            for r in recs:
                rec_id = r["outfit_id"]
                assert rec_id in db_rec_map
                db_rec = db_rec_map[rec_id]
                assert db_rec.user_id == GOLDEN_USER_ID
                assert db_rec.rank == r["rank"]
                assert abs(db_rec.composite_score - r["composite_score"]) < 1e-4

                # Check persisted outfit items
                db_items = session.exec(
                    select(OutfitItem).where(
                        OutfitItem.outfit_id == rec_id,
                        OutfitItem.user_id == GOLDEN_USER_ID,
                    )
                ).all()
                assert len(db_items) == len(r["items"])
                db_item_set = {(i.wardrobe_item_id, i.slot_role.value) for i in db_items}
                resp_item_set = {(i["item_id"], i["slot"]) for i in r["items"]}
                assert db_item_set == resp_item_set

            # Check wardrobe items referenced in recommendations
            all_used_item_ids = {item["item_id"] for r in recs for item in r["items"]}
            db_wardrobe_items = session.exec(
                select(WardrobeItem).where(
                    WardrobeItem.user_id == GOLDEN_USER_ID,
                    WardrobeItem.id.in_(all_used_item_ids),
                )
            ).all()
            assert len(db_wardrobe_items) == len(all_used_item_ids)
            for wi in db_wardrobe_items:
                assert wi.is_active is True
                assert wi.deleted_at is None
                assert wi.user_id == GOLDEN_USER_ID

            # --------------------------------------------------------------------
            # 5. Non-Trivial Cross-User Isolation Assertions
            # --------------------------------------------------------------------
            # User B items and outfits must not leak into Golden User's response
            user_b_item_ids = {"item-b-top", "item-b-bot", "item-b-shoe"}
            assert user_b_item_ids.isdisjoint(all_used_item_ids), (
                f"User B items leaked into recommendation response: {user_b_item_ids.intersection(all_used_item_ids)}"
            )
            assert user_b_outfit_id not in all_returned_outfit_ids

            # User B recommendations in DB must be 100% identically preserved (all business fields)
            b_recs_after_raw = session.exec(
                select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_b_id)
            ).all()
            b_recs_after = [_snapshot_user_b_rec(r) for r in b_recs_after_raw]
            assert b_recs_after == b_recs_before

            # User B outfit items in DB must be 100% identically preserved
            b_items_after_raw = session.exec(
                select(OutfitItem).where(OutfitItem.user_id == user_b_id)
            ).all()
            b_items_after = sorted(
                [_snapshot_user_b_outfit_item(i) for i in b_items_after_raw],
                key=lambda x: (x["outfit_id"], x["wardrobe_item_id"]),
            )
            assert b_items_after == b_items_before

            # User B wardrobe items in DB must be 100% identically preserved (category, colors, active, etc.)
            b_wardrobe_after_raw = session.exec(
                select(WardrobeItem).where(WardrobeItem.user_id == user_b_id)
            ).all()
            b_wardrobe_after = sorted(
                [_snapshot_user_b_wardrobe_item(w) for w in b_wardrobe_after_raw],
                key=lambda x: x["id"],
            )
            assert b_wardrobe_after == b_wardrobe_before

            # All non-golden recommendations and items in DB belong exclusively to User B control
            other_user_recs = session.exec(
                select(OutfitRecommendation).where(OutfitRecommendation.user_id != GOLDEN_USER_ID)
            ).all()
            assert len(other_user_recs) == len(b_recs_before)
            assert all(r.user_id == user_b_id for r in other_user_recs)

            other_user_items = session.exec(
                select(OutfitItem).where(OutfitItem.user_id != GOLDEN_USER_ID)
            ).all()
            assert len(other_user_items) == len(b_items_before)
            assert all(i.user_id == user_b_id for i in other_user_items)

    finally:
        app.dependency_overrides.clear()


def test_golden_phase5_actions_and_learning_lifecycle(
    migrated_database: tuple[object, object],
) -> None:
    """End-to-end golden flow test for Phase 5 actions and learning lifecycle.

    Validates that:
    1. Golden User chats through POST /api/v1/stylist/chat and recommendations are persisted.
    2. Golden User bookmarks outfit #1 via PUT /api/v1/outfits/{id}/bookmark and it persists in DB.
    3. GET /api/v1/outfits/saved returns the bookmarked outfit with complete items and scores.
    4. POST /api/v1/outfits/{id}/worn logs wear count idempotently (second call does not double count).
    5. Non-trivial cross-user isolation: User B receives 404 for detail, bookmark, worn, and rating on Golden User's outfit.
       User B's saved list is completely isolated and returns total=0.
    6. PUT /api/v1/outfits/{id}/rating creates rating, updates stars idempotently without double-counting ratings_count.
    7. Learned feature weights in DB are bounded strictly in [-1.0, 1.0].
    8. Feedback prompt dismissal via POST /api/v1/feedback/prompts/dismiss sets minimum 3-outfit cooldown
       without suppressing the entire session.
    9. Prompted rating via PUT /api/v1/outfits/{id}/rating with source='prompted' records session suppression.
    """
    _, engine = migrated_database

    # Seed the canonical Phase 1 8-item golden wardrobe
    seed_golden_wardrobe(engine)

    # Seed control User B
    user_b_id = f"user_b_p5_{uuid4().hex[:8]}"
    with Session(engine) as session:
        session.add(User(id=user_b_id))
        session.commit()

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _golden_fixed_clock

    try:
        client = TestClient(app)

        # --------------------------------------------------------------------
        # 1. Chat and Recommendation Persistence
        # --------------------------------------------------------------------
        chat_res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": GOLDEN_USER_ID},
            json={
                "query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?",
                "location": None,
            },
        )
        assert chat_res.status_code == 200
        recs = chat_res.json()["data"]["recommendations"]
        assert len(recs) >= 2
        outfit_1_id = recs[0]["outfit_id"]
        outfit_2_id = recs[1]["outfit_id"]

        with Session(engine) as session:
            db_outfit_1 = session.get(OutfitRecommendation, outfit_1_id)
            assert db_outfit_1 is not None
            assert db_outfit_1.user_id == GOLDEN_USER_ID
            assert db_outfit_1.is_bookmarked is False

        # --------------------------------------------------------------------
        # 2. Bookmark Action
        # --------------------------------------------------------------------
        bm_res = client.put(
            f"/api/v1/outfits/{outfit_1_id}/bookmark",
            headers={"X-User-Id": GOLDEN_USER_ID},
            json={"is_bookmarked": True},
        )
        assert bm_res.status_code == 200
        assert bm_res.json()["data"]["is_bookmarked"] is True

        with Session(engine) as session:
            db_outfit_1 = session.get(OutfitRecommendation, outfit_1_id)
            assert db_outfit_1.is_bookmarked is True

        # --------------------------------------------------------------------
        # 3. Saved Outfits List Retrieval
        # --------------------------------------------------------------------
        saved_res = client.get(
            "/api/v1/outfits/saved",
            headers={"X-User-Id": GOLDEN_USER_ID},
        )
        assert saved_res.status_code == 200
        saved_data = saved_res.json()["data"]
        assert saved_data["total"] == 1
        assert saved_data["items"][0]["id"] == outfit_1_id
        assert saved_data["items"][0]["is_bookmarked"] is True
        assert len(saved_data["items"][0]["items"]) == 3

        # --------------------------------------------------------------------
        # 4. Worn Action & Idempotency
        # --------------------------------------------------------------------
        idemp_key = str(uuid4())
        wear_res_1 = client.post(
            f"/api/v1/outfits/{outfit_1_id}/worn",
            headers={"X-User-Id": GOLDEN_USER_ID},
            json={"idempotency_key": idemp_key},
        )
        assert wear_res_1.status_code == 200
        wear_data_1 = wear_res_1.json()["data"]
        assert wear_data_1["times_worn"] == 1
        assert wear_data_1["already_processed"] is False

        # Call again with the exact same idempotency key
        wear_res_2 = client.post(
            f"/api/v1/outfits/{outfit_1_id}/worn",
            headers={"X-User-Id": GOLDEN_USER_ID},
            json={"idempotency_key": idemp_key},
        )
        assert wear_res_2.status_code == 200
        wear_data_2 = wear_res_2.json()["data"]
        assert wear_data_2["times_worn"] == 1
        assert wear_data_2["already_processed"] is True

        # Verify DB wear log and constituent WardrobeItem times_worn increment
        with Session(engine) as session:
            logs = session.exec(select(WearLog).where(WearLog.outfit_id == outfit_1_id)).all()
            assert len(logs) == 1
            assert logs[0].idempotency_key == idemp_key

            outfit_items = session.exec(select(OutfitItem).where(OutfitItem.outfit_id == outfit_1_id)).all()
            assert len(outfit_items) == 3
            for oi in outfit_items:
                wi = session.get(WardrobeItem, oi.wardrobe_item_id)
                assert wi is not None
                assert wi.times_worn == 1

        # --------------------------------------------------------------------
        # 5. Non-Trivial Cross-User Isolation (Negative Paths)
        # --------------------------------------------------------------------
        # User B cannot access Golden User's outfit
        assert client.get(f"/api/v1/outfits/{outfit_1_id}", headers={"X-User-Id": user_b_id}).status_code == 404
        assert client.put(
            f"/api/v1/outfits/{outfit_1_id}/bookmark",
            headers={"X-User-Id": user_b_id},
            json={"is_bookmarked": True},
        ).status_code == 404
        assert client.post(
            f"/api/v1/outfits/{outfit_1_id}/worn",
            headers={"X-User-Id": user_b_id},
            json={"idempotency_key": str(uuid4())},
        ).status_code == 404
        assert client.put(
            f"/api/v1/outfits/{outfit_1_id}/rating",
            headers={"X-User-Id": user_b_id},
            json={"stars": 5, "source": "manual"},
        ).status_code == 404

        # User B's saved outfits list is completely isolated (empty)
        user_b_saved = client.get("/api/v1/outfits/saved", headers={"X-User-Id": user_b_id})
        assert user_b_saved.status_code == 200
        assert user_b_saved.json()["data"]["total"] == 0
        assert len(user_b_saved.json()["data"]["items"]) == 0

        # --------------------------------------------------------------------
        # 6. Manual Rating & Idempotent Upsert
        # --------------------------------------------------------------------
        rate_res_1 = client.put(
            f"/api/v1/outfits/{outfit_1_id}/rating",
            headers={"X-User-Id": GOLDEN_USER_ID},
            json={"stars": 5, "source": "manual"},
        )
        assert rate_res_1.status_code == 200
        rate_data_1 = rate_res_1.json()["data"]
        assert rate_data_1["stars"] == 5
        assert rate_data_1["ratings_count"] == 1
        assert rate_data_1["source"] == "manual"

        # Update rating to 4 stars: must update rating record without double-counting ratings_count
        rate_res_2 = client.put(
            f"/api/v1/outfits/{outfit_1_id}/rating",
            headers={"X-User-Id": GOLDEN_USER_ID},
            json={"stars": 4, "source": "manual"},
        )
        assert rate_res_2.status_code == 200
        rate_data_2 = rate_res_2.json()["data"]
        assert rate_data_2["stars"] == 4
        assert rate_data_2["ratings_count"] == 1

        with Session(engine) as session:
            ratings = session.exec(select(Rating).where(Rating.outfit_id == outfit_1_id)).all()
            assert len(ratings) == 1
            assert ratings[0].stars == 4

        # --------------------------------------------------------------------
        # 7. Bounded Preference Learning
        # --------------------------------------------------------------------
        with Session(engine) as session:
            pref = session.get(UserPreference, GOLDEN_USER_ID)
            assert pref is not None
            assert pref.ratings_count == 1
            assert isinstance(pref.learned_feature_weights, dict)
            weights_map = pref.learned_feature_weights.get("weights", {})
            assert isinstance(weights_map, dict)
            for feat_key, weight in weights_map.items():
                assert -1.0 <= weight <= 1.0, f"Feature weight {feat_key}={weight} not bounded in [-1.0, 1.0]"

        # --------------------------------------------------------------------
        # 8. Cadence Dismissal Without Session Suppression
        # --------------------------------------------------------------------
        session_to_dismiss = str(uuid4())
        dismiss_res = client.post(
            "/api/v1/feedback/prompts/dismiss",
            headers={
                "X-User-Id": GOLDEN_USER_ID,
                "X-Client-Session-Id": session_to_dismiss,
            },
            json={"client_session_id": session_to_dismiss},
        )
        assert dismiss_res.status_code == 200
        dismiss_data = dismiss_res.json()["data"]
        assert dismiss_data["dismissed"] is True
        assert dismiss_data["cooldown_remaining"] >= 3

        with Session(engine) as session:
            suppressed = session.exec(
                select(FeedbackSuppressedSession).where(
                    FeedbackSuppressedSession.user_id == GOLDEN_USER_ID,
                    FeedbackSuppressedSession.client_session_id == session_to_dismiss,
                )
            ).first()
            assert suppressed is None

        # --------------------------------------------------------------------
        # 9. Prompted Rating Flow & Session Suppression
        # --------------------------------------------------------------------
        session_prompted = str(uuid4())
        rate_prompted_res = client.put(
            f"/api/v1/outfits/{outfit_2_id}/rating",
            headers={
                "X-User-Id": GOLDEN_USER_ID,
                "X-Client-Session-Id": session_prompted,
            },
            json={
                "stars": 5,
                "source": "prompted",
                "client_session_id": session_prompted,
            },
        )
        assert rate_prompted_res.status_code == 200
        p_data = rate_prompted_res.json()["data"]
        assert p_data["source"] == "prompted"
        assert p_data["stars"] == 5
        assert p_data["ratings_count"] == 2

        with Session(engine) as session:
            p_suppressed = session.exec(
                select(FeedbackSuppressedSession).where(
                    FeedbackSuppressedSession.user_id == GOLDEN_USER_ID,
                    FeedbackSuppressedSession.client_session_id == session_prompted,
                )
            ).first()
            assert p_suppressed is not None

    finally:
        app.dependency_overrides.clear()

