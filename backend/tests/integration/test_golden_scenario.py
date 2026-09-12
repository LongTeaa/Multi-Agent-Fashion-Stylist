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
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    User,
    WardrobeCategory,
    WardrobeItem,
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
