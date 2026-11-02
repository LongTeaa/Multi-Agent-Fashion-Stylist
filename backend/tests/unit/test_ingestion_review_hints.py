from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func
from sqlmodel import Session, select

from app.models.entities import IngestionBatch, IngestionStatus, User, utc_now
from app.services.ingestion_service import get_batch_review


@pytest.mark.parametrize('completed,eligible', [
    (0, True), (1, True), (2, False), (12, False),
    (13, True), (14, False), (25, True),
])
def test_hint_cadence_counts_confirmed_owned_batches_only(
    migrated_database: tuple[object, Engine], completed: int, eligible: bool,
) -> None:
    _, engine = migrated_database
    user, other = str(uuid4()), str(uuid4())
    with Session(engine) as session:
        session.add_all([User(id=user), User(id=other)])
        session.flush()
        batch = IngestionBatch(user_id=user, status=IngestionStatus.NEEDS_REVIEW,
                               expires_at=utc_now() + timedelta(hours=24))
        session.add(batch)
        for owner, count, status in [(user, completed, IngestionStatus.CONFIRMED),
                                     (other, 15, IngestionStatus.CONFIRMED),
                                     (user, 3, IngestionStatus.FAILED),
                                     (user, 3, IngestionStatus.EXPIRED)]:
            for _ in range(count):
                session.add(IngestionBatch(user_id=owner, status=status,
                                           expires_at=utc_now() + timedelta(hours=24)))
        session.commit()
        before = session.exec(select(func.count()).select_from(IngestionBatch)).one()
        for _ in range(3):
            assert get_batch_review(session=session, batch_id=batch.id,
                                    user_id=user).show_review_hint is eligible
        assert session.exec(select(func.count()).select_from(IngestionBatch)).one() == before
