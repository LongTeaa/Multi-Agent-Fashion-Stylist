from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from threading import Barrier
from pathlib import Path
from typing import Any
from sqlalchemy import Engine
from uuid import uuid4

import pytest
from PIL import Image
from sqlmodel import Session, select

from app.agents.state import OutfitItemSlot, RankedOutfit
from app.core.seed import GOLDEN_USER_ID, seed_golden_wardrobe
from app.models.entities import (IngestionBatch, IngestionStatus, MediaAsset, ItemMedia,
                                OutfitRecommendation, WardrobeItem, OutfitSlotRole, utc_now)
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.ingestion_service import (create_ingestion_batch, process_ingestion_batch,
                                            confirm_ingestion_batch)
from app.services.cleanup_service import cleanup_expired_batches
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider
from app.schemas.ingestion import DetectionConfirmationItem
from app.services.ingestion_service import get_batch_review
from app.services.outfit_persistence import persist_outfit_recommendations
from app.api.v1.endpoints.stylist import _reconstruct_idempotent_response
from app.schemas.common import AppException


def make_ranked(session: Session) -> RankedOutfit:
    items = []
    for item_id, role in [('item-top-01', 'top'), ('item-bottom-01', 'bottom'), ('item-shoes-01', 'footwear')]:
        item = session.get(WardrobeItem, item_id)
        items.append(OutfitItemSlot(item_id=item.id, slot_role=OutfitSlotRole(role),
                                   category=item.category, name=item.sub_category,
                                   primary_color=item.primary_color, style=item.style))
    return RankedOutfit(rank=1, items=items, fashion_score=.8,
                        personalization_score=.5, composite_score=.7, explanation_vi='test')


def test_concurrent_persistence_returns_one_set(migrated_database: tuple[object, Engine]) -> None:
    _, engine = migrated_database
    seed_golden_wardrobe(engine)
    start = Barrier(2)
    def persist() -> tuple[bool, list[str]]:
        with Session(engine) as session:
            ranked = make_ranked(session)
            start.wait(timeout=10)
            return persist_outfit_recommendations(session, GOLDEN_USER_ID, 'retry-key',
                                                  'query', {}, [ranked])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: persist(), range(2)))
    assert all(ok for ok, _ in results)
    assert results[0][1] == results[1][1]
    with Session(engine) as session:
        assert len(session.exec(select(OutfitRecommendation)).all()) == 1


@pytest.mark.parametrize('change', ['inactive', 'deleted', 'unconfirmed', 'category'])
def test_replay_rejects_deleted_item(migrated_database: tuple[object, Engine], change: str) -> None:
    _, engine = migrated_database
    seed_golden_wardrobe(engine)
    with Session(engine) as session:
        persist_outfit_recommendations(session, GOLDEN_USER_ID, 'retry-key', 'query', {},
                                       [make_ranked(session)])
        item = session.get(WardrobeItem, 'item-top-01')
        if change == 'inactive':
            item.is_active = False
        elif change == 'deleted':
            item.deleted_at = utc_now()
        elif change == 'unconfirmed':
            item.is_user_confirmed = False
        else:
            from app.models.entities import WardrobeCategory
            item.category = WardrobeCategory.DRESS
        session.add(item)
        session.commit()
        recs = list(session.exec(select(OutfitRecommendation)).all())
        with pytest.raises(AppException) as exc:
            _reconstruct_idempotent_response(session, GOLDEN_USER_ID, 'retry-key', recs)
        assert exc.value.status_code == 409
        assert exc.value.code == 'STALE_RECOMMENDATION'


@pytest.mark.parametrize('expired', [False, True])
def test_cleanup_refreshes_confirmation_after_scan(
    migrated_database: tuple[object, Engine], tmp_path: Path, expired: bool,
) -> None:
    _, engine = migrated_database
    storage = LocalObjectStorage(tmp_path / 'storage', StorageBuckets(
        wardrobe='wardrobe-private', thumbnails='wardrobe-thumbnails', tryon='tryon-private'))
    buffer = BytesIO()
    Image.new('RGB', (128, 128), 'white').save(buffer, format='PNG')
    user = str(uuid4())
    with Session(engine) as session:
        batch = create_ingestion_batch(session=session, storage=storage, user_id=user,
                                       raw_files=[('item.png', buffer.getvalue())])
        process_ingestion_batch(session=session, storage=storage, user_id=user, batch_id=batch.id,
                                detector=FakeDetector(), vision_provider=FakeVisionProvider())
        review = get_batch_review(session=session, batch_id=batch.id, user_id=user)
        batch_id = batch.id
        if expired:
            batch.expires_at = utc_now() - timedelta(seconds=1)
            session.add(batch)
            session.commit()
    if expired:
        from app.schemas.common import IngestionNotReadyError
        with Session(engine) as session:
            with pytest.raises(IngestionNotReadyError):
                confirm_ingestion_batch(session=session, batch_id=batch_id, user_id=user,
                    confirmations=[DetectionConfirmationItem(detection_id=d.detection_id)
                                   for d in review.detections])
            assert session.exec(select(WardrobeItem)).all() == []
        return
    # Simulate a confirmation winning after the cleanup scan loaded its snapshot.
    class ScanRaceSession(Session):
        raced = False
        def exec(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            result = super().exec(statement, *args, **kwargs)
            if not self.raced and 'FROM ingestion_batches' in str(statement):
                rows = result.all()
                self.raced = True
                with Session(engine) as other:
                    confirm_ingestion_batch(session=other, batch_id=batch_id, user_id=user,
                        confirmations=[DetectionConfirmationItem(detection_id=d.detection_id)
                                       for d in review.detections])
                class Rows:
                    def all(self) -> list[IngestionBatch]:
                        return rows
                return Rows()
            return result
    with ScanRaceSession(engine) as session:
        cleanup_expired_batches(session=session, storage=storage,
                                current_time=utc_now() + timedelta(hours=25))
    with Session(engine) as session:
        assert session.get(IngestionBatch, batch_id).status == IngestionStatus.CONFIRMED
        for link in session.exec(select(ItemMedia)).all():
            asset = session.get(MediaAsset, link.media_asset_id)
            assert asset.deleted_at is None
            assert storage.object_exists(user_id=user, bucket=asset.bucket, object_key=asset.object_key)
