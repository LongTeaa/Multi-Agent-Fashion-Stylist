from io import BytesIO
from pathlib import Path
from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select
from sqlalchemy import Engine
from alembic.config import Config

from app.main import app
from app.core.dependencies import get_db_session, get_object_storage
from app.models.entities import MediaAsset, WardrobeItem, OrphanMediaCleanup
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider
from app.services.ingestion_service import create_ingestion_batch, process_ingestion_batch


@pytest.fixture
def crop_fixture(migrated_database: tuple[Config, Engine], tmp_path: Path) -> Iterator[tuple[TestClient, Engine, LocalObjectStorage, str, str]]:
    _, engine = migrated_database
    storage = LocalObjectStorage(tmp_path / 'storage', StorageBuckets(
        wardrobe='wardrobe-private', thumbnails='wardrobe-thumbnails', tryon='tryon-private'))
    user = str(uuid4())
    files = []
    for color in ('red', 'blue'):
        buffer = BytesIO()
        Image.new('RGB', (160, 200), color).save(buffer, format='PNG')
        files.append((color + '.png', buffer.getvalue()))
    with Session(engine) as session:
        batch = create_ingestion_batch(session=session, storage=storage, user_id=user, raw_files=files)
        process_ingestion_batch(session=session, storage=storage, user_id=user, batch_id=batch.id,
                                detector=FakeDetector(), vision_provider=FakeVisionProvider())
        batch_id = batch.id
    def db() -> Iterator[Session]:
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_object_storage] = lambda: storage
    yield TestClient(app), engine, storage, user, batch_id


def test_multi_photo_crop_reload_and_confirmation(crop_fixture: tuple[TestClient, Engine, LocalObjectStorage, str, str]) -> None:
    client, engine, storage, user, batch = crop_fixture
    headers = {'X-User-Id': user}
    url = f'/api/v1/ingestions/{batch}'
    review = client.get(url, headers=headers).json()['data']
    assert len(review['source_images']) == 2
    assert review['original_media_url'] is None
    assert {d['source_media_asset_id'] for d in review['detections']} == {
        s['media_asset_id'] for s in review['source_images']}
    det = review['detections'][0]
    crop_url = f"{url}/detections/{det['detection_id']}/crop"
    assert client.patch(crop_url, headers={'X-User-Id': str(uuid4())},
                        json={'bounding_box': [0, 0, 1, 1]}).status_code == 404
    assert client.patch(crop_url, headers=headers,
                        json={'bounding_box': [.9, 0, .1, 1]}).status_code == 422
    changed = client.patch(crop_url, headers=headers, json={'bounding_box': [0, 0, .5, 1]})
    assert changed.status_code == 200
    after = client.get(url, headers=headers).json()['data']
    edited = next(d for d in after['detections'] if d['detection_id'] == det['detection_id'])
    assert edited['source_media_asset_id'] == det['source_media_asset_id']
    assert edited['bounding_box'] == [0, 0, .5, 1]
    assert edited['crop_url'] != det['crop_url']
    image = Image.open(BytesIO(client.get(edited['crop_url'], headers=headers).content))
    assert image.size == (80, 200)
    original = next(s for s in after['source_images'] if s['media_asset_id'] == det['source_media_asset_id'])
    original_image = Image.open(BytesIO(client.get(original['media_url'], headers=headers).content))
    assert image.getpixel((0, 0)) == original_image.getpixel((0, 0))
    confirmed = client.post(url + '/confirm', headers=headers, json={'confirmations': [
        {'detection_id': d['detection_id'], 'accepted': True} for d in after['detections']]})
    assert confirmed.status_code == 200
    assert len(confirmed.json()['data']['wardrobe_item_ids']) == 2
    assert client.patch(crop_url, headers=headers, json={'bounding_box': [0, 0, 1, 1]}).status_code == 409
    with Session(engine) as session:
        assert len(session.exec(select(WardrobeItem)).all()) == 2
        assert session.exec(select(OrphanMediaCleanup)).all() == []


def test_failed_crop_upload_preserves_previous_review(crop_fixture: tuple[TestClient, Engine, LocalObjectStorage, str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    client, engine, storage, user, batch = crop_fixture
    headers = {'X-User-Id': user}
    url = f'/api/v1/ingestions/{batch}'
    before = client.get(url, headers=headers).json()['data']
    det = before['detections'][0]
    from app.repositories.object_storage import ObjectStorageError
    def fail(**kwargs: object) -> None:
        raise ObjectStorageError('test failure')
    monkeypatch.setattr(storage, 'put_object', fail)
    result = client.patch(f"{url}/detections/{det['detection_id']}/crop", headers=headers,
                          json={'bounding_box': [0, 0, 1, 1]})
    assert result.status_code == 503
    assert client.get(url, headers=headers).json()['data'] == before
    with Session(engine) as session:
        assert len(session.exec(select(OrphanMediaCleanup)).all()) == 2


def test_migration_preserves_confirmed_items_and_ambiguous_sources(crop_fixture: tuple[TestClient, Engine, LocalObjectStorage, str, str], migrated_database: tuple[Config, Engine]) -> None:
    client, engine, storage, user, batch = crop_fixture
    from alembic import command
    from app.models.entities import IngestionDetection
    config, _ = migrated_database
    headers = {'X-User-Id': user}
    review = client.get(f'/api/v1/ingestions/{batch}', headers=headers).json()['data']
    result = client.post(f'/api/v1/ingestions/{batch}/confirm', headers=headers,
                         json={'confirmations': [{'detection_id': d['detection_id']} for d in review['detections']]})
    assert result.status_code == 200
    with Session(engine) as session:
        original = session.get(MediaAsset, review['source_images'][0]['media_asset_id'])
        raw = storage.get_object(user_id=user, bucket=original.bucket, object_key=original.object_key)
        single = create_ingestion_batch(session=session, storage=storage, user_id=user,
                                        raw_files=[('single.png', raw)])
        process_ingestion_batch(session=session, storage=storage, user_id=user, batch_id=single.id,
                                detector=FakeDetector(), vision_provider=FakeVisionProvider())
        single_id = single.id
        expected = session.exec(select(IngestionDetection).where(
            IngestionDetection.ingestion_batch_id == single_id)).one().source_media_asset_id
    command.downgrade(config, '0008')
    command.upgrade(config, 'head')
    with Session(engine) as session:
        assert len(session.exec(select(WardrobeItem)).all()) == 2
        for detection in session.exec(select(IngestionDetection)).all():
            assert detection.source_media_asset_id == (expected if detection.ingestion_batch_id == single_id else None)
    with engine.connect() as conn:
        assert conn.exec_driver_sql('PRAGMA foreign_key_check').all() == []


def test_phone_orientation_matches_crop_coordinates() -> None:
    from app.services.upload_validation import validate_image_bytes
    from app.services.crop_engine import crop_item_and_generate_thumbnail
    source = Image.new('RGB', (160, 80), 'red')
    source.paste('blue', (80, 0, 160, 80))
    exif = Image.Exif()
    exif[274] = 6
    raw = BytesIO()
    source.save(raw, format='JPEG', exif=exif)
    validated = validate_image_bytes(raw.getvalue())
    assert (validated.width, validated.height) == (80, 160)
    legacy_crop = crop_item_and_generate_thumbnail(raw.getvalue(), (0, 0, 1, .5))
    assert (legacy_crop.crop_width, legacy_crop.crop_height) == (80, 80)
    cropped = crop_item_and_generate_thumbnail(validated.raw_bytes, (0, 0, 1, .5))
    with Image.open(BytesIO(cropped.crop_bytes)) as top:
        red, green, blue = top.getpixel((20, 20))
        assert red > 200 and green < 30 and blue < 30
