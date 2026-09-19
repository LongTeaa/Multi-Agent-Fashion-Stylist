"""Serve a migrated, isolated API fixture for Playwright browser tests."""

from __future__ import annotations

import os
import sys
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import Engine  # noqa: E402
from sqlmodel import Session  # noqa: E402
import uvicorn  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import create_database_engine, get_engine  # noqa: E402
from app.core.dependencies import get_object_storage  # noqa: E402
from app.core.seed import GOLDEN_USER_ID, GOLDEN_WARDROBE, seed_golden_wardrobe  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import ItemMedia, ItemMediaRole, MediaAsset, MediaKind, new_uuid  # noqa: E402
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets  # noqa: E402


def seed_reference_images(engine: Engine, storage: LocalObjectStorage) -> None:
    """Attach real private media so browser tests cover image loading and try-on."""
    with Session(engine) as session:
        for index, item in enumerate(GOLDEN_WARDROBE):
            image = Image.new("RGB", (80, 80), color=(90 + index * 12, 110, 135))
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            image_bytes = buffer.getvalue()
            asset_id = new_uuid()
            key = f"users/{GOLDEN_USER_ID}/items/{item.id}/crop/v1.png"
            storage.put_object(
                user_id=GOLDEN_USER_ID,
                bucket="wardrobe-private",
                object_key=key,
                data=image_bytes,
                content_type="image/png",
            )
            session.add(
                MediaAsset(
                    id=asset_id,
                    user_id=GOLDEN_USER_ID,
                    kind=MediaKind.CROP,
                    bucket="wardrobe-private",
                    object_key=key,
                    mime_type="image/png",
                    size_bytes=len(image_bytes),
                    width=80,
                    height=80,
                    sha256=sha256(image_bytes).hexdigest(),
                )
            )
            session.flush()
            session.add(
                ItemMedia(
                    wardrobe_item_id=item.id,
                    media_asset_id=asset_id,
                    user_id=GOLDEN_USER_ID,
                    role=ItemMediaRole.PRIMARY,
                )
            )
        session.commit()


def main() -> None:
    with TemporaryDirectory(prefix="fashion-browser-e2e-") as fixture_dir:
        fixture_root = Path(fixture_dir)
        database_url = f"sqlite:///{(fixture_root / 'fixture.db').as_posix()}"
        os.environ["DATABASE_URL"] = database_url
        os.environ["OBJECT_STORAGE_BACKEND"] = "local"
        os.environ["CLEANUP_SCHEDULER_ENABLED"] = "false"
        get_settings.cache_clear()
        get_engine.cache_clear()

        command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
        engine = create_database_engine(database_url)
        seed_golden_wardrobe(engine)
        storage = LocalObjectStorage(
            root=fixture_root / "storage",
            buckets=StorageBuckets(
                wardrobe="wardrobe-private",
                thumbnails="wardrobe-thumbnails",
                tryon="tryon-private",
            ),
        )
        seed_reference_images(engine, storage)
        app.dependency_overrides[get_object_storage] = lambda: storage
        try:
            uvicorn.run(app, host="127.0.0.1", port=8011, log_level="warning")
        finally:
            app.dependency_overrides.clear()
            engine.dispose()


if __name__ == "__main__":
    main()
