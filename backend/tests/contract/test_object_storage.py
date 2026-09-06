from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pytest
from minio.error import S3Error

from app.core.config import Settings
from app.repositories.object_storage import (
    InvalidStorageLocationError,
    LocalObjectStorage,
    MinioObjectStorage,
    ObjectNotFoundError,
    ObjectStorage,
    ObjectStorageError,
    StorageBuckets,
    StorageConfigurationError,
)

TEST_BUCKETS = StorageBuckets(
    wardrobe="wardrobe-private",
    thumbnails="wardrobe-thumbnails",
    tryon="tryon-private",
)


class FakeMinioResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeMinioClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.content_types: dict[tuple[str, str], str] = {}
        self.last_response: FakeMinioResponse | None = None
        self.failure: Exception | None = None

    def _raise_failure(self) -> None:
        if self.failure is not None:
            raise self.failure

    @staticmethod
    def _not_found(bucket_name: str, object_name: str) -> S3Error:
        return S3Error(
            None,
            "NoSuchKey",
            "Object does not exist",
            object_name,
            "request-id",
            "host-id",
            bucket_name,
            object_name,
        )

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> object:
        self._raise_failure()
        payload = data.read(length)
        self.objects[(bucket_name, object_name)] = payload
        self.content_types[(bucket_name, object_name)] = content_type
        return object()

    def get_object(self, bucket_name: str, object_name: str) -> FakeMinioResponse:
        self._raise_failure()
        try:
            data = self.objects[(bucket_name, object_name)]
        except KeyError as error:
            raise self._not_found(bucket_name, object_name) from error
        self.last_response = FakeMinioResponse(data)
        return self.last_response

    def stat_object(self, bucket_name: str, object_name: str) -> object:
        self._raise_failure()
        if (bucket_name, object_name) not in self.objects:
            raise self._not_found(bucket_name, object_name)
        return object()

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self._raise_failure()
        try:
            del self.objects[(bucket_name, object_name)]
        except KeyError as error:
            raise self._not_found(bucket_name, object_name) from error


@dataclass(frozen=True)
class StorageHarness:
    storage: ObjectStorage
    minio_client: FakeMinioClient | None = None


@pytest.fixture(params=("local", "minio"))
def storage_harness(request: pytest.FixtureRequest, tmp_path: Path) -> StorageHarness:
    if request.param == "local":
        return StorageHarness(LocalObjectStorage(tmp_path / "objects", TEST_BUCKETS))

    client = FakeMinioClient()
    return StorageHarness(MinioObjectStorage(client, TEST_BUCKETS), client)


@pytest.mark.parametrize(
    ("bucket", "object_key"),
    [
        (
            TEST_BUCKETS.wardrobe,
            "users/user-1/ingestions/batch-1/original/asset-1.jpeg",
        ),
        (TEST_BUCKETS.wardrobe, "users/user-1/items/item-1/crop/v1.png"),
        (
            TEST_BUCKETS.thumbnails,
            "users/user-1/items/item-1/thumbnail/v1.webp",
        ),
        (TEST_BUCKETS.tryon, "users/user-1/tryons/tryon-1/render.webp"),
    ],
)
def test_adapters_share_round_trip_contract(
    storage_harness: StorageHarness,
    bucket: str,
    object_key: str,
) -> None:
    storage = storage_harness.storage
    assert isinstance(storage, ObjectStorage)
    assert storage.object_exists(user_id="user-1", bucket=bucket, object_key=object_key) is False

    storage.put_object(
        user_id="user-1",
        bucket=bucket,
        object_key=object_key,
        data=b"first",
        content_type="image/webp",
    )
    assert storage.object_exists(user_id="user-1", bucket=bucket, object_key=object_key) is True
    assert storage.get_object(user_id="user-1", bucket=bucket, object_key=object_key) == b"first"

    storage.put_object(
        user_id="user-1",
        bucket=bucket,
        object_key=object_key,
        data=b"replacement",
        content_type="image/webp",
    )
    assert storage.get_object(user_id="user-1", bucket=bucket, object_key=object_key) == b"replacement"

    storage.delete_object(user_id="user-1", bucket=bucket, object_key=object_key)
    assert storage.object_exists(user_id="user-1", bucket=bucket, object_key=object_key) is False
    with pytest.raises(ObjectNotFoundError, match="Private object was not found"):
        storage.get_object(user_id="user-1", bucket=bucket, object_key=object_key)
    with pytest.raises(ObjectNotFoundError, match="Private object was not found"):
        storage.delete_object(user_id="user-1", bucket=bucket, object_key=object_key)


@pytest.mark.parametrize(
    ("bucket", "object_key"),
    [
        (TEST_BUCKETS.wardrobe, "users/user-2/items/item-1/crop/v1.png"),
        (TEST_BUCKETS.wardrobe, "users/user-1/../user-2/items/item-1/crop/v1.png"),
        (TEST_BUCKETS.wardrobe, "/users/user-1/items/item-1/crop/v1.png"),
        (TEST_BUCKETS.wardrobe, "users/user-1/items/item-1/thumbnail/v1.webp"),
        (TEST_BUCKETS.thumbnails, "users/user-1/items/item-1/crop/v1.png"),
        (TEST_BUCKETS.tryon, "users/user-1/tryons/tryon-1/other.webp"),
        ("public-assets", "users/user-1/items/item-1/crop/v1.png"),
    ],
)
def test_adapters_reject_unowned_or_non_normative_locations(
    storage_harness: StorageHarness,
    bucket: str,
    object_key: str,
) -> None:
    operations: tuple[Callable[[], object], ...] = (
        lambda: storage_harness.storage.put_object(
            user_id="user-1",
            bucket=bucket,
            object_key=object_key,
            data=b"image",
            content_type="image/png",
        ),
        lambda: storage_harness.storage.get_object(
            user_id="user-1", bucket=bucket, object_key=object_key
        ),
        lambda: storage_harness.storage.object_exists(
            user_id="user-1", bucket=bucket, object_key=object_key
        ),
        lambda: storage_harness.storage.delete_object(
            user_id="user-1", bucket=bucket, object_key=object_key
        ),
    )

    for operation in operations:
        with pytest.raises(InvalidStorageLocationError):
            operation()


def test_minio_adapter_releases_retrieval_connection() -> None:
    client = FakeMinioClient()
    storage = MinioObjectStorage(client, TEST_BUCKETS)
    object_key = "users/user-1/items/item-1/crop/v1.png"
    client.objects[(TEST_BUCKETS.wardrobe, object_key)] = b"image"

    assert storage.get_object(
        user_id="user-1", bucket=TEST_BUCKETS.wardrobe, object_key=object_key
    ) == b"image"
    assert client.last_response is not None
    assert client.last_response.closed is True
    assert client.last_response.released is True


def test_minio_adapter_preserves_content_type() -> None:
    client = FakeMinioClient()
    storage = MinioObjectStorage(client, TEST_BUCKETS)
    object_key = "users/user-1/items/item-1/thumbnail/v1.webp"

    storage.put_object(
        user_id="user-1",
        bucket=TEST_BUCKETS.thumbnails,
        object_key=object_key,
        data=b"image",
        content_type="image/webp",
    )

    assert client.content_types[(TEST_BUCKETS.thumbnails, object_key)] == "image/webp"


def test_minio_retrieval_error_does_not_expose_internal_location() -> None:
    client = FakeMinioClient()
    storage = MinioObjectStorage(client, TEST_BUCKETS)
    object_key = "users/user-1/items/item-1/crop/v1.png"
    client.failure = RuntimeError(f"provider failure at {TEST_BUCKETS.wardrobe}/{object_key}")

    with pytest.raises(ObjectStorageError) as captured_error:
        storage.get_object(
            user_id="user-1",
            bucket=TEST_BUCKETS.wardrobe,
            object_key=object_key,
        )

    public_message = str(captured_error.value)
    assert public_message == "Private object storage operation failed."
    assert TEST_BUCKETS.wardrobe not in public_message
    assert object_key not in public_message


def test_minio_adapter_requires_credentials() -> None:
    settings = Settings(
        _env_file=None,
        minio_access_key=None,
        minio_secret_key=None,
    )

    with pytest.raises(StorageConfigurationError, match="credentials are required"):
        MinioObjectStorage.from_settings(settings)


def test_minio_adapter_can_be_constructed_without_network_access() -> None:
    settings = Settings(
        _env_file=None,
        minio_endpoint="http://localhost:9000",
        minio_access_key="test-access-key",
        minio_secret_key="test-secret-key",
    )

    assert isinstance(MinioObjectStorage.from_settings(settings), ObjectStorage)
