from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.dependencies import get_db_session
from app.main import app
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    OutfitItem,
    OutfitRecommendation,
    OutfitSlotRole,
    Rating,
    RatingSource,
    User,
    WardrobeCategory,
    WardrobeItem,
    WearLog,
)


def _create_user(session: Session, user_id: str | None = None) -> User:
    uid = user_id or str(uuid4())
    user = User(id=uid, email=f"{uid}@example.com", name="Test User")
    session.add(user)
    session.commit()
    return user


def _create_wardrobe_item(
    session: Session,
    user_id: str,
    category: WardrobeCategory,
    sub_category: str,
    primary_color: str = "white",
    style: str = "smart_casual",
    is_active: bool = True,
    deleted: bool = False,
    with_media: bool = True,
) -> WardrobeItem:
    item_id = str(uuid4())
    item = WardrobeItem(
        id=item_id,
        user_id=user_id,
        category=category,
        sub_category=sub_category,
        primary_color=primary_color,
        pattern="solid",
        material="cotton",
        style=style,
        fit="regular",
        formality_level=3,
        weather_suitability=["warm", "cool"],
        free_text_tags=[style, primary_color, sub_category],
        is_user_confirmed=True,
        is_active=is_active,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    session.add(item)
    session.commit()

    if with_media:
        media_id = str(uuid4())
        media = MediaAsset(
            id=media_id,
            user_id=user_id,
            kind=MediaKind.ORIGINAL,
            bucket="user-media",
            object_key=f"{user_id}/{media_id}.jpg",
            mime_type="image/jpeg",
            size_bytes=2048,
            width=800,
            height=600,
            sha256="b" * 64,
        )
        session.add(media)
        session.commit()

        link = ItemMedia(
            wardrobe_item_id=item_id,
            media_asset_id=media_id,
            user_id=user_id,
            role=ItemMediaRole.PRIMARY,
        )
        session.add(link)
        session.commit()

    return item


def _create_outfit(
    session: Session,
    user_id: str,
    *,
    outfit_id: str | None = None,
    is_bookmarked: bool = False,
    created_at: datetime | None = None,
) -> OutfitRecommendation:
    outfit = OutfitRecommendation(
        id=outfit_id or str(uuid4()),
        user_id=user_id,
        request_id=str(uuid4()),
        user_query="Tối nay đi cafe lịch sự nhẹ",
        context_snapshot={"occasion": "cafe", "environment": "outdoor"},
        explanation_vi="Set đồ phù hợp với không gian cafe thanh lịch.",
        fashion_score=0.88,
        personalization_score=0.92,
        composite_score=0.90,
        rank=1,
        is_bookmarked=is_bookmarked,
        rule_version="v1.0",
        created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(outfit)
    session.commit()
    return outfit


@pytest.fixture
def api_client(migrated_database: tuple[object, object]):
    _, engine = migrated_database

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    client = TestClient(app)
    try:
        yield client, engine
    finally:
        app.dependency_overrides.pop(get_db_session, None)


# ============================================================================
# 1. OUTFIT DETAIL TESTS
# ============================================================================

def test_get_outfit_detail_success(api_client):
    client, engine = api_client
    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "polo", "white")
        bottom = _create_wardrobe_item(session, user.id, WardrobeCategory.BOTTOM, "chinos", "navy")
        shoes = _create_wardrobe_item(session, user.id, WardrobeCategory.FOOTWEAR, "sneakers", "white")

        outfit = _create_outfit(session, user.id, is_bookmarked=False)

        # Attach items in arbitrary order to test deterministic slot sorting
        session.add(OutfitItem(outfit_id=outfit.id, wardrobe_item_id=shoes.id, user_id=user.id, slot_role=OutfitSlotRole.FOOTWEAR))
        session.add(OutfitItem(outfit_id=outfit.id, wardrobe_item_id=top.id, user_id=user.id, slot_role=OutfitSlotRole.TOP))
        session.add(OutfitItem(outfit_id=outfit.id, wardrobe_item_id=bottom.id, user_id=user.id, slot_role=OutfitSlotRole.BOTTOM))

        # Add wear log
        wear_time = datetime.now(timezone.utc) - timedelta(days=2)
        session.add(WearLog(id=str(uuid4()), outfit_id=outfit.id, user_id=user.id, worn_at=wear_time, idempotency_key=str(uuid4())))

        # Add rating
        session.add(Rating(id=str(uuid4()), outfit_id=outfit.id, user_id=user.id, stars=4, source=RatingSource.MANUAL))
        session.commit()

        outfit_id = outfit.id
        user_id = user.id
        top_id = top.id
        bottom_id = bottom.id
        shoes_id = shoes.id

    resp = client.get(f"/api/v1/outfits/{outfit_id}", headers={"X-User-Id": user_id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]

    assert data["id"] == outfit_id
    assert data["composite_score"] == 0.90
    assert data["fashion_score"] == 0.88
    assert data["personalization_score"] == 0.92
    assert data["rank"] == 1
    assert data["is_bookmarked"] is False
    assert data["times_worn"] == 1
    assert data["last_worn_at"] is not None
    assert data["user_rating"] == 4

    # Verify items order: TOP, BOTTOM, FOOTWEAR
    items = data["items"]
    assert len(items) == 3
    assert items[0]["slot_role"] == "top"
    assert items[0]["wardrobe_item_id"] == top_id
    assert items[0]["image_url"].startswith("/api/v1/media/")
    assert "bucket" not in items[0]
    assert "object_key" not in items[0]

    assert items[1]["slot_role"] == "bottom"
    assert items[1]["wardrobe_item_id"] == bottom_id

    assert items[2]["slot_role"] == "footwear"
    assert items[2]["wardrobe_item_id"] == shoes_id


def test_get_outfit_detail_unknown_404(api_client):
    client, _ = api_client
    unknown_id = str(uuid4())
    resp = client.get(f"/api/v1/outfits/{unknown_id}", headers={"X-User-Id": "user-404"})
    assert resp.status_code == 404
    data = resp.json()
    assert data["success"] is False
    assert data["error"]["code"] == "OUTFIT_NOT_FOUND"


def test_get_outfit_detail_cross_user_isolation_404(api_client):
    client, engine = api_client
    with Session(engine) as session:
        user_a = _create_user(session)
        user_b = _create_user(session)
        outfit_a = _create_outfit(session, user_a.id)
        outfit_id = outfit_a.id
        user_b_id = user_b.id

    # User B requests User A's outfit
    resp = client.get(f"/api/v1/outfits/{outfit_id}", headers={"X-User-Id": user_b_id})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "OUTFIT_NOT_FOUND"


def test_get_outfit_detail_with_inactive_or_deleted_items(api_client):
    client, engine = api_client
    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "t-shirt", is_active=False, deleted=True)
        outfit = _create_outfit(session, user.id)
        session.add(OutfitItem(outfit_id=outfit.id, wardrobe_item_id=top.id, user_id=user.id, slot_role=OutfitSlotRole.TOP))
        session.commit()
        outfit_id = outfit.id
        user_id = user.id

    # Must return 200 without crashing and indicate is_active=False
    resp = client.get(f"/api/v1/outfits/{outfit_id}", headers={"X-User-Id": user_id})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["items"]) == 1
    assert data["items"][0]["is_active"] is False


# ============================================================================
# 2. SAVED OUTFITS TESTS
# ============================================================================

def test_get_saved_outfits_empty(api_client):
    client, engine = api_client
    with Session(engine) as session:
        user = _create_user(session)
        user_id = user.id

    resp = client.get("/api/v1/outfits/saved", headers={"X-User-Id": user_id})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["items"] == []


def test_get_saved_outfits_pagination_and_tie_break(api_client):
    client, engine = api_client
    base_time = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)
    saved_ids = []

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "polo")

        # 5 bookmarked outfits with distinct created_at
        for i in range(5):
            t = base_time + timedelta(hours=i)
            o = _create_outfit(session, user.id, is_bookmarked=True, created_at=t)
            session.add(OutfitItem(outfit_id=o.id, wardrobe_item_id=top.id, user_id=user.id, slot_role=OutfitSlotRole.TOP))
            session.commit()
            saved_ids.append(o.id)

        # 2 non-bookmarked outfits (must NOT be in saved list)
        for _ in range(2):
            o_unbookmarked = _create_outfit(session, user.id, is_bookmarked=False)
            session.add(OutfitItem(outfit_id=o_unbookmarked.id, wardrobe_item_id=top.id, user_id=user.id, slot_role=OutfitSlotRole.TOP))
            session.commit()

        user_id = user.id

    # Expected order: newest first (saved_ids[4], saved_ids[3], ...)
    expected_order = list(reversed(saved_ids))

    # Page 1, page_size 2
    r1 = client.get("/api/v1/outfits/saved?page=1&page_size=2", headers={"X-User-Id": user_id})
    assert r1.status_code == 200
    d1 = r1.json()["data"]
    assert d1["total"] == 5
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert len(d1["items"]) == 2
    assert d1["items"][0]["id"] == expected_order[0]
    assert d1["items"][1]["id"] == expected_order[1]

    # Page 2, page_size 2
    r2 = client.get("/api/v1/outfits/saved?page=2&page_size=2", headers={"X-User-Id": user_id})
    assert r2.status_code == 200
    d2 = r2.json()["data"]
    assert len(d2["items"]) == 2
    assert d2["items"][0]["id"] == expected_order[2]
    assert d2["items"][1]["id"] == expected_order[3]

    # Page 3, page_size 2
    r3 = client.get("/api/v1/outfits/saved?page=3&page_size=2", headers={"X-User-Id": user_id})
    assert r3.status_code == 200
    d3 = r3.json()["data"]
    assert len(d3["items"]) == 1
    assert d3["items"][0]["id"] == expected_order[4]


# ============================================================================
# 3. BOOKMARK TESTS
# ============================================================================

def test_set_bookmark_idempotency(api_client):
    client, engine = api_client
    with Session(engine) as session:
        user = _create_user(session)
        outfit = _create_outfit(session, user.id, is_bookmarked=False)
        outfit_id = outfit.id
        user_id = user.id

    headers = {"X-User-Id": user_id}

    # 1. Bookmark = True
    r1 = client.put(f"/api/v1/outfits/{outfit_id}/bookmark", headers=headers, json={"is_bookmarked": True})
    assert r1.status_code == 200
    assert r1.json()["data"]["is_bookmarked"] is True

    with Session(engine) as session:
        db_outfit = session.get(OutfitRecommendation, outfit_id)
        assert db_outfit.is_bookmarked is True

    # 2. Repeated bookmark = True (idempotent)
    r2 = client.put(f"/api/v1/outfits/{outfit_id}/bookmark", headers=headers, json={"is_bookmarked": True})
    assert r2.status_code == 200
    assert r2.json()["data"]["is_bookmarked"] is True

    # 3. Unbookmark = False
    r3 = client.put(f"/api/v1/outfits/{outfit_id}/bookmark", headers=headers, json={"is_bookmarked": False})
    assert r3.status_code == 200
    assert r3.json()["data"]["is_bookmarked"] is False

    with Session(engine) as session:
        db_outfit = session.get(OutfitRecommendation, outfit_id)
        assert db_outfit.is_bookmarked is False


def test_bookmark_cross_user_denial_404(api_client):
    client, engine = api_client
    with Session(engine) as session:
        user_a = _create_user(session)
        user_b = _create_user(session)
        outfit_a = _create_outfit(session, user_a.id, is_bookmarked=False)
        outfit_id = outfit_a.id
        user_b_id = user_b.id

    # User B attempts to bookmark User A's outfit
    resp = client.put(
        f"/api/v1/outfits/{outfit_id}/bookmark",
        headers={"X-User-Id": user_b_id},
        json={"is_bookmarked": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "OUTFIT_NOT_FOUND"

    with Session(engine) as session:
        db_outfit = session.get(OutfitRecommendation, outfit_id)
        assert db_outfit.is_bookmarked is False


def test_get_saved_outfits_deterministic_id_tie_break(api_client):
    """INVARIANT: When created_at timestamps are identical, tie-break must strictly order by id DESC."""
    client, engine = api_client
    same_time = datetime(2026, 9, 14, 15, 0, 0, tzinfo=timezone.utc)

    # Three explicit deterministic UUIDs
    id_1 = "11111111-1111-1111-1111-111111111111"
    id_2 = "22222222-2222-2222-2222-222222222222"
    id_3 = "33333333-3333-3333-3333-333333333333"

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "polo")
        user_id = user.id
        top_id = top.id

        for oid in [id_1, id_3, id_2]:
            _create_outfit(
                session,
                user_id,
                outfit_id=oid,
                is_bookmarked=True,
                created_at=same_time,
            )
            session.add(OutfitItem(outfit_id=oid, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    resp = client.get("/api/v1/outfits/saved", headers={"X-User-Id": user_id})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 3
    # Must be ordered by id DESC: id_3 > id_2 > id_1
    assert items[0]["id"] == id_3
    assert items[1]["id"] == id_2
    assert items[2]["id"] == id_1


def test_get_outfit_detail_with_soft_deleted_media(api_client):
    """INVARIANT: If an item's media asset is soft-deleted, image_url must be None instead of broken 404 URL."""
    client, engine = api_client
    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "polo", with_media=True)

        # Soft-delete the media asset
        media_link = session.exec(select(ItemMedia).where(ItemMedia.wardrobe_item_id == top.id)).first()
        assert media_link is not None
        media_asset = session.get(MediaAsset, media_link.media_asset_id)
        assert media_asset is not None
        media_asset.deleted_at = datetime.now(timezone.utc)
        session.add(media_asset)

        outfit = _create_outfit(session, user.id)
        session.add(OutfitItem(outfit_id=outfit.id, wardrobe_item_id=top.id, user_id=user.id, slot_role=OutfitSlotRole.TOP))
        session.commit()

        outfit_id = outfit.id
        user_id = user.id

    resp = client.get(f"/api/v1/outfits/{outfit_id}", headers={"X-User-Id": user_id})
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    # Must be None since the media asset is deleted
    assert items[0]["image_url"] is None


def test_set_bookmark_updated_at_stability_on_idempotent_retry(api_client):
    """INVARIANT: Repeated idempotent bookmark requests must return stable persistent updated_at timestamp."""
    client, engine = api_client
    with Session(engine) as session:
        user = _create_user(session)
        outfit = _create_outfit(session, user.id, is_bookmarked=False)
        outfit_id = outfit.id
        user_id = user.id

    headers = {"X-User-Id": user_id}

    # 1. First bookmark: updates state
    r1 = client.put(f"/api/v1/outfits/{outfit_id}/bookmark", headers=headers, json={"is_bookmarked": True})
    assert r1.status_code == 200
    t1 = r1.json()["data"]["updated_at"]

    # 2. Idempotent retry with same boolean: timestamp must be identical
    r2 = client.put(f"/api/v1/outfits/{outfit_id}/bookmark", headers=headers, json={"is_bookmarked": True})
    assert r2.status_code == 200
    t2 = r2.json()["data"]["updated_at"]
    assert t1 == t2, "Idempotent retry with unchanged state must return stable updated_at timestamp"


# ============================================================================
# 4. WORN TRACKING TESTS (TASK 5.3)
# ============================================================================

def test_mark_outfit_worn_first_time(api_client):
    """INVARIANT: First wear event persists WearLog, increments times_worn on items, and sets last_worn_at."""
    client, engine = api_client
    target_time = datetime.now(timezone.utc) - timedelta(hours=1)
    idempotency_key = str(uuid4())

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "t-shirt")
        bottom = _create_wardrobe_item(session, user.id, WardrobeCategory.BOTTOM, "jeans")
        outfit = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        bottom_id = bottom.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=bottom_id, user_id=user_id, slot_role=OutfitSlotRole.BOTTOM))
        session.commit()

    headers = {"X-User-Id": user_id}
    payload = {
        "idempotency_key": idempotency_key,
        "worn_at": target_time.isoformat(),
    }

    resp = client.post(f"/api/v1/outfits/{outfit_id}/worn", headers=headers, json=payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["outfit_id"] == outfit_id
    assert data["times_worn"] == 1
    assert data["already_processed"] is False
    assert datetime.fromisoformat(data["worn_at"]) == target_time

    # Verify DB projection
    with Session(engine) as session:
        logs = session.exec(select(WearLog).where(WearLog.outfit_id == outfit_id)).all()
        assert len(logs) == 1
        assert logs[0].idempotency_key == idempotency_key

        db_top = session.get(WardrobeItem, top_id)
        assert db_top.times_worn == 1
        assert db_top.last_worn_at is not None

        db_bottom = session.get(WardrobeItem, bottom_id)
        assert db_bottom.times_worn == 1
        assert db_bottom.last_worn_at is not None


def test_mark_outfit_worn_idempotent_retry(api_client):
    """INVARIANT: Idempotent retry with identical idempotency_key returns already_processed=True and does not duplicate."""
    client, engine = api_client
    idempotency_key = str(uuid4())

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "polo")
        outfit = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    headers = {"X-User-Id": user_id}
    payload = {"idempotency_key": idempotency_key}

    # 1. Initial wear call
    r1 = client.post(f"/api/v1/outfits/{outfit_id}/worn", headers=headers, json=payload)
    assert r1.status_code == 200
    d1 = r1.json()["data"]
    assert d1["already_processed"] is False
    assert d1["times_worn"] == 1

    # 2. Idempotent retry with same key
    r2 = client.post(f"/api/v1/outfits/{outfit_id}/worn", headers=headers, json=payload)
    assert r2.status_code == 200
    d2 = r2.json()["data"]
    assert d2["already_processed"] is True
    assert d2["times_worn"] == 1
    assert d2["wear_log_id"] == d1["wear_log_id"]

    # Verify DB has exactly one wear log and times_worn is still 1
    with Session(engine) as session:
        logs = session.exec(select(WearLog).where(WearLog.outfit_id == outfit_id)).all()
        assert len(logs) == 1
        db_top = session.get(WardrobeItem, top_id)
        assert db_top.times_worn == 1


def test_mark_outfit_worn_different_key_increments(api_client):
    """INVARIANT: Different idempotency keys represent distinct wear events and increment times_worn."""
    client, engine = api_client
    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "shirt")
        outfit = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    headers = {"X-User-Id": user_id}

    # Wear 1
    r1 = client.post(f"/api/v1/outfits/{outfit_id}/worn", headers=headers, json={"idempotency_key": str(uuid4())})
    assert r1.status_code == 200
    assert r1.json()["data"]["times_worn"] == 1

    # Wear 2 (distinct key)
    r2 = client.post(f"/api/v1/outfits/{outfit_id}/worn", headers=headers, json={"idempotency_key": str(uuid4())})
    assert r2.status_code == 200
    assert r2.json()["data"]["times_worn"] == 2

    with Session(engine) as session:
        logs = session.exec(select(WearLog).where(WearLog.outfit_id == outfit_id)).all()
        assert len(logs) == 2
        db_top = session.get(WardrobeItem, top_id)
        assert db_top.times_worn == 2


def test_mark_outfit_worn_idempotency_conflict_409(api_client):
    """INVARIANT: Reusing the same idempotency key for a different outfit must return 409 IDEMPOTENCY_CONFLICT."""
    client, engine = api_client
    shared_key = str(uuid4())

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "polo")
        outfit_1 = _create_outfit(session, user.id)
        outfit_2 = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        outfit_1_id = outfit_1.id
        outfit_2_id = outfit_2.id

        session.add(OutfitItem(outfit_id=outfit_1_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.add(OutfitItem(outfit_id=outfit_2_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    headers = {"X-User-Id": user_id}

    # Wear outfit 1 with shared_key
    r1 = client.post(f"/api/v1/outfits/{outfit_1_id}/worn", headers=headers, json={"idempotency_key": shared_key})
    assert r1.status_code == 200

    # Attempt to wear outfit 2 with the same key -> 409 Conflict
    r2 = client.post(f"/api/v1/outfits/{outfit_2_id}/worn", headers=headers, json={"idempotency_key": shared_key})
    assert r2.status_code == 409
    err = r2.json()
    assert err["success"] is False
    assert err["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_mark_outfit_worn_past_timestamp_preserves_latest_last_worn(api_client):
    """INVARIANT: Marking wear at a past timestamp increments times_worn but does NOT rewind last_worn_at."""
    client, engine = api_client
    now = datetime.now(timezone.utc)
    recent_worn_at = now - timedelta(days=1)
    past_worn_at = now - timedelta(days=5)

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "jacket")
        # Pre-set top's wear history
        top.times_worn = 1
        top.last_worn_at = recent_worn_at
        session.add(top)

        outfit = _create_outfit(session, user.id)
        user_id = user.id
        top_id = top.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    headers = {"X-User-Id": user_id}

    # Mark as worn 5 days ago (older than existing last_worn_at of 1 day ago)
    resp = client.post(
        f"/api/v1/outfits/{outfit_id}/worn",
        headers=headers,
        json={"idempotency_key": str(uuid4()), "worn_at": past_worn_at.isoformat()},
    )
    assert resp.status_code == 200

    with Session(engine) as session:
        db_top = session.get(WardrobeItem, top_id)
        # times_worn incremented to 2
        assert db_top.times_worn == 2
        # last_worn_at was NOT rewound to 5 days ago; it remains 1 day ago
        item_last = db_top.last_worn_at
        if item_last.tzinfo is None:
            item_last = item_last.replace(tzinfo=timezone.utc)
        assert item_last == recent_worn_at


def test_mark_outfit_worn_cross_user_isolation_404(api_client):
    """INVARIANT: User B cannot mark User A's outfit as worn (returns 404 OUTFIT_NOT_FOUND)."""
    client, engine = api_client
    with Session(engine) as session:
        user_a = _create_user(session)
        user_b = _create_user(session)
        top_a = _create_wardrobe_item(session, user_a.id, WardrobeCategory.TOP, "polo")
        outfit_a = _create_outfit(session, user_a.id)

        session.add(OutfitItem(outfit_id=outfit_a.id, wardrobe_item_id=top_a.id, user_id=user_a.id, slot_role=OutfitSlotRole.TOP))
        session.commit()

        outfit_id = outfit_a.id
        user_b_id = user_b.id

    resp = client.post(
        f"/api/v1/outfits/{outfit_id}/worn",
        headers={"X-User-Id": user_b_id},
        json={"idempotency_key": str(uuid4())},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "OUTFIT_NOT_FOUND"

    with Session(engine) as session:
        logs = session.exec(select(WearLog).where(WearLog.outfit_id == outfit_id)).all()
        assert len(logs) == 0


def test_mark_outfit_worn_integrates_with_personalization_anti_repetition(api_client):
    """INVARIANT: Worn outfit immediately feeds into get_user_personalization_data for 72h/48h penalties."""
    from app.agents.personalization_agent import get_user_personalization_data

    client, engine = api_client
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "linen shirt")
        bottom = _create_wardrobe_item(session, user.id, WardrobeCategory.BOTTOM, "chinos")
        outfit = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        bottom_id = bottom.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=bottom_id, user_id=user_id, slot_role=OutfitSlotRole.BOTTOM))
        session.commit()

    headers = {"X-User-Id": user_id}

    # Mark as worn 2 hours ago
    worn_time = now - timedelta(hours=2)
    resp = client.post(
        f"/api/v1/outfits/{outfit_id}/worn",
        headers=headers,
        json={"idempotency_key": str(uuid4()), "worn_at": worn_time.isoformat()},
    )
    assert resp.status_code == 200

    # Query personalization data at reference time `now`
    with Session(engine) as session:
        _, recent_wear_data = get_user_personalization_data(session, user_id, reference_time=now)
        # Exact outfit must be in 72h list
        assert {top_id, bottom_id} in recent_wear_data["exact_outfits_72h"]
        # Constituent items must be in 48h set
        assert top_id in recent_wear_data["items_worn_48h"]
        assert bottom_id in recent_wear_data["items_worn_48h"]


def test_mark_outfit_worn_conflicting_payload_same_outfit_different_worn_at_409(api_client):
    """INVARIANT: Reusing the same idempotency key with conflicting worn_at on same outfit returns 409 IDEMPOTENCY_CONFLICT."""
    client, engine = api_client
    shared_key = str(uuid4())
    now = datetime.now(timezone.utc)
    t1 = now - timedelta(hours=3)
    t2 = now - timedelta(hours=1)

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "t-shirt")
        outfit = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    headers = {"X-User-Id": user_id}

    # Request 1: Initial wear with t1 -> 200
    r1 = client.post(
        f"/api/v1/outfits/{outfit_id}/worn",
        headers=headers,
        json={"idempotency_key": shared_key, "worn_at": t1.isoformat()},
    )
    assert r1.status_code == 200

    # Request 2: Same key, same outfit, but DIFFERENT worn_at (t2 != t1) -> 409
    r2 = client.post(
        f"/api/v1/outfits/{outfit_id}/worn",
        headers=headers,
        json={"idempotency_key": shared_key, "worn_at": t2.isoformat()},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    # Request 3: Same key, same outfit, but worn_at is None -> 409
    r3 = client.post(
        f"/api/v1/outfits/{outfit_id}/worn",
        headers=headers,
        json={"idempotency_key": shared_key},
    )
    assert r3.status_code == 409
    assert r3.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_mark_outfit_worn_concurrent_same_key_race_resolves_idempotently(api_client):
    """INVARIANT: Concurrent requests with same idempotency_key must not crash with 500 and must resolve idempotently."""
    from concurrent.futures import ThreadPoolExecutor

    client, engine = api_client
    shared_key = str(uuid4())
    worn_time = datetime.now(timezone.utc) - timedelta(hours=1)

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "polo")
        outfit = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    headers = {"X-User-Id": user_id}
    payload = {"idempotency_key": shared_key, "worn_at": worn_time.isoformat()}

    def send_request():
        return client.post(f"/api/v1/outfits/{outfit_id}/worn", headers=headers, json=payload)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_request) for _ in range(5)]
        responses = [f.result() for f in futures]

    # All responses must succeed with 200 (no 500s)
    status_codes = [r.status_code for r in responses]
    assert all(code == 200 for code in status_codes), f"Unexpected status codes: {status_codes}"

    already_processed_flags = [r.json()["data"]["already_processed"] for r in responses]
    # Exactly one request was the initial creator, the remaining 4 were idempotent recoveries
    assert already_processed_flags.count(False) == 1
    assert already_processed_flags.count(True) == 4

    with Session(engine) as session:
        logs = session.exec(select(WearLog).where(WearLog.outfit_id == outfit_id)).all()
        assert len(logs) == 1
        db_top = session.get(WardrobeItem, top_id)
        assert db_top.times_worn == 1


def test_mark_outfit_worn_concurrent_distinct_keys_no_lost_updates(api_client):
    """INVARIANT: Concurrent requests with distinct keys atomically increment times_worn without lost updates."""
    from concurrent.futures import ThreadPoolExecutor

    client, engine = api_client
    worn_time = datetime.now(timezone.utc) - timedelta(hours=1)

    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "henley")
        outfit = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    headers = {"X-User-Id": user_id}

    def send_distinct_wear():
        payload = {"idempotency_key": str(uuid4()), "worn_at": worn_time.isoformat()}
        return client.post(f"/api/v1/outfits/{outfit_id}/worn", headers=headers, json=payload)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_distinct_wear) for _ in range(5)]
        responses = [f.result() for f in futures]

    assert all(r.status_code == 200 for r in responses)

    with Session(engine) as session:
        logs = session.exec(select(WearLog).where(WearLog.outfit_id == outfit_id)).all()
        assert len(logs) == 5
        db_top = session.get(WardrobeItem, top_id)
        # Atomic SQL update must ensure times_worn equals 5 with no lost updates
        assert db_top.times_worn == 5


def test_record_outfit_worn_transaction_rollback_on_failure(api_client):
    """INVARIANT: If an error occurs during record_outfit_worn, transaction rolls back cleanly."""
    from unittest.mock import patch
    from app.services import outfit_service
    from app.schemas.outfits import WornOutfitRequest

    client, engine = api_client
    with Session(engine) as session:
        user = _create_user(session)
        top = _create_wardrobe_item(session, user.id, WardrobeCategory.TOP, "knit")
        outfit = _create_outfit(session, user.id)

        user_id = user.id
        top_id = top.id
        outfit_id = outfit.id

        session.add(OutfitItem(outfit_id=outfit_id, wardrobe_item_id=top_id, user_id=user_id, slot_role=OutfitSlotRole.TOP))
        session.commit()

    payload = WornOutfitRequest(
        idempotency_key=str(uuid4()),
        worn_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )

    # Force an unrecoverable RuntimeError during session.commit
    with Session(engine) as test_session:
        with patch.object(test_session, "commit", side_effect=RuntimeError("Simulated DB Disk Failure")):
            with pytest.raises(RuntimeError, match="Simulated DB Disk Failure"):
                outfit_service.record_outfit_worn(
                    session=test_session,
                    outfit_id=outfit_id,
                    user_id=user_id,
                    payload=payload,
                )

    # Verify that in a new session, no wear log exists and times_worn was not incremented
    with Session(engine) as verify_session:
        logs = verify_session.exec(select(WearLog).where(WearLog.outfit_id == outfit_id)).all()
        assert len(logs) == 0
        db_top = verify_session.get(WardrobeItem, top_id)
        assert db_top.times_worn == 0



