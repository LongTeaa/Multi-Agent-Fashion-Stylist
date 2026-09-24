import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import Session

from app.models.entities import (
    ItemMedia,
    ItemMediaRole,
    MediaAsset,
    MediaKind,
    User,
    WardrobeCategory,
    WardrobeItem,
    WardrobeRetrievalDocument,
    new_uuid,
)
from scripts.merge_wardrobe_databases import merge_wardrobe_databases


def test_merge_preserves_wardrobe_media_and_is_repeatable(
    migrated_database: tuple[object, object], tmp_path: Path
) -> None:
    _, target_engine = migrated_database
    target_path = Path(target_engine.url.database)
    source_path = tmp_path / "legacy.db"
    with sqlite3.connect(target_path) as target, sqlite3.connect(source_path) as source:
        target.backup(source)

    user_id, item_id, media_id = new_uuid(), new_uuid(), new_uuid()
    source_engine = create_engine(f"sqlite:///{source_path.as_posix()}")
    with Session(source_engine) as session:
        session.add(User(id=user_id))
        session.add(
            WardrobeItem(
                id=item_id,
                user_id=user_id,
                category=WardrobeCategory.TOP,
                sub_category="polo",
                primary_color="white",
                pattern="solid",
                material="cotton",
                style="casual",
                fit="regular",
                formality_level=3,
                is_user_confirmed=True,
            )
        )
        session.add(
            MediaAsset(
                id=media_id,
                user_id=user_id,
                kind=MediaKind.CROP,
                bucket="wardrobe-private",
                object_key=f"users/{user_id}/items/{item_id}/crop/v1.jpg",
                mime_type="image/jpeg",
                size_bytes=10,
                width=10,
                height=10,
                sha256="a" * 64,
            )
        )
        session.add(ItemMedia(wardrobe_item_id=item_id, media_asset_id=media_id, user_id=user_id, role=ItemMediaRole.PRIMARY))
        session.add(WardrobeRetrievalDocument(wardrobe_item_id=item_id, user_id=user_id, searchable_text="white polo", metadata_snapshot={}))
        session.commit()
    source_engine.dispose()

    expected = merge_wardrobe_databases(source_path, target_path)
    assert expected["wardrobe_items"] == 1
    assert expected["item_media"] == 1
    assert expected["media_assets"] == 1
    assert merge_wardrobe_databases(source_path, target_path, apply=True) == expected
    assert all(count == 0 for count in merge_wardrobe_databases(source_path, target_path).values())

    with sqlite3.connect(target_path) as target:
        target.execute("PRAGMA foreign_keys=ON")
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []
        assert target.execute("SELECT user_id FROM wardrobe_items WHERE id=?", (item_id,)).fetchone()[0] == user_id
        assert target.execute("SELECT media_asset_id FROM item_media WHERE wardrobe_item_id=?", (item_id,)).fetchone()[0] == media_id

    assert len(list(tmp_path.glob("*.before_merge_*.db"))) == 2
