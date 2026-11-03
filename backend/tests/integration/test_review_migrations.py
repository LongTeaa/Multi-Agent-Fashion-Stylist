from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlmodel import Session, select

from app.core.seed import GOLDEN_USER_ID, GOLDEN_WARDROBE, _new_item
from app.models.entities import (User, WardrobeItem, MediaAsset, MediaKind, ItemMedia, ItemMediaRole,
                                OutfitItem, RecommendationRequest, WardrobeRetrievalDocument)
from app.agents.state import RankedOutfit
from app.models.entities import OutfitSlotRole
from app.services.outfit_persistence import persist_outfit_recommendations
from app.services.retrieval_document_service import refresh_retrieval_document
from tests.unit.test_personalization import _make_slot


def test_seed_migration_keeps_media_outfits_documents_and_cached_references(
    migrated_database: tuple[Config, Engine],
) -> None:
    config, engine = migrated_database
    command.downgrade(config, "0010")
    legacy = ["item-top-01", "item-bottom-01", "item-shoes-01"]
    specs = [GOLDEN_WARDROBE[i] for i in (0, 3, 6)]
    asset_id = str(uuid4())
    with Session(engine) as session:
        session.add(User(id=GOLDEN_USER_ID))
        session.flush()
        for old, spec in zip(legacy, specs):
            item = _new_item(spec)
            item.id = old
            session.add(item)
            session.flush()
            refresh_retrieval_document(session, item)
        asset = MediaAsset(id=asset_id, user_id=GOLDEN_USER_ID, kind=MediaKind.CROP,
            bucket="wardrobe-private", object_key=f"users/{GOLDEN_USER_ID}/items/fixture/crop/v1.png",
            mime_type="image/png", size_bytes=1, width=1, height=1, sha256="0" * 64)
        session.add(asset)
        session.flush()
        session.add(ItemMedia(wardrobe_item_id=legacy[0], media_asset_id=asset_id,
                             user_id=GOLDEN_USER_ID, role=ItemMediaRole.PRIMARY))
        session.commit()
        outfit = RankedOutfit(rank=1, composite_score=.8, fashion_score=.8, personalization_score=.8,
            items=[_make_slot(old, role) for old, role in zip(legacy,
                [OutfitSlotRole.TOP, OutfitSlotRole.BOTTOM, OutfitSlotRole.FOOTWEAR])], explanation_vi="test")
        ok, ids = persist_outfit_recommendations(session, GOLDEN_USER_ID, "legacy", "query", {}, [outfit])
        assert ok
        session.add(RecommendationRequest(user_id=GOLDEN_USER_ID, request_id="legacy", fingerprint="0" * 64,
            response_data={"item_ids": legacy, "note": legacy[0]}))
        session.commit()
    command.upgrade(config, "head")
    with Session(engine) as session:
        assert all(session.get(WardrobeItem, old) is None for old in legacy)
        assert all(session.get(WardrobeItem, spec.id) is not None for spec in specs)
        assert session.exec(select(ItemMedia)).one().media_asset_id == asset_id
        assert session.exec(select(ItemMedia)).one().wardrobe_item_id == specs[0].id
        assert {item.wardrobe_item_id for item in session.exec(select(OutfitItem)).all()} == {spec.id for spec in specs}
        assert {item.wardrobe_item_id for item in session.exec(select(WardrobeRetrievalDocument)).all()} == {spec.id for spec in specs}
        response = session.get(RecommendationRequest, (GOLDEN_USER_ID, "legacy")).response_data
        assert response["item_ids"] == [spec.id for spec in specs]
        assert response["note"] == legacy[0]
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []
    # Downgrade/upgrade round trip keeps the same references and counts.
    command.downgrade(config, "0010")
    command.upgrade(config, "head")
    with Session(engine) as session:
        assert len(session.exec(select(WardrobeItem)).all()) == 3
        assert session.execute(text("PRAGMA foreign_key_check")).all() == []
