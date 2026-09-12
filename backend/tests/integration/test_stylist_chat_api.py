from __future__ import annotations

from datetime import datetime, timezone
import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.agents.state import OutfitItemSlot, RankedOutfit, StylistContext
from app.core.dependencies import get_db_session, get_stylist_runner, get_utc_clock
from app.main import app
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    User,
    WardrobeCategory,
    WardrobeItem,
)
from app.services.retrieval_document_service import refresh_retrieval_document


def _fixed_clock() -> datetime:
    return datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)


def _add_wardrobe_item(
    session: Session,
    *,
    item_id: str,
    user_id: str,
    category: WardrobeCategory,
    sub_category: str = "generic",
    color: str = "white",
    style: str = "smart_casual",
    formality: int = 3,
    weather: list[str] | None = None,
    material: str = "cotton",
    active: bool = True,
    deleted: bool = False,
    media_id: str | None = None,
) -> WardrobeItem:
    item = WardrobeItem(
        id=item_id,
        user_id=user_id,
        category=category,
        sub_category=sub_category,
        primary_color=color,
        pattern="solid",
        material=material,
        style=style,
        fit="regular",
        formality_level=formality,
        weather_suitability=weather or ["cool", "warm"],
        free_text_tags=[style, color, sub_category],
        is_user_confirmed=True,
        is_active=active,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    session.add(item)
    session.flush()
    refresh_retrieval_document(session, item)

    if media_id:
        media_asset = MediaAsset(
            id=media_id,
            user_id=user_id,
            kind=MediaKind.ORIGINAL,
            bucket="user-media",
            object_key=f"{user_id}/{media_id}.jpg",
            mime_type="image/jpeg",
            size_bytes=1024,
            width=800,
            height=600,
            sha256="a" * 64,
        )
        session.add(media_asset)
        session.flush()

        item_media = ItemMedia(
            wardrobe_item_id=item_id,
            media_asset_id=media_id,
            user_id=user_id,
            role=ItemMediaRole.PRIMARY,
        )
        session.add(item_media)
        session.flush()

    return item


# ============================================================================
# 1. GROUNDED HAPPY PATH
# ============================================================================

def test_stylist_chat_happy_path(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = f"user_api_happy_{uuid4().hex[:8]}"
    top_media_id = f"media_top_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock

    try:
        with Session(engine) as session:
            session.add(User(id=user_id))
            session.flush()

            # Seed complete active wardrobe
            _add_wardrobe_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white", media_id=top_media_id)
            _add_wardrobe_item(session, item_id="bot-01", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="navy")
            _add_wardrobe_item(session, item_id="shoe-01", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")
            _add_wardrobe_item(session, item_id="outer-01", user_id=user_id, category=WardrobeCategory.OUTERWEAR, sub_category="jacket", color="beige")
            _add_wardrobe_item(session, item_id="acc-01", user_id=user_id, category=WardrobeCategory.ACCESSORY, sub_category="belt", color="brown")
            session.commit()

        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_id},
            json={
                "query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?",
                "location": "Hà Nội",
            },
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True

        data = body["data"]
        assert data["needs_clarification"] is False
        assert data["clarification_question"] is None
        assert data["feedback_prompt_eligible"] is False
        assert data["feedback_target_outfit_id"] is None

        # Context assertions
        ctx = data["context"]
        assert ctx is not None
        assert ctx["occasion"] == "cafe"
        assert ctx["weather_condition"] == "cool"
        assert "confidence" not in ctx
        assert "structured_must_have" not in ctx

        # Recommendations assertions
        recs = data["recommendations"]
        assert 1 <= len(recs) <= 3
        ranks = [r["rank"] for r in recs]
        assert ranks == list(range(1, len(recs) + 1))

        rec_ids = [r["outfit_id"] for r in recs]
        for rec in recs:
            assert rec["outfit_id"] is not None
            assert 0.0 <= rec["composite_score"] <= 1.0
            assert rec["explanation_vi"] != ""
            assert len(rec["items"]) >= 3
            # Ensure fashion_score and personalization_score are not exposed
            assert "fashion_score" not in rec
            assert "personalization_score" not in rec

            for item in rec["items"]:
                assert item["slot"] in ["top", "bottom", "dress", "footwear", "outerwear", "accessory"]
                assert item["item_id"] in ["top-01", "bot-01", "shoe-01", "outer-01", "acc-01"]
                if item["item_id"] == "top-01":
                    assert item["image_url"] == f"/api/v1/media/{top_media_id}"
                else:
                    assert item["image_url"] is None or item["image_url"].startswith("/api/v1/media/")

        # Ensure raw storage keys are NOT in serialized response
        raw_text = res.text
        assert "object_key" not in raw_text
        assert "user-media" not in raw_text

        # Verify DB records
        with Session(engine) as session:
            db_recs = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)).all()
            assert len(db_recs) == len(recs)
            assert {r.id for r in db_recs} == set(rec_ids)

            db_items = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_id)).all()
            assert len(db_items) >= 3
            for oi in db_items:
                assert oi.outfit_id in rec_ids

    finally:
        app.dependency_overrides.clear()


# ============================================================================
# 2. CLARIFICATION SUCCESS
# ============================================================================

def test_stylist_chat_clarification(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = f"user_api_clar_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock

    try:
        with Session(engine) as session:
            session.add(User(id=user_id))
            _add_wardrobe_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP)
            session.commit()

        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_id},
            json={"query": "Mặc gì?"},
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True

        data = body["data"]
        assert data["needs_clarification"] is True
        assert data["clarification_question"] is not None
        assert "Bạn dự định mặc trang phục này đi đâu" in data["clarification_question"]
        assert data["recommendations"] == []
        assert data["feedback_prompt_eligible"] is False
        assert data["feedback_target_outfit_id"] is None

        # Zero DB records
        with Session(engine) as session:
            assert session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)).all() == []
            assert session.exec(select(OutfitItem).where(OutfitItem.user_id == user_id)).all() == []

    finally:
        app.dependency_overrides.clear()


# ============================================================================
# 3. EMPTY WARDROBE AND INCOMPLETE WARDROBE
# ============================================================================

def test_stylist_chat_empty_wardrobe(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = f"user_api_empty_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock

    try:
        with Session(engine) as session:
            session.add(User(id=user_id))
            session.commit()

        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_id},
            json={"query": "Đi cafe sáng nay, thời tiết mát mẻ"},
        )

        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "WARDROBE_EMPTY"
        assert body["error"]["message"] == "Tủ đồ của bạn chưa có trang phục. Hãy thêm quần áo trước nhé."

        # Zero DB records
        with Session(engine) as session:
            assert session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)).all() == []
            assert session.exec(select(OutfitItem).where(OutfitItem.user_id == user_id)).all() == []

    finally:
        app.dependency_overrides.clear()


def test_stylist_chat_incomplete_wardrobe(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = f"user_api_inc_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock

    try:
        with Session(engine) as session:
            session.add(User(id=user_id))
            _add_wardrobe_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP)
            session.commit()

        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_id},
            json={"query": "Đi cafe sáng nay, thời tiết mát mẻ"},
        )

        assert res.status_code == 422
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "NO_COMPLETE_OUTFIT"
        assert body["error"]["message"] == "Tủ đồ hiện chưa đủ món để tạo một bộ trang phục hoàn chỉnh."

        # Zero DB records
        with Session(engine) as session:
            assert session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)).all() == []
            assert session.exec(select(OutfitItem).where(OutfitItem.user_id == user_id)).all() == []

    finally:
        app.dependency_overrides.clear()


# ============================================================================
# 4. IDENTITY AND CROSS-USER ISOLATION
# ============================================================================

def test_stylist_chat_identity_header_required(
    migrated_database: tuple[object, object],
) -> None:
    client = TestClient(app)

    # Missing header
    res1 = client.post("/api/v1/stylist/chat", json={"query": "Đi cafe"})
    assert res1.status_code == 422
    assert res1.json()["error"]["code"] == "VALIDATION_ERROR"

    # Blank header
    res2 = client.post("/api/v1/stylist/chat", headers={"X-User-Id": "   "}, json={"query": "Đi cafe"})
    assert res2.status_code == 422
    assert res2.json()["error"]["code"] == "VALIDATION_ERROR"


def test_stylist_chat_cross_user_isolation(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_a = f"user_api_iso_a_{uuid4().hex[:8]}"
    user_b = f"user_api_iso_b_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock

    try:
        with Session(engine) as session:
            session.add_all([User(id=user_a), User(id=user_b)])
            session.flush()

            # Seed User A wardrobe
            _add_wardrobe_item(session, item_id="top-a", user_id=user_a, category=WardrobeCategory.TOP, sub_category="polo")
            _add_wardrobe_item(session, item_id="bot-a", user_id=user_a, category=WardrobeCategory.BOTTOM, sub_category="chinos")
            _add_wardrobe_item(session, item_id="shoe-a", user_id=user_a, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers")

            # Seed User B wardrobe with luxury items
            _add_wardrobe_item(session, item_id="top-b-luxury", user_id=user_b, category=WardrobeCategory.TOP, sub_category="blazer")
            _add_wardrobe_item(session, item_id="bot-b-luxury", user_id=user_b, category=WardrobeCategory.BOTTOM, sub_category="trousers")
            _add_wardrobe_item(session, item_id="shoe-b-luxury", user_id=user_b, category=WardrobeCategory.FOOTWEAR, sub_category="oxford")
            session.commit()

        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_a},
            json={"query": "Đi cafe sáng nay, thời tiết mát mẻ"},
        )

        assert res.status_code == 200
        data = res.json()["data"]

        # Ensure no item in any recommended outfit belongs to User B
        for rec in data["recommendations"]:
            for item in rec["items"]:
                assert "-b-" not in item["item_id"]
                assert item["item_id"] in {"top-a", "bot-a", "shoe-a"}

        # Verify DB records: User A has persisted records, User B has zero
        with Session(engine) as session:
            recs_a = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_a)).all()
            assert len(recs_a) >= 1
            items_a = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_a)).all()
            assert len(items_a) >= 3
            for oi in items_a:
                assert oi.wardrobe_item_id in {"top-a", "bot-a", "shoe-a"}
                assert "-b-" not in oi.wardrobe_item_id

            recs_b = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_b)).all()
            assert len(recs_b) == 0
            items_b = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_b)).all()
            assert len(items_b) == 0

    finally:
        app.dependency_overrides.clear()


# ============================================================================
# 5. INPUT AND INTERNAL-ERROR SAFETY
# ============================================================================

def test_stylist_chat_query_validation(
    migrated_database: tuple[object, object],
) -> None:
    client = TestClient(app)
    headers = {"X-User-Id": "test-user-valid"}

    # Blank query string
    res_empty = client.post("/api/v1/stylist/chat", headers=headers, json={"query": ""})
    assert res_empty.status_code == 422
    assert res_empty.json()["error"]["code"] == "VALIDATION_ERROR"

    # Whitespace only query string
    res_ws = client.post("/api/v1/stylist/chat", headers=headers, json={"query": "   \n  \t "})
    assert res_ws.status_code == 422
    assert res_ws.json()["error"]["code"] == "VALIDATION_ERROR"


def test_stylist_chat_internal_error_safety(
    migrated_database: tuple[object, object],
) -> None:
    _, engine = migrated_database
    user_id = f"user_err_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    def failing_runner(*args, **kwargs):
        raise RuntimeError("CRITICAL_INTERNAL_DB_CRASH: table lock timeout")

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock
    app.dependency_overrides[get_stylist_runner] = lambda: failing_runner

    try:
        with Session(engine) as session:
            session.add(User(id=user_id))
            session.commit()

        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_id},
            json={"query": "Đi ăn tiệc tối nay"},
        )

        assert res.status_code == 502
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "PROVIDER_ERROR"
        assert body["error"]["message"] == "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."

        # Never leak internal crash message or stack trace to client
        raw_text = res.text
        assert "CRITICAL_INTERNAL_DB_CRASH" not in raw_text
        assert "table lock timeout" not in raw_text
        assert "Traceback" not in raw_text

    finally:
        app.dependency_overrides.clear()


def _seed_wardrobe_and_outfit(
    session: Session,
    *,
    user_id: str,
    outfit_id: str,
    rank: int = 1,
) -> tuple[list[str], RankedOutfit]:
    top_id = f"{outfit_id}_top"
    bot_id = f"{outfit_id}_bot"
    shoe_id = f"{outfit_id}_shoe"
    _add_wardrobe_item(session, item_id=top_id, user_id=user_id, category=WardrobeCategory.TOP)
    _add_wardrobe_item(session, item_id=bot_id, user_id=user_id, category=WardrobeCategory.BOTTOM)
    _add_wardrobe_item(session, item_id=shoe_id, user_id=user_id, category=WardrobeCategory.FOOTWEAR)

    outfit_rec = OutfitRecommendation(
        id=outfit_id,
        user_id=user_id,
        request_id=f"req_{outfit_id}",
        user_query="Đi cafe sáng nay",
        context_snapshot={"occasion": "cafe"},
        explanation_vi="Trang phục năng động phù hợp đi cafe.",
        fashion_score=0.9,
        personalization_score=0.9,
        composite_score=0.9,
        rank=rank,
        rule_version="v1",
    )
    session.add(outfit_rec)
    session.flush()

    session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
    session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=bot_id, user_id=user_id, slot_role=OutfitSlotRole.BOTTOM))
    session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=shoe_id, user_id=user_id, slot_role=OutfitSlotRole.FOOTWEAR))
    session.flush()

    items = [
        OutfitItemSlot(
            item_id=top_id,
            slot_role=OutfitSlotRole.TOP,
            name="Áo thun trắng",
            primary_color="white",
            style="casual",
            category=WardrobeCategory.TOP,
            formality_level=3,
        ),
        OutfitItemSlot(
            item_id=bot_id,
            slot_role=OutfitSlotRole.BOTTOM,
            name="Quần jean đen",
            primary_color="black",
            style="casual",
            category=WardrobeCategory.BOTTOM,
            formality_level=3,
        ),
        OutfitItemSlot(
            item_id=shoe_id,
            slot_role=OutfitSlotRole.FOOTWEAR,
            name="Giày sneaker",
            primary_color="white",
            style="casual",
            category=WardrobeCategory.FOOTWEAR,
            formality_level=3,
        ),
    ]
    ranked = RankedOutfit(
        outfit_id=outfit_id,
        rank=rank,
        composite_score=0.9,
        items=items,
        explanation_vi="Trang phục năng động phù hợp đi cafe.",
        applied_preferences=["casual"],
    )
    return [top_id, bot_id, shoe_id], ranked


@pytest.mark.parametrize(
    "case_type",
    ["duplicate_rec_ids", "mismatched_outfit_id", "duplicate_ranked_outfit_ids"],
)
def test_stylist_chat_output_tamper_mismatch_safety(
    migrated_database: tuple[object, object],
    case_type: str,
) -> None:
    """Verify endpoint rejects tampered/mismatched output states with 502 PROVIDER_ERROR."""
    _, engine = migrated_database
    user_id = f"user_tamper_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    with Session(engine) as session:
        session.add(User(id=user_id))
        _, outfit_1 = _seed_wardrobe_and_outfit(session, user_id=user_id, outfit_id="outfit-1", rank=1)
        _, outfit_2 = _seed_wardrobe_and_outfit(session, user_id=user_id, outfit_id="outfit-2", rank=2)
        session.commit()

    valid_context = StylistContext(
        occasion="cafe",
        time_of_day="morning",
        weather_condition="cool",
        needs_clarification=False,
    )

    if case_type == "duplicate_rec_ids":
        # duplicate recommendation_ids
        tampered_rec_ids = ["outfit-1", "outfit-1"]
        ranked_outfits = [outfit_1]
    elif case_type == "mismatched_outfit_id":
        # recommendation_ids has outfit-1, but ranked_outfits has outfit-2
        tampered_rec_ids = ["outfit-1"]
        ranked_outfits = [outfit_2.model_copy(update={"rank": 1})]
    else:  # duplicate_ranked_outfit_ids
        tampered_rec_ids = ["outfit-1", "outfit-2"]
        outfit_dup = outfit_1.model_copy(update={"rank": 2})
        ranked_outfits = [outfit_1, outfit_dup]  # both have outfit_id="outfit-1"

    def tampered_runner(*args, **kwargs):
        return {
            "request_id": "req-tampered",
            "user_id": user_id,
            "context": valid_context,
            "grounding_validated": True,
            "recommendation_ids": tampered_rec_ids,
            "ranked_outfits": ranked_outfits,
            "errors": [],
        }

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock
    app.dependency_overrides[get_stylist_runner] = lambda: tampered_runner

    try:
        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_id},
            json={"query": "Đi cafe sáng nay"},
        )

        assert res.status_code == 502
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "PROVIDER_ERROR"
        assert body["error"]["message"] == "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."

    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "case_type",
    ["rank_gap_single", "duplicate_ranks", "rank_gap_sequence"],
)
def test_stylist_chat_output_rank_sequence_safety(
    migrated_database: tuple[object, object],
    case_type: str,
) -> None:
    """Verify endpoint rejects non-consecutive or duplicate ranks with 502 PROVIDER_ERROR."""
    _, engine = migrated_database
    user_id = f"user_rank_tamper_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    with Session(engine) as session:
        session.add(User(id=user_id))
        _, outfit_1 = _seed_wardrobe_and_outfit(session, user_id=user_id, outfit_id="outfit-1", rank=1)
        _, outfit_2 = _seed_wardrobe_and_outfit(session, user_id=user_id, outfit_id="outfit-2", rank=2)
        session.commit()

    valid_context = StylistContext(
        occasion="cafe",
        time_of_day="morning",
        weather_condition="cool",
        needs_clarification=False,
    )

    if case_type == "rank_gap_single":
        # 1 outfit but rank is 2 (gap, not starting at 1)
        tampered_rec_ids = ["outfit-1"]
        ranked_outfits = [outfit_1.model_copy(update={"rank": 2})]
    elif case_type == "duplicate_ranks":
        # 2 outfits both have rank 1
        tampered_rec_ids = ["outfit-1", "outfit-2"]
        ranked_outfits = [outfit_1, outfit_2.model_copy(update={"rank": 1})]
    else:  # rank_gap_sequence
        # 2 outfits with ranks [1, 3] (missing rank 2)
        tampered_rec_ids = ["outfit-1", "outfit-2"]
        ranked_outfits = [outfit_1, outfit_2.model_copy(update={"rank": 3})]

    def tampered_runner(*args, **kwargs):
        return {
            "request_id": "req-rank-tampered",
            "user_id": user_id,
            "context": valid_context,
            "grounding_validated": True,
            "recommendation_ids": tampered_rec_ids,
            "ranked_outfits": ranked_outfits,
            "errors": [],
        }

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock
    app.dependency_overrides[get_stylist_runner] = lambda: tampered_runner

    try:
        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_id},
            json={"query": "Đi cafe sáng nay"},
        )

        assert res.status_code == 502
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "PROVIDER_ERROR"
        assert body["error"]["message"] == "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."

    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "invalid_score",
    [1.1, -0.01, float("nan"), float("inf"), float("-inf")],
)
def test_stylist_chat_output_composite_score_safety(
    migrated_database: tuple[object, object],
    invalid_score: float,
) -> None:
    """Verify endpoint rejects invalid composite_score with 502 PROVIDER_ERROR rather than 500."""
    _, engine = migrated_database
    user_id = f"user_score_tamper_{uuid4().hex[:8]}"

    def override_db():
        with Session(engine) as session:
            yield session

    with Session(engine) as session:
        session.add(User(id=user_id))
        _, outfit_1 = _seed_wardrobe_and_outfit(session, user_id=user_id, outfit_id="outfit-1", rank=1)
        session.commit()

    valid_context = StylistContext(
        occasion="cafe",
        time_of_day="morning",
        weather_condition="cool",
        needs_clarification=False,
    )

    tampered_outfit = outfit_1.model_copy(update={"composite_score": invalid_score})

    def tampered_runner(*args, **kwargs):
        return {
            "request_id": "req-score-tampered",
            "user_id": user_id,
            "context": valid_context,
            "grounding_validated": True,
            "recommendation_ids": ["outfit-1"],
            "ranked_outfits": [tampered_outfit],
            "errors": [],
        }

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_utc_clock] = lambda: _fixed_clock
    app.dependency_overrides[get_stylist_runner] = lambda: tampered_runner

    try:
        client = TestClient(app)
        res = client.post(
            "/api/v1/stylist/chat",
            headers={"X-User-Id": user_id},
            json={"query": "Đi cafe sáng nay"},
        )

        assert res.status_code == 502
        body = res.json()
        assert body["success"] is False
        assert body["error"]["code"] == "PROVIDER_ERROR"
        assert body["error"]["message"] == "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."

    finally:
        app.dependency_overrides.clear()
