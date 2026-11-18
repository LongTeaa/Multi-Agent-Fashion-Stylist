"""Build the public demo wardrobes through the real ingestion pipeline.

Downloads the CC0 images listed in data/fixtures/demo_wardrobe_v1.json into the
git-ignored data/demo-wardrobe/ directory, verifies each SHA-256, and uploads them
for one deterministic demo user per persona using the configured detector, vision
provider, object storage, and database.

Batches stop at ``needs_review``: items are never confirmed automatically
(AGENTS.md). Open the app as the printed demo user and confirm each detection,
correcting attributes where the provider was wrong. Re-running skips images that
user already uploaded, so an interrupted run can be resumed.

Usage (from backend/):
    python scripts/build_demo_wardrobe.py --download --persona female
    python scripts/build_demo_wardrobe.py --persona all --dry-run
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
from uuid import NAMESPACE_URL, uuid5

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from sqlmodel import Session, select  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402
from app.core.dependencies import get_detector, get_object_storage, get_vision_provider  # noqa: E402
from app.models.entities import InputKind, MediaAsset, MediaKind, User  # noqa: E402
from app.services.ingestion_service import (  # noqa: E402
    create_ingestion_batch,
    process_ingestion_batch,
)

DEFAULT_MANIFEST = ROOT / "data" / "fixtures" / "demo_wardrobe_v1.json"
DEFAULT_IMAGES = ROOT / "data" / "demo-wardrobe"
ALLOWED_SOURCE_PREFIX = "https://raw.githubusercontent.com/alexeygrigorev/clothing-dataset/"
BATCH_SIZE = 10  # create_ingestion_batch accepts at most 10 images
USER_STORAGE_KEY = "fashion_stylist_user_id"


def demo_user_id(persona: str) -> str:
    """Stable demo identity per persona; never a real user's identifier."""
    return str(uuid5(NAMESPACE_URL, f"multi-agent-fashion-stylist:demo-wardrobe:{persona}"))


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("dataset_version") != "demo-wardrobe-v1":
        raise SystemExit(f"Unsupported manifest version in {path}")
    return manifest


def _download(url: str, attempts: int = 4) -> bytes:
    """Fetch one source image; GitHub raw intermittently resets connections."""
    if not url.startswith(ALLOWED_SOURCE_PREFIX):
        raise SystemExit(f"Refusing unexpected source URL: {url}")
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 - prefix checked
                return response.read()
        except (OSError, urllib.error.URLError) as error:
            last_error = error
            time.sleep(2 ** attempt)
    raise SystemExit(f"Download failed after {attempts} attempts: {url} ({last_error})")


def ensure_image(item: dict, images_dir: Path, *, download: bool) -> bytes:
    path = images_dir / f"{item['source_image_id']}.jpg"
    if not path.is_file():
        if not download:
            raise SystemExit(f"Missing {path.name}; rerun with --download")
        path.write_bytes(_download(item["source_url"]))
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != item["sha256"]:
        raise SystemExit(f"SHA-256 mismatch for {path.name}; delete it and rerun with --download")
    return raw


def already_uploaded(session: Session, user_id: str) -> set[str]:
    rows = session.exec(
        select(MediaAsset.sha256).where(
            MediaAsset.user_id == user_id,
            MediaAsset.kind == MediaKind.ORIGINAL,
            MediaAsset.deleted_at.is_(None),
        )
    ).all()
    return {digest for digest in rows if digest}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--persona", choices=("female", "male", "all"), default="all")
    parser.add_argument("--download", action="store_true", help="Download images missing from --images-dir")
    parser.add_argument("--dry-run", action="store_true", help="Verify images and show the plan without uploading")
    parser.add_argument("--max-batches", type=int, default=None,
                        help="Upload at most this many batches of 10 per persona (probe provider quota first)")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    args.images_dir.mkdir(parents=True, exist_ok=True)
    personas = ("female", "male") if args.persona == "all" else (args.persona,)
    settings = get_settings()
    print(f"Database: {settings.database_url}")
    print(f"Providers: detector={settings.detector_backend} vision={settings.vision_provider} "
          f"storage={settings.object_storage_backend}")

    engine = create_database_engine(settings.database_url)
    storage = get_object_storage()
    detector = None if args.dry_run else get_detector()
    vision_provider = None if args.dry_run else get_vision_provider()
    try:
        for persona in personas:
            user_id = demo_user_id(persona)
            items = [item for item in manifest["items"] if item["persona"] == persona]
            images = [(item, ensure_image(item, args.images_dir, download=args.download)) for item in items]
            with Session(engine) as session:
                done = already_uploaded(session, user_id)
            pending = [(item, raw) for item, raw in images if item["sha256"] not in done]
            print(f"\n[{persona}] user {user_id}: {len(items)} items, {len(items) - len(pending)} already "
                  f"uploaded, {len(pending)} to upload")
            if args.dry_run or not pending:
                continue
            with Session(engine) as session:
                if session.get(User, user_id) is None:
                    session.add(User(id=user_id))
                    session.commit()
            starts = list(range(0, len(pending), BATCH_SIZE))
            if args.max_batches is not None:
                starts = starts[: max(0, args.max_batches)]
            for start in starts:
                chunk = pending[start:start + BATCH_SIZE]
                with Session(engine) as session:
                    batch = create_ingestion_batch(
                        session=session,
                        storage=storage,
                        user_id=user_id,
                        raw_files=[(f"{item['source_image_id']}.jpg", raw) for item, raw in chunk],
                        declared_input_kind=InputKind.SINGLE_ITEM,
                    )
                    batch = process_ingestion_batch(
                        session=session,
                        storage=storage,
                        detector=detector,
                        vision_provider=vision_provider,
                        batch_id=batch.id,
                        user_id=user_id,
                    )
                    warnings = len(batch.quality_warnings or [])
                    print(f"  batch {batch.id}: {len(chunk)} images -> {batch.status.value}"
                          f" ({warnings} warnings)")
            print(f"  Review in the app: run in the browser console, then reload:\n"
                  f"    localStorage.setItem('{USER_STORAGE_KEY}', '{user_id}')")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
