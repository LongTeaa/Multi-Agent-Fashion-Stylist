from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlmodel import Session, select

from app.core.dependencies import get_db_session, get_object_storage
from app.main import app
from app.models.entities import IngestionBatch, IngestionStatus, MediaAsset, MediaKind, User
from app.repositories.object_storage import LocalObjectStorage, StorageBuckets
from app.schemas.common import ForbiddenAssetError, ValidationError
from app.services.ingestion_service import create_ingestion_batch
from app.services.upload_validation import (
    MAX_FILE_SIZE_BYTES,
    MIN_PIXEL_DIMENSION,
    ValidatedImage,
    validate_image_bytes,
)


def create_test_image_bytes(
    format_name: str = "JPEG",
    size: tuple[int, int] = (128, 128),
    color: tuple[int, int, int] = (255, 0, 0),
) -> bytes:
    buffer = BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(buffer, format=format_name)
    return buffer.getvalue()


@pytest.fixture
def test_storage(tmp_path: Path) -> LocalObjectStorage:
    buckets = StorageBuckets(
        wardrobe="wardrobe-private",
        thumbnails="wardrobe-thumbnails",
        tryon="tryon-private",
    )
    return LocalObjectStorage(root=tmp_path / "storage", buckets=buckets)


class TestUploadValidationService:
    def test_accepts_valid_formats(self) -> None:
        for fmt, expected_mime, expected_ext in [
            ("JPEG", "image/jpeg", "jpg"),
            ("PNG", "image/png", "png"),
            ("WEBP", "image/webp", "webp"),
        ]:
            data = create_test_image_bytes(format_name=fmt, size=(100, 100))
            validated = validate_image_bytes(data)
            assert isinstance(validated, ValidatedImage)
            assert validated.mime_type == expected_mime
            assert validated.extension == expected_ext
            assert validated.width == 100
            assert validated.height == 100
            assert len(validated.sha256) == 64
            assert validated.size_bytes == len(data)

    def test_rejects_empty_bytes(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            validate_image_bytes(b"")
        assert exc_info.value.code == "VALIDATION_ERROR"
        assert "rỗng" in exc_info.value.message

    def test_rejects_spoofed_or_corrupt_files(self) -> None:
        fake_files = [
            b"This is a plain text file pretending to be an image.",
            b"MZ\x90\x00\x03\x00\x00\x00",  # Fake DOS/Windows executable header
            b"\x89PNG\r\n\x1a\nCorrupted byte stream",
        ]
        for fake_data in fake_files:
            with pytest.raises(ValidationError) as exc_info:
                validate_image_bytes(fake_data)
            assert exc_info.value.code == "VALIDATION_ERROR"

    def test_rejects_oversized_file(self) -> None:
        large_bytes = b"0" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(ValidationError) as exc_info:
            validate_image_bytes(large_bytes)
        assert exc_info.value.code == "VALIDATION_ERROR"
        assert "10MB" in exc_info.value.message

    def test_rejects_too_small_pixels(self) -> None:
        too_small_data = create_test_image_bytes(size=(MIN_PIXEL_DIMENSION - 1, 100))
        with pytest.raises(ValidationError) as exc_info:
            validate_image_bytes(too_small_data)
        assert exc_info.value.code == "VALIDATION_ERROR"
        assert "quá nhỏ" in exc_info.value.message


class TestIngestionApiAndFailureSemantics:
    def test_upload_success_and_persistence(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        def override_storage():
            return test_storage

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = override_storage

        try:
            client = TestClient(app)
            img1_bytes = create_test_image_bytes("JPEG", (120, 120), (255, 0, 0))
            img2_bytes = create_test_image_bytes("PNG", (150, 150), (0, 255, 0))

            files = [
                ("images[]", ("photo1.jpg", img1_bytes, "image/jpeg")),
                ("images[]", ("photo2.png", img2_bytes, "image/png")),
            ]
            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=files,
            )

            assert response.status_code == 202
            body = response.json()
            assert body["success"] is True
            assert "batch_id" in body["data"]
            assert body["data"]["status"] == "processing"

            batch_id = body["data"]["batch_id"]

            with Session(engine) as session:
                batch = session.get(IngestionBatch, batch_id)
                assert batch is not None
                assert batch.status in (IngestionStatus.PROCESSING, IngestionStatus.NEEDS_REVIEW)

                original_assets = session.exec(
                    select(MediaAsset).where(
                        MediaAsset.ingestion_batch_id == batch_id,
                        MediaAsset.kind == MediaKind.ORIGINAL,
                    )
                ).all()
                assert len(original_assets) == 2
                for asset in original_assets:
                    assert test_storage.object_exists(
                        user_id=user_id,
                        bucket=asset.bucket,
                        object_key=asset.object_key,
                    )
        finally:
            app.dependency_overrides.clear()

    def test_upload_rejects_exceeding_10_files(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            single_img = create_test_image_bytes("JPEG", (80, 80))
            files = [("images[]", (f"img_{i}.jpg", single_img, "image/jpeg")) for i in range(11)]

            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=files,
            )
            assert response.status_code == 422
            body = response.json()
            assert body["success"] is False
            assert body["error"]["code"] == "VALIDATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_upload_accepts_boundary_10_files(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """Uploading exactly 10 images (boundary maximum) is accepted with HTTP 202."""
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            single_img = create_test_image_bytes("JPEG", (80, 80))
            files = [("images[]", (f"img_{i}.jpg", single_img, "image/jpeg")) for i in range(10)]

            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=files,
            )
            assert response.status_code == 202
            body = response.json()
            assert body["success"] is True
            assert "batch_id" in body["data"]
            assert body["data"]["status"] == "processing"

            batch_id = body["data"]["batch_id"]
            with Session(engine) as session:
                batch = session.get(IngestionBatch, batch_id)
                assert batch is not None
                original_assets = session.exec(
                    select(MediaAsset).where(
                        MediaAsset.ingestion_batch_id == batch_id,
                        MediaAsset.kind == MediaKind.ORIGINAL,
                    )
                ).all()
                assert len(original_assets) == 10
        finally:
            app.dependency_overrides.clear()

    def test_upload_rejects_zero_files(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """Submitting no images returns HTTP 422 VALIDATION_ERROR."""
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                data={},
            )
            assert response.status_code == 422
            body = response.json()
            assert body["success"] is False
            assert body["error"]["code"] == "VALIDATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_upload_rejects_field_without_brackets(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """Contract requires 'images[]' alias; submitting unbracketed 'images' returns 422."""
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            single_img = create_test_image_bytes("JPEG", (80, 80))
            files = [("images", ("img.jpg", single_img, "image/jpeg"))]

            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=files,
            )
            assert response.status_code == 422
            body = response.json()
            assert body["success"] is False
            assert body["error"]["code"] == "VALIDATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_upload_rejects_disguised_or_corrupted_file(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """Disguised non-image bytes (e.g. text/plain pretending to be JPEG) return 422."""
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            fake_bytes = b"Not an image at all, just plain ASCII text!"
            files = [("images[]", ("fake.jpg", fake_bytes, "image/jpeg"))]

            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=files,
            )
            assert response.status_code == 422
            body = response.json()
            assert body["success"] is False
            assert body["error"]["code"] == "VALIDATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_upload_rejects_invalid_declared_input_kind(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        """Submitting an invalid declared_input_kind enum value returns 422."""
        _, engine = migrated_database
        user_id = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            single_img = create_test_image_bytes("JPEG", (80, 80))
            files = [("images[]", ("item.jpg", single_img, "image/jpeg"))]

            response = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_id},
                files=files,
                data={"declared_input_kind": "invalid_kind_name"},
            )
            assert response.status_code == 422
            body = response.json()
            assert body["success"] is False
            assert body["error"]["code"] == "VALIDATION_ERROR"
        finally:
            app.dependency_overrides.clear()

    def test_media_streaming_and_cross_user_isolation(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
    ) -> None:
        _, engine = migrated_database
        user_a = str(uuid4())
        user_b = str(uuid4())

        def override_db():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_db_session] = override_db
        app.dependency_overrides[get_object_storage] = lambda: test_storage

        try:
            client = TestClient(app)
            test_img = create_test_image_bytes("JPEG", (100, 100), (0, 0, 255))
            upload_res = client.post(
                "/api/v1/ingestions",
                headers={"X-User-Id": user_a},
                files=[("images[]", ("item.jpg", test_img, "image/jpeg"))],
            )
            assert upload_res.status_code == 202
            batch_id = upload_res.json()["data"]["batch_id"]

            with Session(engine) as session:
                asset = session.exec(
                    select(MediaAsset).where(MediaAsset.ingestion_batch_id == batch_id)
                ).first()
                assert asset is not None
                asset_id = asset.id

            # 1. User A (owner) can stream the asset
            res_owner = client.get(
                f"/api/v1/media/{asset_id}",
                headers={"X-User-Id": user_a},
            )
            assert res_owner.status_code == 200
            assert res_owner.headers["content-type"] == "image/jpeg"
            assert res_owner.content == test_img

            # 2. User B (non-owner) receives 403 FORBIDDEN_ASSET with normative Vietnamese message
            res_non_owner = client.get(
                f"/api/v1/media/{asset_id}",
                headers={"X-User-Id": user_b},
            )
            assert res_non_owner.status_code == 403
            err_body = res_non_owner.json()
            assert err_body["success"] is False
            assert err_body["error"]["code"] == "FORBIDDEN_ASSET"
            assert err_body["error"]["message"] == "Bạn không có quyền truy cập ảnh này."

            # 3. Non-existent asset ID returns 404
            res_not_found = client.get(
                f"/api/v1/media/{uuid4()}",
                headers={"X-User-Id": user_a},
            )
            assert res_not_found.status_code == 404
            assert res_not_found.json()["error"]["code"] == "MEDIA_NOT_FOUND"
        finally:
            app.dependency_overrides.clear()

    def test_failure_semantics_fs1_storage_failure_rollback(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())

        def broken_put_object(*args, **kwargs):
            raise RuntimeError("Simulated ObjectStorage I/O failure")

        monkeypatch.setattr(test_storage, "put_object", broken_put_object)

        with Session(engine) as session:
            img = create_test_image_bytes()
            with pytest.raises(Exception):
                create_ingestion_batch(
                    session=session,
                    storage=test_storage,
                    user_id=user_id,
                    raw_files=[("test.jpg", img)],
                )

            # Assert database transaction was rolled back cleanly
            batches = session.exec(select(IngestionBatch).where(IngestionBatch.user_id == user_id)).all()
            assert len(batches) == 0
            assets = session.exec(select(MediaAsset).where(MediaAsset.user_id == user_id)).all()
            assert len(assets) == 0

    def test_failure_semantics_fs2_db_error_compensating_cleanup(
        self,
        migrated_database: tuple[object, object],
        test_storage: LocalObjectStorage,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _, engine = migrated_database
        user_id = str(uuid4())
        deleted_keys: list[str] = []

        original_delete = test_storage.delete_object

        def track_delete(*, user_id: str, bucket: str, object_key: str):
            deleted_keys.append(object_key)
            original_delete(user_id=user_id, bucket=bucket, object_key=object_key)

        monkeypatch.setattr(test_storage, "delete_object", track_delete)

        with Session(engine) as session:
            # Fail the final batch/media commit after the user and cleanup
            # manifest commits have succeeded and the object was uploaded.
            original_commit = session.commit
            commit_count = 0

            def broken_commit():
                nonlocal commit_count
                commit_count += 1
                if commit_count == 3:
                    raise RuntimeError("Simulated DB lock/commit crash")
                return original_commit()

            monkeypatch.setattr(session, "commit", broken_commit)

            img = create_test_image_bytes()
            with pytest.raises(Exception):
                create_ingestion_batch(
                    session=session,
                    storage=test_storage,
                    user_id=user_id,
                    raw_files=[("test.jpg", img)],
                )

            # Assert compensating cleanup deleted the uploaded object
            assert len(deleted_keys) == 1
            assert "original" in deleted_keys[0]
            # Verify the object no longer exists in storage
            assert not test_storage.object_exists(
                user_id=user_id,
                bucket="wardrobe-private",
                object_key=deleted_keys[0],
            )


def _photo_with_metadata(
    format_name: str,
    *,
    orientation: int = 1,
    size: tuple[int, int] = (160, 96),
) -> bytes:
    """A phone-style photo: left half red, right half blue, with GPS and device EXIF."""
    image = Image.new("RGB", size, "red")
    image.paste("blue", (size[0] // 2, 0, size[0], size[1]))
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x010F] = "PhoneMaker"
    exif[0x0132] = "2026:11:19 08:30:00"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2], gps[3], gps[4] = "N", (10.0, 46.0, 30.0), "E", (106.0, 41.0, 50.0)
    exif[0x8825] = gps
    options: dict[str, object] = {"exif": exif.tobytes()}
    if format_name != "PNG":
        options["xmp"] = b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF/></x:xmpmeta>'
    buffer = BytesIO()
    image.save(buffer, format=format_name, **options)
    return buffer.getvalue()


def _assert_no_metadata(raw: bytes) -> None:
    with Image.open(BytesIO(raw)) as image:
        assert len(image.getexif()) == 0
        assert "xmp" not in image.info and "XML:com.adobe.xmp" not in image.info
        assert not getattr(image, "text", None)
    assert b"PhoneMaker" not in raw


class TestUploadMetadataStripping:
    @pytest.mark.parametrize("format_name", ["JPEG", "PNG", "WEBP"])
    @pytest.mark.parametrize("orientation", [1, 6])
    def test_strips_gps_and_device_metadata_and_applies_orientation(
        self, format_name: str, orientation: int
    ) -> None:
        validated = validate_image_bytes(_photo_with_metadata(format_name, orientation=orientation))

        _assert_no_metadata(validated.raw_bytes)
        expected = (96, 160) if orientation == 6 else (160, 96)
        assert (validated.width, validated.height) == expected
        assert validated.size_bytes == len(validated.raw_bytes)
        with Image.open(BytesIO(validated.raw_bytes)) as image:
            assert image.format == format_name
            assert image.size == expected
            # Orientation 6 means "rotate 90 degrees clockwise to display": red ends on top.
            top_left = image.convert("RGB").getpixel((5, 5))
            assert top_left[0] > 200 and top_left[2] < 60

    def test_upload_without_metadata_is_kept_byte_for_byte(self) -> None:
        raw = create_test_image_bytes("JPEG")
        assert validate_image_bytes(raw).raw_bytes == raw

    def test_jpeg_keeps_its_quantization_when_only_metadata_is_removed(self) -> None:
        source = Image.effect_noise((256, 256), 64).convert("RGB")
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"
        buffer = BytesIO()
        source.save(buffer, format="JPEG", quality=92, exif=exif.tobytes())
        raw = buffer.getvalue()

        cleaned = validate_image_bytes(raw).raw_bytes

        with Image.open(BytesIO(raw)) as before, Image.open(BytesIO(cleaned)) as after:
            assert after.quantization == before.quantization
            before_pixels = before.convert("L").tobytes()
            after_pixels = after.convert("L").tobytes()
        mean_error = sum(abs(a - b) for a, b in zip(before_pixels, after_pixels)) / len(before_pixels)
        assert mean_error < 2.0

    def test_png_text_chunks_are_removed_and_transparency_is_kept(self) -> None:
        from PIL.PngImagePlugin import PngInfo

        image = Image.new("P", (96, 96), 0)
        image.putpalette([255, 255, 255, 255, 0, 0] + [0] * 762)
        image.paste(1, (0, 0, 48, 96))
        info = PngInfo()
        info.add_text("Author", "PhoneMaker owner")
        buffer = BytesIO()
        image.save(buffer, format="PNG", pnginfo=info, transparency=0)

        cleaned = validate_image_bytes(buffer.getvalue()).raw_bytes

        _assert_no_metadata(cleaned)
        with Image.open(BytesIO(cleaned)) as result:
            assert result.info.get("transparency") == 0
            assert result.convert("RGBA").getpixel((90, 10))[3] == 0


@pytest.mark.parametrize(("orientation", "stored_size"), [(1, (160, 96)), (6, (96, 160))])
def test_ingestion_stores_and_sends_photos_without_metadata(
    migrated_database: tuple[object, object],
    test_storage: LocalObjectStorage,
    orientation: int,
    stored_size: tuple[int, int],
) -> None:
    """The stored original and the bytes given to the detector (Gemini in production) carry no EXIF."""
    from app.core.dependencies import get_detector, get_vision_provider
    from app.services.fakes.vision_fakes import FakeDetector, FakeVisionProvider

    _, engine = migrated_database
    user_id = str(uuid4())
    received: list[bytes] = []

    class RecordingDetector(FakeDetector):
        def detect(self, image_bytes: bytes):  # type: ignore[no-untyped-def]
            received.append(image_bytes)
            return super().detect(image_bytes)

    def override_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_object_storage] = lambda: test_storage
    app.dependency_overrides[get_detector] = lambda: RecordingDetector(mode="single_item")
    app.dependency_overrides[get_vision_provider] = lambda: FakeVisionProvider(scenario="golden_polo")
    try:
        response = TestClient(app).post(
            "/api/v1/ingestions",
            headers={"X-User-Id": user_id},
            files=[("images[]", ("phone.jpg", _photo_with_metadata("JPEG", orientation=orientation), "image/jpeg"))],
        )
        assert response.status_code == 202

        with Session(engine) as session:
            original = session.exec(
                select(MediaAsset).where(
                    MediaAsset.user_id == user_id, MediaAsset.kind == MediaKind.ORIGINAL
                )
            ).one()
            stored = test_storage.get_object(
                user_id=user_id, bucket=original.bucket, object_key=original.object_key
            )
            assert (original.width, original.height) == stored_size
            assert original.size_bytes == len(stored)

        _assert_no_metadata(stored)
        assert received == [stored]
    finally:
        app.dependency_overrides.clear()
