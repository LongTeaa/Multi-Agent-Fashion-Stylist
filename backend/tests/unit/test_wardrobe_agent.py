from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlmodel import Session

from app.agents.state import StylistContext, StylistGraphState
from app.agents.wardrobe_agent import (
    EMPTY_WARDROBE_ERROR,
    EMPTY_WARDROBE_WARNING,
    retrieve_candidate_pool,
    wardrobe_agent_node,
)
from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    OutfitSlotRole,
    User,
    WardrobeCategory,
    WardrobeItem,
)
from app.services.retrieval_document_service import refresh_retrieval_document


def _add_item(
    session: Session,
    *,
    item_id: str,
    user_id: str,
    category: WardrobeCategory = WardrobeCategory.TOP,
    sub_category: str = "polo",
    color: str = "white",
    material: str = "cotton",
    style: str = "smart_casual",
    formality: int = 3,
    weather: list[str] | None = None,
    tags: list[str] | None = None,
    confirmed: bool = True,
    active: bool = True,
    deleted: bool = False,
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
        weather_suitability=weather or ["warm", "cool"],
        free_text_tags=tags or [],
        is_user_confirmed=confirmed,
        is_active=active,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    session.add(item)
    session.flush()
    refresh_retrieval_document(session, item)
    return item


def _add_media(
    session: Session,
    *,
    media_id: str,
    item_id: str,
    user_id: str,
    role: ItemMediaRole = ItemMediaRole.PRIMARY,
) -> MediaAsset:
    asset = MediaAsset(
        id=media_id,
        user_id=user_id,
        kind=MediaKind.ORIGINAL,
        bucket="wardrobe-private",
        object_key=f"items/{media_id}.jpg",
        mime_type="image/jpeg",
        size_bytes=1024,
        width=800,
        height=600,
        sha256="a" * 64,
    )
    session.add(asset)
    session.flush()
    item_media = ItemMedia(
        wardrobe_item_id=item_id,
        media_asset_id=media_id,
        user_id=user_id,
        role=role,
    )
    session.add(item_media)
    session.flush()
    return asset


def test_wardrobe_agent_retrieval_and_slot_pooling(
    migrated_database: tuple[object, object],
) -> None:
    """Verify Wardrobe Agent retrieves candidates into 6 canonical slots."""
    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white")
        _add_item(session, item_id="top-02", user_id=user_id, category=WardrobeCategory.TOP, sub_category="shirt", color="navy")
        _add_item(session, item_id="bot-01", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="navy")
        _add_item(session, item_id="dress-01", user_id=user_id, category=WardrobeCategory.DRESS, sub_category="floral dress", color="blue")
        _add_item(session, item_id="shoe-01", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")
        _add_item(session, item_id="outer-01", user_id=user_id, category=WardrobeCategory.OUTERWEAR, sub_category="jacket", color="beige")
        _add_item(session, item_id="acc-01", user_id=user_id, category=WardrobeCategory.ACCESSORY, sub_category="belt", color="brown")
        session.commit()

        context = StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[2, 3],
        )

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    assert set(candidate_pool.keys()) == {
        "tops",
        "bottoms",
        "dresses",
        "footwear",
        "outerwear",
        "accessories",
    }
    assert len(candidate_pool["tops"]) == 2
    assert len(candidate_pool["bottoms"]) == 1
    assert len(candidate_pool["dresses"]) == 1
    assert len(candidate_pool["footwear"]) == 1
    assert len(candidate_pool["outerwear"]) == 1
    assert len(candidate_pool["accessories"]) == 1

    top_slot = candidate_pool["tops"][0]
    assert top_slot.slot_role == OutfitSlotRole.TOP
    assert top_slot.category == WardrobeCategory.TOP
    assert top_slot.primary_color in ("white", "navy")


def test_wardrobe_agent_bounded_pool_limit(
    migrated_database: tuple[object, object],
) -> None:
    """Verify slots are capped at a maximum of 15 items."""
    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        # Add 20 tops
        for i in range(20):
            _add_item(
                session,
                item_id=f"top-{i:02d}",
                user_id=user_id,
                category=WardrobeCategory.TOP,
                sub_category="t-shirt",
                color="white",
            )
        session.commit()

        context = StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[2, 3],
        )

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    assert len(candidate_pool["tops"]) == 15  # Capped at 15 items


def test_wardrobe_agent_empty_wardrobe_error(
    migrated_database: tuple[object, object],
) -> None:
    """Verify empty wardrobe returns WARDROBE_EMPTY error and Vietnamese message."""
    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.commit()

        context = StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[2, 3],
        )

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == [EMPTY_WARDROBE_ERROR]
    assert EMPTY_WARDROBE_WARNING in warnings
    assert all(len(items) == 0 for items in candidate_pool.values())


def test_wardrobe_agent_ownership_and_active_invariant(
    migrated_database: tuple[object, object],
) -> None:
    """Verify Invariant 1: Only active, confirmed items owned by user_id are returned (zero hallucination)."""
    _, engine = migrated_database
    user_a = str(uuid4())
    user_b = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_a))
        session.add(User(id=user_b))
        session.flush()

        _add_item(session, item_id="valid-top", user_id=user_a, category=WardrobeCategory.TOP)
        _add_item(session, item_id="other-user-top", user_id=user_b, category=WardrobeCategory.TOP)
        _add_item(session, item_id="inactive-top", user_id=user_a, category=WardrobeCategory.TOP, active=False)
        _add_item(session, item_id="unconfirmed-top", user_id=user_a, category=WardrobeCategory.TOP, confirmed=False)
        _add_item(session, item_id="deleted-top", user_id=user_a, category=WardrobeCategory.TOP, deleted=True)
        session.commit()

        context = StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[2, 3],
        )

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_a, context)

    assert errors == []
    top_ids = [slot.item_id for slot in candidate_pool["tops"]]
    assert top_ids == ["valid-top"]


def test_wardrobe_agent_media_attachment(
    migrated_database: tuple[object, object],
) -> None:
    """Verify primary image media URL is attached to OutfitItemSlot."""
    _, engine = migrated_database
    user_id = str(uuid4())
    media_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="polo-item", user_id=user_id, category=WardrobeCategory.TOP)
        _add_media(session, media_id=media_id, item_id="polo-item", user_id=user_id)
        session.commit()

        context = StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[2, 3],
        )

        candidate_pool, _, _ = retrieve_candidate_pool(session, user_id, context)

    assert len(candidate_pool["tops"]) == 1
    assert candidate_pool["tops"][0].image_url == f"/api/v1/media/{media_id}"


def test_wardrobe_agent_node_execution(
    migrated_database: tuple[object, object],
) -> None:
    """Verify wardrobe_agent_node function handles LangGraph state."""
    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        _add_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP)
        session.commit()

        state: StylistGraphState = {
            "request_id": "req-001",
            "user_id": user_id,
            "user_query": "Tối nay đi cafe với bạn",
            "context": StylistContext(
                occasion="cafe",
                time_of_day="evening",
                weather_condition="cool",
                target_formality_range=[2, 3],
                needs_clarification=False,
            ),
        }

        update = wardrobe_agent_node(state, session=session)
        assert "candidate_pool" in update
        assert len(update["candidate_pool"]["tops"]) == 1

        # Test case: needs_clarification is True -> skips retrieval
        clarification_state: StylistGraphState = {
            "request_id": "req-002",
            "user_id": user_id,
            "user_query": "Mặc gì bây giờ?",
            "context": StylistContext(
                occasion="casual",
                time_of_day="morning",
                weather_condition="warm",
                needs_clarification=True,
                clarification_question="Bạn đi đâu?",
            ),
        }
        clarification_update = wardrobe_agent_node(clarification_state, session=session)
        assert all(len(slots) == 0 for slots in clarification_update["candidate_pool"].values())


def test_wardrobe_agent_bilingual_constraints_and_localized_names(
    migrated_database: tuple[object, object],
) -> None:
    """Verify bilingual mapping bridges Vietnamese constraints to English DB fields, and names are localized."""
    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="black-polo", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="black")
        _add_item(session, item_id="white-polo", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white")
        session.commit()

        # Vietnamese constraints: avoid black, require polo
        context = StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[2, 3],
            must_have=["áo polo"],
            must_avoid=["màu đen"],
        )

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    top_ids = [slot.item_id for slot in candidate_pool["tops"]]
    assert "white-polo" in top_ids
    assert "black-polo" not in top_ids

    # Verify localized Vietnamese item name
    white_polo_slot = candidate_pool["tops"][0]
    assert white_polo_slot.name == "Áo polo trắng"


def test_wardrobe_agent_missing_mandatory_slots_warning(
    migrated_database: tuple[object, object],
) -> None:
    """Verify pre-flight feasibility check emits warning when mandatory slots are missing."""
    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        # User only has top and bottom, NO footwear
        _add_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP)
        _add_item(session, item_id="bot-01", user_id=user_id, category=WardrobeCategory.BOTTOM)
        session.commit()

        context = StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[2, 3],
        )

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    # Should warn about missing mandatory footwear slot
    assert any("giày/dép" in w for w in warnings)


def test_wardrobe_agent_vibe_keywords_full_text(
    migrated_database: tuple[object, object],
) -> None:
    """Verify vibe_keywords activate full-text retrieval query."""
    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="vibe-item", user_id=user_id, category=WardrobeCategory.TOP, tags=["lịch sự nhẹ"])
        _add_item(session, item_id="plain-item", user_id=user_id, category=WardrobeCategory.TOP)
        session.commit()

        context = StylistContext(
            occasion="cafe",
            time_of_day="evening",
            weather_condition="cool",
            target_formality_range=[2, 3],
            vibe_keywords=["lịch sự nhẹ"],
        )

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    # Both items retrieved, but vibe-item ranks first due to full-text score
    assert candidate_pool["tops"][0].item_id == "vibe-item"


def test_wardrobe_agent_pipeline_with_extracted_context(
    migrated_database: tuple[object, object],
) -> None:
    """Verify that Context Agent output flows directly into Wardrobe Agent successfully."""
    from app.agents.context_agent import extract_context

    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="white-polo", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white")
        _add_item(session, item_id="black-polo", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="black")
        _add_item(session, item_id="navy-chinos", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="navy")
        _add_item(session, item_id="white-sneakers", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")
        session.commit()

        # Extract context directly from realistic Vietnamese query
        query = "Đi cafe tối nay, phải mặc áo polo và giày sneaker, không mặc màu đen"
        context = extract_context(query)

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    top_ids = [slot.item_id for slot in candidate_pool["tops"]]
    assert "white-polo" in top_ids
    assert "black-polo" not in top_ids
    assert len(candidate_pool["bottoms"]) == 1
    assert candidate_pool["bottoms"][0].item_id == "navy-chinos"
    assert len(candidate_pool["footwear"]) == 1
    assert candidate_pool["footwear"][0].item_id == "white-sneakers"


def test_wardrobe_agent_outerwear_and_dress_category_pipeline(
    migrated_database: tuple[object, object],
) -> None:
    """Verify that áo blazer is categorized as outerwear (not top), váy đầm as dress, and áo khoác can be excluded."""
    from app.agents.context_agent import extract_context

    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="white-polo", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white")
        _add_item(session, item_id="navy-blazer", user_id=user_id, category=WardrobeCategory.OUTERWEAR, sub_category="blazer", color="navy")
        _add_item(session, item_id="beige-jacket", user_id=user_id, category=WardrobeCategory.OUTERWEAR, sub_category="jacket", color="beige")
        _add_item(session, item_id="floral-dress", user_id=user_id, category=WardrobeCategory.DRESS, sub_category="floral dress", color="blue")
        _add_item(session, item_id="navy-chinos", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="navy")
        _add_item(session, item_id="white-sneakers", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")
        session.commit()

        # Query requiring blazer and dress, avoiding jacket
        query = "Đi làm ngày mai, phải mặc áo blazer và váy đầm, không mặc áo khoác"
        context = extract_context(query)

        assert "áo blazer" in context.must_have
        assert "váy đầm" in context.must_have
        assert "áo khoác" in context.must_avoid

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    # Outerwear should contain navy-blazer and NOT beige-jacket
    outer_ids = [slot.item_id for slot in candidate_pool["outerwear"]]
    assert "navy-blazer" in outer_ids
    assert "beige-jacket" not in outer_ids

    # Dress pool should contain floral-dress
    dress_ids = [slot.item_id for slot in candidate_pool["dresses"]]
    assert "floral-dress" in dress_ids

    # Tops should not be constrained by blazer
    assert len(candidate_pool["tops"]) == 1
    assert candidate_pool["tops"][0].item_id == "white-polo"


def test_wardrobe_agent_mandatory_color_hint_prioritization(
    migrated_database: tuple[object, object],
) -> None:
    """Verify that general must_have color constraint prioritizes matching colors across slots without causing empty pools."""
    from app.agents.context_agent import extract_context

    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="white-polo", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white")
        _add_item(session, item_id="navy-shirt", user_id=user_id, category=WardrobeCategory.TOP, sub_category="shirt", color="navy")
        _add_item(session, item_id="navy-chinos", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="navy")
        _add_item(session, item_id="white-sneakers", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")
        session.commit()

        # General color requirement without specific garment
        query = "Đi cafe tối nay, phải mặc màu trắng"
        context = extract_context(query)
        assert "màu trắng" in context.must_have

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    # In tops: white-polo should rank first due to color match
    assert candidate_pool["tops"][0].item_id == "white-polo"
    # In bottoms: navy-chinos should still be retrieved (pool not empty)
    assert len(candidate_pool["bottoms"]) == 1
    assert candidate_pool["bottoms"][0].item_id == "navy-chinos"
    # In footwear: white-sneakers retrieved
    assert len(candidate_pool["footwear"]) == 1
    assert candidate_pool["footwear"][0].item_id == "white-sneakers"


def test_wardrobe_agent_category_only_must_have_preserves_pool(
    migrated_database: tuple[object, object],
) -> None:
    """Verify that generic terms like 'phải mặc giày' or 'phải mặc áo' do not wipe out candidate pools."""
    from app.agents.context_agent import extract_context

    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="sneaker-1", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")
        _add_item(session, item_id="polo-1", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="navy")
        _add_item(session, item_id="chinos-1", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="beige")
        session.commit()

        query = "Đi làm ngày mai, phải mặc giày và phải mặc áo"
        context = extract_context(query)

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    # Both pools must have items, NOT empty
    assert len(candidate_pool["footwear"]) == 1
    assert candidate_pool["footwear"][0].item_id == "sneaker-1"
    assert len(candidate_pool["tops"]) == 1
    assert candidate_pool["tops"][0].item_id == "polo-1"


def test_wardrobe_agent_compound_avoid_excludes_only_specific_garment_color(
    migrated_database: tuple[object, object],
) -> None:
    """Verify 'không mặc áo polo đen' only excludes black polo, preserving white polo and black pants."""
    from app.agents.context_agent import extract_context

    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="white-polo", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white")
        _add_item(session, item_id="black-polo", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="black")
        _add_item(session, item_id="black-pants", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="black")
        _add_item(session, item_id="white-sneakers", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")
        session.commit()

        query = "Đi làm ngày mai, không mặc áo polo đen"
        context = extract_context(query)

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    top_ids = [slot.item_id for slot in candidate_pool["tops"]]
    # black-polo must be excluded, white-polo must be preserved
    assert "black-polo" not in top_ids
    assert "white-polo" in top_ids

    # black-pants must NOT be excluded by an áo polo constraint
    bottom_ids = [slot.item_id for slot in candidate_pool["bottoms"]]
    assert "black-pants" in bottom_ids


def test_wardrobe_agent_vest_mapped_to_outerwear_and_leather_shoes(
    migrated_database: tuple[object, object],
) -> None:
    """Verify 'áo vest' is retrieved into outerwear slot and 'giày da' matches leather footwear."""
    from app.agents.context_agent import extract_context

    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="blazer-vest", user_id=user_id, category=WardrobeCategory.OUTERWEAR, sub_category="blazer", color="black", formality=4)
        _add_item(session, item_id="leather-oxford", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="oxford", color="brown", material="leather", formality=4)
        _add_item(session, item_id="white-shirt", user_id=user_id, category=WardrobeCategory.TOP, sub_category="shirt", color="white", formality=4)
        _add_item(session, item_id="black-trousers", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="black", formality=4)
        session.commit()

        query = "Đi tiệc tối nay, phải mặc áo vest và giày da"
        context = extract_context(query)

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    assert errors == []
    outerwear_ids = [slot.item_id for slot in candidate_pool["outerwear"]]
    assert "blazer-vest" in outerwear_ids

    footwear_ids = [slot.item_id for slot in candidate_pool["footwear"]]
    assert "leather-oxford" in footwear_ids


def test_wardrobe_agent_must_have_color_warning_when_missing(
    migrated_database: tuple[object, object],
) -> None:
    """Verify that if user explicitly requires a color not in wardrobe, a clear UX warning is emitted."""
    from app.agents.context_agent import extract_context

    _, engine = migrated_database
    user_id = str(uuid4())

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_item(session, item_id="black-shirt", user_id=user_id, category=WardrobeCategory.TOP, sub_category="shirt", color="black")
        _add_item(session, item_id="black-pants", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="black")
        _add_item(session, item_id="black-sneakers", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="black")
        session.commit()

        query = "Đi cafe tối nay, phải mặc màu trắng"
        context = extract_context(query)

        candidate_pool, errors, warnings = retrieve_candidate_pool(session, user_id, context)

    # Must emit a warning informing the user that white items are missing
    assert any("trắng" in w and "không có" in w for w in warnings)
