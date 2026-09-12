from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
import pytest
from sqlmodel import Session, select

from app.agents.coordinator import COORDINATOR_RULE_VERSION
from app.agents.state import StylistGraphState
from app.agents.stylist_graph import (
    create_stylist_graph,
    execute_stylist_recommendation,
)
from app.agents.wardrobe_agent import EMPTY_WARDROBE_ERROR
from app.agents.fashion_agent import NO_COMPLETE_OUTFIT_ERROR
from app.models.entities import (
    OutfitItem,
    OutfitRecommendation,
    User,
    WardrobeCategory,
    WardrobeItem,
)
from app.services.retrieval_document_service import refresh_retrieval_document


# ============================================================================
# TEST HELPERS
# ============================================================================

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
) -> WardrobeItem:
    """Helper to seed WardrobeItem and its searchable retrieval document."""
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
    return item


def _fixed_clock() -> datetime:
    """Deterministic fixed clock returning 2026-09-12 10:00:00 UTC."""
    return datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)


# ============================================================================
# 1. HAPPY PATH, FIXED SEQUENCE
# ============================================================================

def test_stylist_graph_happy_path_fixed_sequence(
    migrated_database: tuple[object, object],
) -> None:
    """Verify happy path executes Context -> Wardrobe -> Fashion -> Personalization -> Coordinator.

    Checks:
    - Normalized context.
    - Candidate pool, evaluated outfits, and ranked outfits are non-empty.
    - Ranks strictly consecutive [1..n] where 1 <= n <= 3.
    - Grounded Vietnamese explanation populated.
    - recommendation_ids matches outfit_ids and grounding_validated is True.
    - Database contains persisted OutfitRecommendation and OutfitItem records owned by user.
    - Graph topology has no bypass to later agents.
    """
    _, engine = migrated_database
    user_id = f"user_happy_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        # Seed full wardrobe for user
        _add_wardrobe_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white", style="smart_casual")
        _add_wardrobe_item(session, item_id="bot-01", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="navy", style="smart_casual")
        _add_wardrobe_item(session, item_id="shoe-01", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white", style="smart_casual")
        _add_wardrobe_item(session, item_id="outer-01", user_id=user_id, category=WardrobeCategory.OUTERWEAR, sub_category="jacket", color="beige", style="smart_casual")
        _add_wardrobe_item(session, item_id="acc-01", user_id=user_id, category=WardrobeCategory.ACCESSORY, sub_category="belt", color="brown", style="smart_casual")
        session.commit()

        # Check compiled graph topology
        graph = create_stylist_graph(session=session, clock=_fixed_clock)
        nodes = set(graph.nodes.keys())
        assert {"context", "wardrobe", "fashion", "personalization", "coordinator"}.issubset(nodes)

        # Strictly assert edge topology: only sequential next node or __end__, no bypass/skip
        edges = {(e.source, e.target) for e in graph.get_graph().edges}
        assert edges == {
            ("__start__", "context"),
            ("context", "wardrobe"),
            ("context", "__end__"),
            ("wardrobe", "fashion"),
            ("wardrobe", "__end__"),
            ("fashion", "personalization"),
            ("fashion", "__end__"),
            ("personalization", "coordinator"),
            ("personalization", "__end__"),
            ("coordinator", "__end__"),
        }

        initial_state: StylistGraphState = {
            "request_id": f"req_{uuid4().hex[:8]}",
            "user_id": user_id,
            "user_query": "Tối nay tôi đi cafe với bạn, trời mát, nên mặc gì?",
            "location": "Hà Nội",
        }

        result = execute_stylist_recommendation(
            initial_state,
            session=session,
            clock=_fixed_clock,
        )

        # 1. State assertions
        assert result["grounding_validated"] is True
        assert len(result["recommendation_ids"]) >= 1
        assert len(result["ranked_outfits"]) == len(result["recommendation_ids"])
        assert result["context"] is not None
        assert result["context"].occasion == "cafe"
        assert result["context"].weather_condition == "cool"
        assert result["context"].needs_clarification is False

        # 2. Output bounds and ranking
        assert 1 <= len(result["ranked_outfits"]) <= 3
        ranks = [o.rank for o in result["ranked_outfits"]]
        assert ranks == list(range(1, len(result["ranked_outfits"]) + 1))

        for outfit in result["ranked_outfits"]:
            assert outfit.outfit_id is not None
            assert outfit.outfit_id in result["recommendation_ids"]
            assert outfit.explanation_vi != ""
            assert len(outfit.items) >= 3

        # 3. Database persistence assertions
        recs = session.exec(
            select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)
        ).all()
        assert len(recs) == len(result["recommendation_ids"])
        rec_ids = {r.id for r in recs}
        assert rec_ids == set(result["recommendation_ids"])

        for rec in recs:
            assert rec.rule_version == COORDINATOR_RULE_VERSION
            assert rec.user_query == initial_state["user_query"]
            assert rec.user_id == user_id

        # Verify OutfitItem ownership and links
        outfit_items = session.exec(
            select(OutfitItem).where(OutfitItem.user_id == user_id)
        ).all()
        assert len(outfit_items) >= 3
        for oi in outfit_items:
            assert oi.outfit_id in rec_ids
            assert oi.user_id == user_id


# ============================================================================
# 2. CLARIFICATION EARLY TERMINATION
# ============================================================================

def test_stylist_graph_clarification_early_termination(
    migrated_database: tuple[object, object],
) -> None:
    """Ambiguous query ('Mặc gì?') terminates immediately after Context Agent.

    Checks:
    - needs_clarification is True with clarification_question.
    - Candidate pool has empty lists.
    - evaluated_outfits, ranked_outfits, recommendation_ids are empty.
    - grounding_validated is False.
    - Zero OutfitRecommendation / OutfitItem records persisted in DB.
    """
    _, engine = migrated_database
    user_id = f"user_clar_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        # Even with items in wardrobe, clarification stops before wardrobe retrieval
        _add_wardrobe_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP)
        session.commit()

        initial_state: StylistGraphState = {
            "request_id": "req-clarify-1",
            "user_id": user_id,
            "user_query": "Mặc gì?",
        }

        result = execute_stylist_recommendation(
            initial_state,
            session=session,
            clock=_fixed_clock,
        )

        assert result["context"] is not None
        assert result["context"].needs_clarification is True
        assert result["context"].clarification_question is not None

        # Short-circuit assertions
        assert result["grounding_validated"] is False
        assert result["recommendation_ids"] == []
        assert result["ranked_outfits"] == []
        assert result["evaluated_outfits"] == []
        assert result["feedback_prompt_eligible"] is False
        assert result["feedback_target_outfit_id"] is None
        for slot in ["tops", "bottoms", "dresses", "footwear", "outerwear", "accessories"]:
            assert result["candidate_pool"][slot] == []

        # Zero DB records created
        db_recs = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)).all()
        assert len(db_recs) == 0
        db_items = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_id)).all()
        assert len(db_items) == 0


# ============================================================================
# 3. EMPTY WARDROBE EARLY TERMINATION
# ============================================================================

def test_stylist_graph_empty_wardrobe_early_termination(
    migrated_database: tuple[object, object],
) -> None:
    """User with 0 wardrobe items terminates with WARDROBE_EMPTY after Wardrobe Agent."""
    _, engine = migrated_database
    user_id = f"user_empty_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.commit()

        initial_state: StylistGraphState = {
            "request_id": "req-empty-1",
            "user_id": user_id,
            "user_query": "Tối nay tôi đi ăn tiệc, nên mặc gì?",
        }

        result = execute_stylist_recommendation(
            initial_state,
            session=session,
            clock=_fixed_clock,
        )

        assert EMPTY_WARDROBE_ERROR in result["errors"]
        assert any("chưa có trang phục" in w for w in result["warnings"])
        assert result["grounding_validated"] is False
        assert result["recommendation_ids"] == []
        assert result["ranked_outfits"] == []
        assert result["evaluated_outfits"] == []
        assert result["feedback_prompt_eligible"] is False
        assert result["feedback_target_outfit_id"] is None
        for slot in ["tops", "bottoms", "dresses", "footwear", "outerwear", "accessories"]:
            assert result["candidate_pool"][slot] == []

        # Zero DB records created
        db_recs = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)).all()
        assert len(db_recs) == 0
        db_items = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_id)).all()
        assert len(db_items) == 0


# ============================================================================
# 4. INCOMPLETE WARDROBE / NO-COMPLETE-OUTFIT TERMINATION
# ============================================================================

def test_stylist_graph_incomplete_wardrobe_early_termination(
    migrated_database: tuple[object, object],
) -> None:
    """User has only tops (missing bottoms, dresses, footwear) -> NO_COMPLETE_OUTFIT."""
    _, engine = migrated_database
    user_id = f"user_inc_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        # Seed only tops
        _add_wardrobe_item(session, item_id="top-01", user_id=user_id, category=WardrobeCategory.TOP)
        _add_wardrobe_item(session, item_id="top-02", user_id=user_id, category=WardrobeCategory.TOP)
        session.commit()

        initial_state: StylistGraphState = {
            "request_id": "req-inc-1",
            "user_id": user_id,
            "user_query": "Đi cafe sáng mai mặc gì",
        }

        result = execute_stylist_recommendation(
            initial_state,
            session=session,
            clock=_fixed_clock,
        )

        assert NO_COMPLETE_OUTFIT_ERROR in result["errors"]
        assert result["grounding_validated"] is False
        assert result["recommendation_ids"] == []
        assert result["evaluated_outfits"] == []
        assert result["ranked_outfits"] == []
        assert result["feedback_prompt_eligible"] is False
        assert result["feedback_target_outfit_id"] is None

        # Zero DB records created
        db_recs = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)).all()
        assert len(db_recs) == 0
        db_items = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_id)).all()
        assert len(db_items) == 0


# ============================================================================
# 5. CROSS-USER DATA ISOLATION
# ============================================================================

def test_stylist_graph_cross_user_isolation(
    migrated_database: tuple[object, object],
) -> None:
    """User A cannot receive User B's wardrobe items in candidate pool or recommendations."""
    _, engine = migrated_database
    user_a = f"user_iso_a_{uuid4().hex[:8]}"
    user_b = f"user_iso_b_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add_all([User(id=user_a), User(id=user_b)])
        session.flush()

        # Seed User A wardrobe
        _add_wardrobe_item(session, item_id="top-a", user_id=user_a, category=WardrobeCategory.TOP, sub_category="polo", color="white")
        _add_wardrobe_item(session, item_id="bot-a", user_id=user_a, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="navy")
        _add_wardrobe_item(session, item_id="shoe-a", user_id=user_a, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")

        # Seed User B wardrobe with high-scoring items
        _add_wardrobe_item(session, item_id="top-b-luxury", user_id=user_b, category=WardrobeCategory.TOP, sub_category="blazer", color="black")
        _add_wardrobe_item(session, item_id="bot-b-luxury", user_id=user_b, category=WardrobeCategory.BOTTOM, sub_category="trousers", color="black")
        _add_wardrobe_item(session, item_id="shoe-b-luxury", user_id=user_b, category=WardrobeCategory.FOOTWEAR, sub_category="oxford", color="black")
        session.commit()

        initial_state: StylistGraphState = {
            "request_id": "req-iso-1",
            "user_id": user_a,
            "user_query": "Đi cafe sáng nay, thời tiết mát mẻ",
        }

        result = execute_stylist_recommendation(
            initial_state,
            session=session,
            clock=_fixed_clock,
        )

        assert result["grounding_validated"] is True

        # Assert no candidate item belongs to User B
        all_pool_items = [item for slots in result["candidate_pool"].values() for item in slots]
        assert not any("user_b" in item.item_id or "-b-" in item.item_id for item in all_pool_items)

        # Assert ranked outfit items are exclusively User A
        for outfit in result["ranked_outfits"]:
            for item in outfit.items:
                assert "-b-" not in item.item_id
                assert item.item_id in {"top-a", "bot-a", "shoe-a"}

        # Assert persisted records are exclusively User A
        outfit_items = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_a)).all()
        for oi in outfit_items:
            assert oi.wardrobe_item_id in {"top-a", "bot-a", "shoe-a"}


# ============================================================================
# 6. FRESH-STATE AND FIELD-OWNERSHIP BEHAVIOR
# ============================================================================

def test_stylist_graph_fresh_state_clears_stale_inputs(
    migrated_database: tuple[object, object],
) -> None:
    """Stale caller-supplied outputs are stripped before graph execution."""
    _, engine = migrated_database
    user_id = f"user_fresh_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.commit()

        # Caller provides an ambiguous query with deliberately dirty/stale derived state
        stale_state: StylistGraphState = {
            "request_id": "req-stale-1",
            "user_id": user_id,
            "user_query": "Mặc gì?",
            "location": "Đà Nẵng",
            "reference_time": datetime(2026, 9, 12, 8, 30, tzinfo=timezone.utc),
            "recommendation_ids": ["stale-rec-id-999"],
            "grounding_validated": True,
            "feedback_prompt_eligible": True,
            "feedback_target_outfit_id": "stale-outfit-id",
            "errors": ["STALE_ERROR"],
            "warnings": ["STALE_WARNING"],
            "candidate_pool": {
                "tops": [{"item_id": "stale_top"}],  # type: ignore[dict-item]
            },
            "evaluated_outfits": [{"fake": "evaluated"}],  # type: ignore[list-item]
            "ranked_outfits": [{"fake": "ranked"}],        # type: ignore[list-item]
        }

        result = execute_stylist_recommendation(
            stale_state,
            session=session,
            clock=_fixed_clock,
        )

        # Clarification triggers, stale data must be completely gone
        assert result["context"] is not None
        assert result["context"].needs_clarification is True
        assert result["grounding_validated"] is False
        assert result["recommendation_ids"] == []
        assert result["ranked_outfits"] == []
        assert result["evaluated_outfits"] == []
        assert result["feedback_prompt_eligible"] is False
        assert result["feedback_target_outfit_id"] is None
        for slot in ["tops", "bottoms", "dresses", "footwear", "outerwear", "accessories"]:
            assert result["candidate_pool"][slot] == []
        assert "STALE_ERROR" not in result["errors"]
        assert "STALE_WARNING" not in result["warnings"]

        # Request-owned fields must be preserved
        assert result["request_id"] == "req-stale-1"
        assert result["user_id"] == user_id
        assert result["user_query"] == "Mặc gì?"
        assert result["location"] == "Đà Nẵng"
        assert result["reference_time"] == datetime(2026, 9, 12, 8, 30, tzinfo=timezone.utc)

        # Zero DB records created
        db_recs = session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)).all()
        assert len(db_recs) == 0
        db_items = session.exec(select(OutfitItem).where(OutfitItem.user_id == user_id)).all()
        assert len(db_items) == 0


# ============================================================================
# 7. VIETNAM TIMEZONE DATE BOUNDARY
# ============================================================================

def test_stylist_graph_vietnam_timezone_date_boundary(
    migrated_database: tuple[object, object],
) -> None:
    """Verify Context Agent calculates today/tomorrow relative to Vietnam local time (UTC+7).

    Case:
    - 2026-09-12 18:30:00 UTC corresponds to 2026-09-13 01:30:00 in Vietnam (UTC+7).
    - Query: "Sáng mai đi làm, mặc gì?" (Going to work tomorrow morning).
    - In Vietnam time, today is 2026-09-13, so "ngày mai" must be 2026-09-14.
    - If mistakenly using UTC date (2026-09-12), "ngày mai" would incorrectly be 2026-09-13.
    """
    _, engine = migrated_database
    user_id = f"user_tz_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_wardrobe_item(session, item_id="top-tz-01", user_id=user_id, category=WardrobeCategory.TOP, sub_category="shirt", color="white")
        _add_wardrobe_item(session, item_id="bot-tz-01", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="trousers", color="black")
        _add_wardrobe_item(session, item_id="shoe-tz-01", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="oxford", color="black")
        session.commit()

        # 18:30 UTC on Sep 12 -> 01:30 UTC+7 on Sep 13
        ref_time_late_utc = datetime(2026, 9, 12, 18, 30, 0, tzinfo=timezone.utc)

        initial_state: StylistGraphState = {
            "request_id": "req-tz-boundary",
            "user_id": user_id,
            "user_query": "Sáng mai đi làm, mặc gì?",
            "reference_time": ref_time_late_utc,
        }

        result = execute_stylist_recommendation(
            initial_state,
            session=session,
            clock=lambda: ref_time_late_utc,
        )

        assert result["context"] is not None
        assert result["context"].event_date == "2026-09-14"
        assert result["reference_time"] == ref_time_late_utc
        assert result["grounding_validated"] is True


# ============================================================================
# 8. DIRECT GRAPH INVOKE DETERMINISTIC CLOCK
# ============================================================================

def test_stylist_graph_direct_invoke_clock_determinism(
    migrated_database: tuple[object, object],
) -> None:
    """Verify create_stylist_graph propagates injected clock to all nodes when called directly."""
    _, engine = migrated_database
    user_id = f"user_direct_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()

        _add_wardrobe_item(session, item_id="top-d-01", user_id=user_id, category=WardrobeCategory.TOP, sub_category="polo", color="white")
        _add_wardrobe_item(session, item_id="bot-d-01", user_id=user_id, category=WardrobeCategory.BOTTOM, sub_category="chinos", color="navy")
        _add_wardrobe_item(session, item_id="shoe-d-01", user_id=user_id, category=WardrobeCategory.FOOTWEAR, sub_category="sneakers", color="white")
        session.commit()

        # Compile graph directly with injected clock
        graph = create_stylist_graph(session=session, clock=_fixed_clock)

        # Raw state with no reference_time provided by caller
        raw_state: StylistGraphState = {
            "request_id": "req-direct-invoke",
            "user_id": user_id,
            "user_query": "Đi cafe sáng nay, thời tiết mát mẻ",
        }

        result = graph.invoke(raw_state)

        # Ensure reference_time was generated by Context and propagated throughout shared state
        assert result["reference_time"] == _fixed_clock()
        assert result["grounding_validated"] is True
        assert len(result["recommendation_ids"]) >= 1
        assert len(result["ranked_outfits"]) == len(result["recommendation_ids"])


def test_stylist_graph_rejects_alternate_branch_that_violates_must_have(
    migrated_database: tuple[object, object],
) -> None:
    """A required polo cannot be bypassed by returning a dress outfit."""
    _, engine = migrated_database
    user_id = f"user_required_{uuid4().hex[:8]}"

    with Session(engine) as session:
        session.add(User(id=user_id))
        session.flush()
        _add_wardrobe_item(
            session,
            item_id="dress-required-01",
            user_id=user_id,
            category=WardrobeCategory.DRESS,
            sub_category="dress",
            color="black",
        )
        _add_wardrobe_item(
            session,
            item_id="shoe-required-01",
            user_id=user_id,
            category=WardrobeCategory.FOOTWEAR,
            sub_category="sneakers",
            color="black",
        )
        session.commit()

        result = execute_stylist_recommendation(
            {
                "request_id": "req-required-polo",
                "user_id": user_id,
                "user_query": "Đi cafe tối nay, phải mặc áo polo",
            },
            session=session,
            clock=_fixed_clock,
        )

        assert result["errors"] == ["NO_COMPLETE_OUTFIT"]
        assert result["recommendation_ids"] == []
        assert result["grounding_validated"] is False
        assert session.exec(
            select(OutfitRecommendation).where(OutfitRecommendation.user_id == user_id)
        ).all() == []
