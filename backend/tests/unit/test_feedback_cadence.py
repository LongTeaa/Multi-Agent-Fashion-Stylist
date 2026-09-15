from __future__ import annotations

import uuid
from datetime import datetime, timezone
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.entities import (
    FeedbackPromptState,
    FeedbackSuppressedSession,
    OutfitRecommendation,
    Rating,
    RatingSource,
    User,
)
from app.services.feedback_cadence_service import FeedbackCadenceService


@pytest.fixture
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _create_user(session: Session, user_id: str | None = None) -> User:
    uid = user_id or str(uuid.uuid4())
    user = User(id=uid, email=f"{uid}@example.com", name="Test User")
    session.add(user)
    session.commit()
    return user


def _create_outfit(session: Session, user_id: str, outfit_id: str | None = None, rank: int = 1) -> OutfitRecommendation:
    oid = outfit_id or str(uuid.uuid4())
    outfit = OutfitRecommendation(
        id=oid,
        user_id=user_id,
        request_id=str(uuid.uuid4()),
        user_query="test query",
        context_snapshot={"occasion": "casual"},
        explanation_vi="outfit test",
        fashion_score=0.8,
        personalization_score=0.8,
        composite_score=0.8,
        rank=rank,
        is_bookmarked=False,
        rule_version="v1",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(outfit)
    session.commit()
    return outfit


def test_cadence_exact_threshold_5_with_seeded_chooser(db_session: Session) -> None:
    """INVARIANT: Seeded chooser=5 triggers prompt eligibility on exactly the 5th eligible outfit."""
    fixed_time = datetime(2026, 9, 15, 12, 0, 0, tzinfo=timezone.utc)
    service = FeedbackCadenceService(
        clock=lambda: fixed_time,
        threshold_chooser=lambda: 5,
    )
    user = _create_user(db_session)
    user_id = user.id

    outfits = [_create_outfit(db_session, user_id, rank=1) for _ in range(5)]

    # 1. First 2 outfits -> count is 2
    eligible, target = service.process_chat_recommendations(
        session=db_session,
        user_id=user_id,
        new_outfit_ids=[outfits[0].id, outfits[1].id],
    )
    assert eligible is False
    assert target is None

    state = db_session.get(FeedbackPromptState, user_id)
    assert state.eligible_count_since_prompt == 2
    assert state.next_threshold == 5

    # 2. Next 2 outfits -> count is 4
    eligible, target = service.process_chat_recommendations(
        session=db_session,
        user_id=user_id,
        new_outfit_ids=[outfits[2].id, outfits[3].id],
    )
    assert eligible is False
    assert target is None

    state = db_session.get(FeedbackPromptState, user_id)
    assert state.eligible_count_since_prompt == 4

    # 3. 5th outfit -> count reaches 5 >= 5 -> prompt triggers!
    eligible, target = service.process_chat_recommendations(
        session=db_session,
        user_id=user_id,
        new_outfit_ids=[outfits[4].id],
    )
    assert eligible is True
    assert target == outfits[4].id

    # Post-prompt state check
    state = db_session.get(FeedbackPromptState, user_id)
    assert state.eligible_count_since_prompt == 0
    assert state.last_prompted_at.replace(tzinfo=timezone.utc) == fixed_time
    assert state.next_threshold == 5


def test_cadence_exact_threshold_10_with_seeded_chooser(db_session: Session) -> None:
    """INVARIANT: Seeded chooser=10 triggers prompt eligibility on exactly the 10th eligible outfit."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 10)
    user = _create_user(db_session)
    user_id = user.id

    outfits = [_create_outfit(db_session, user_id) for _ in range(10)]

    # 3 outfits (count=3)
    eligible, _ = service.process_chat_recommendations(db_session, user_id, [o.id for o in outfits[0:3]])
    assert eligible is False

    # 3 outfits (count=6)
    eligible, _ = service.process_chat_recommendations(db_session, user_id, [o.id for o in outfits[3:6]])
    assert eligible is False

    # 3 outfits (count=9)
    eligible, _ = service.process_chat_recommendations(db_session, user_id, [o.id for o in outfits[6:9]])
    assert eligible is False

    # 10th outfit -> triggers!
    eligible, target = service.process_chat_recommendations(db_session, user_id, [outfits[9].id])
    assert eligible is True
    assert target == outfits[9].id


def test_cadence_multi_outfit_response_accumulates_correctly(db_session: Session) -> None:
    """INVARIANT: Multi-outfit response advances count by length of outfits."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)
    outfits = [_create_outfit(db_session, user.id) for _ in range(6)]

    # Call with 3 outfits
    service.process_chat_recommendations(db_session, user.id, [o.id for o in outfits[:3]])
    state = db_session.get(FeedbackPromptState, user.id)
    assert state.eligible_count_since_prompt == 3

    # Call with next 3 outfits -> triggers (3 + 3 = 6 >= 5)
    eligible, target = service.process_chat_recommendations(db_session, user.id, [o.id for o in outfits[3:6]])
    assert eligible is True
    assert target in [o.id for o in outfits[3:6]]


def test_cadence_duplicate_ids_deduplicated(db_session: Session) -> None:
    """INVARIANT: Duplicate outfit IDs in response are deduplicated before counting."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)
    outfit1 = _create_outfit(db_session, user.id)
    outfit2 = _create_outfit(db_session, user.id)

    # Pass outfit1 twice and outfit2 once -> should count as 2, not 3
    service.process_chat_recommendations(db_session, user.id, [outfit1.id, outfit1.id, outfit2.id])
    state = db_session.get(FeedbackPromptState, user.id)
    assert state.eligible_count_since_prompt == 2


def test_cadence_empty_ids_no_op(db_session: Session) -> None:
    """INVARIANT: Empty outfit list does not advance count or change state."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)

    eligible, target = service.process_chat_recommendations(db_session, user.id, [])
    assert eligible is False
    assert target is None
    state = db_session.get(FeedbackPromptState, user.id)
    assert state is None


def test_cadence_target_highest_ranked_unrated_outfit(db_session: Session) -> None:
    """INVARIANT: Prompt target selects the highest-ranked unrated outfit."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)

    # Pre-seed 4 eligible outfits
    for _ in range(4):
        o = _create_outfit(db_session, user.id)
        service.process_chat_recommendations(db_session, user.id, [o.id])

    # Now create 2 outfits in new response: rank 1 is rated, rank 2 is unrated
    outfit_rank1 = _create_outfit(db_session, user.id, rank=1)
    outfit_rank2 = _create_outfit(db_session, user.id, rank=2)

    # User already rated outfit_rank1
    rating = Rating(
        user_id=user.id,
        outfit_id=outfit_rank1.id,
        stars=5,
        source=RatingSource.MANUAL,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(rating)
    db_session.commit()

    # Chat response with [outfit_rank1, outfit_rank2]
    eligible, target = service.process_chat_recommendations(
        db_session, user.id, [outfit_rank1.id, outfit_rank2.id]
    )
    assert eligible is True
    # Must skip rank 1 because already rated, and select rank 2!
    assert target == outfit_rank2.id


def test_cadence_all_targets_rated_no_fake_eligibility(db_session: Session) -> None:
    """INVARIANT: If all candidate outfits are already rated, do not return fake eligibility."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)

    # Pre-seed 4 eligible outfits
    for _ in range(4):
        o = _create_outfit(db_session, user.id)
        service.process_chat_recommendations(db_session, user.id, [o.id])

    # 5th outfit is created and already rated
    outfit = _create_outfit(db_session, user.id)
    db_session.add(
        Rating(
            user_id=user.id,
            outfit_id=outfit.id,
            stars=4,
            source=RatingSource.MANUAL,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    # Also rate all previous 4 outfits
    all_recs = db_session.exec(select(OutfitRecommendation).where(OutfitRecommendation.user_id == user.id)).all()
    for rec in all_recs:
        existing = db_session.exec(select(Rating).where(Rating.outfit_id == rec.id)).first()
        if not existing:
            db_session.add(Rating(user_id=user.id, outfit_id=rec.id, stars=4, source=RatingSource.MANUAL))
    db_session.commit()

    eligible, target = service.process_chat_recommendations(db_session, user.id, [outfit.id])
    # Must NOT return fake eligibility
    assert eligible is False
    assert target is None


def test_cadence_dismiss_cooldown_and_decrement(db_session: Session) -> None:
    """INVARIANT: Dismissing prompt sets cooldown of at least 3, decremented by subsequent viewed outfits."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)

    # Dismiss prompt
    dismiss_data = service.dismiss_prompt(db_session, user.id)
    assert dismiss_data.cooldown_remaining == 3
    assert dismiss_data.dismissed is True

    state = db_session.get(FeedbackPromptState, user.id)
    assert state.cooldown_remaining == 3
    assert state.eligible_count_since_prompt == 0

    # View 1 outfit -> cooldown drops to 2, eligible is False
    o1 = _create_outfit(db_session, user.id)
    eligible, _ = service.process_chat_recommendations(db_session, user.id, [o1.id])
    assert eligible is False
    state = db_session.get(FeedbackPromptState, user.id)
    assert state.cooldown_remaining == 2
    assert state.eligible_count_since_prompt == 0

    # View 2 outfits -> cooldown drops to 0, eligible is False
    o2 = _create_outfit(db_session, user.id)
    o3 = _create_outfit(db_session, user.id)
    eligible, _ = service.process_chat_recommendations(db_session, user.id, [o2.id, o3.id])
    assert eligible is False
    state = db_session.get(FeedbackPromptState, user.id)
    assert state.cooldown_remaining == 0
    assert state.eligible_count_since_prompt == 0

    # View 1 more outfit -> cooldown was 0, now eligible_count increments to 1!
    o4 = _create_outfit(db_session, user.id)
    eligible, _ = service.process_chat_recommendations(db_session, user.id, [o4.id])
    assert eligible is False
    state = db_session.get(FeedbackPromptState, user.id)
    assert state.cooldown_remaining == 0
    assert state.eligible_count_since_prompt == 1


def test_cadence_same_session_suppression(db_session: Session) -> None:
    """INVARIANT: Requests with suppressed client_session_id do not trigger prompt even at threshold."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)
    session_id = str(uuid.uuid4())

    # Record session suppression
    db_session.add(
        FeedbackSuppressedSession(
            user_id=user.id,
            client_session_id=session_id,
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    # Pre-seed 4 outfits
    for _ in range(4):
        o = _create_outfit(db_session, user.id)
        service.process_chat_recommendations(db_session, user.id, [o.id])

    # 5th outfit with suppressed session ID
    o5 = _create_outfit(db_session, user.id)
    eligible, target = service.process_chat_recommendations(
        db_session, user.id, [o5.id], client_session_id=session_id
    )
    assert eligible is False
    assert target is None

    # But with a different/unsuppressed session ID, prompt triggers!
    different_session = str(uuid.uuid4())
    eligible2, target2 = service.process_chat_recommendations(
        db_session, user.id, [o5.id], client_session_id=different_session
    )
    assert eligible2 is True
    assert target2 is not None


def test_dismiss_with_client_session_id_records_suppression(db_session: Session) -> None:
    """INVARIANT: Dismissing with client_session_id records the session in feedback_suppressed_sessions."""
    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)
    session_id = str(uuid.uuid4())

    dismiss_data = service.dismiss_prompt(db_session, user.id, client_session_id=session_id)
    assert dismiss_data.dismissed is True

    suppression = db_session.exec(
        select(FeedbackSuppressedSession).where(
            FeedbackSuppressedSession.user_id == user.id,
            FeedbackSuppressedSession.client_session_id == session_id,
        )
    ).first()
    assert suppression is not None


def test_cadence_delivered_outfits_deduplication_across_calls(db_session: Session) -> None:
    """INVARIANT: Previously delivered outfit IDs do not increment cadence on subsequent calls (regeneration / retry)."""
    from app.models.entities import FeedbackDeliveredOutfit

    service = FeedbackCadenceService(threshold_chooser=lambda: 5)
    user = _create_user(db_session)
    o1 = _create_outfit(db_session, user.id)

    # First call with o1 -> count becomes 1, recorded in FeedbackDeliveredOutfit
    eligible1, target1 = service.process_chat_recommendations(db_session, user.id, [o1.id])
    assert eligible1 is False
    assert target1 is None
    state1 = db_session.get(FeedbackPromptState, user.id)
    assert state1.eligible_count_since_prompt == 1

    delivered_rows = db_session.exec(
        select(FeedbackDeliveredOutfit).where(
            FeedbackDeliveredOutfit.user_id == user.id,
            FeedbackDeliveredOutfit.outfit_id == o1.id,
        )
    ).all()
    assert len(delivered_rows) == 1

    # Second call with the SAME outfit o1 (e.g. query retry / regeneration) -> count remains 1!
    eligible2, target2 = service.process_chat_recommendations(db_session, user.id, [o1.id])
    assert eligible2 is False
    assert target2 is None
    state2 = db_session.get(FeedbackPromptState, user.id)
    assert state2.eligible_count_since_prompt == 1  # Did NOT increment!

    # Third call with a NEW outfit o2 -> count becomes 2
    o2 = _create_outfit(db_session, user.id)
    eligible3, target3 = service.process_chat_recommendations(db_session, user.id, [o2.id])
    assert eligible3 is False
    assert target3 is None
    state3 = db_session.get(FeedbackPromptState, user.id)
    assert state3.eligible_count_since_prompt == 2

