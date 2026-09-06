from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import mkstemp
from typing import BinaryIO, Protocol, runtime_checkable
from urllib.parse import urlsplit

from minio import Minio
from minio.error import S3Error

from app.core.config import Settings


class ObjectStorageError(RuntimeError):
    """Base error that does not expose internal storage locations."""


class ObjectNotFoundError(ObjectStorageError):
    """Raised when a requested private object does not exist."""


class StorageConfigurationError(ObjectStorageError):
    """Raised when an adapter cannot be built from application settings."""


class InvalidStorageLocationError(ValueError):
    """Raised when a bucket or object key violates the private-key contract."""


@dataclass(frozen=True)
class StorageBuckets:
    wardrobe: str
    thumbnails: str
    tryon: str

    @classmethod
    def from_settings(cls, settings: Settings) -> StorageBuckets:
        return cls(
            wardrobe=settings.minio_bucket_wardrobe,
            thumbnails=settings.minio_bucket_thumbnails,
            tryon=settings.minio_bucket_tryon,
        )

    @property
    def all(self) -> frozenset[str]:
        return frozenset((self.wardrobe, self.thumbnails, self.tryon))


@runtime_checkable
class ObjectStorage(Protocol):
    def put_object(
        self,
        *,
        user_id: str,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> None: ...

    def get_object(self, *, user_id: str, bucket: str, object_key: str) -> bytes: ...

    def object_exists(self, *, user_id: str, bucket: str, object_key: str) -> bool: ...

    def delete_object(self, *, user_id: str, bucket: str, object_key: str) -> None: ...


class _MinioResponse(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class _MinioClient(Protocol):
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BinaryIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> object: ...

    def get_object(self, bucket_name: str, object_name: str) -> _MinioResponse: ...

    def stat_object(self, bucket_name: str, object_name: str) -> object: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...


def _validate_location(
    *,
    buckets: StorageBuckets,
    user_id: str,
    bucket: str,
    object_key: str,
) -> tuple[str, ...]:
    if not user_id or any(character in user_id for character in ("/", "\\", "\x00")):
        raise InvalidStorageLocationError("Invalid storage owner.")
    if bucket not in buckets.all:
        raise InvalidStorageLocationError("Unknown private storage bucket.")
    if not object_key or object_key.startswith("/") or "\\" in object_key or "\x00" in object_key:
        raise InvalidStorageLocationError("Invalid private object key.")
    if "//" in object_key or "@" in object_key:
        raise InvalidStorageLocationError("Invalid private object key.")

    path = PurePosixPath(object_key)
    parts = path.parts
    if any(part in ("", ".", "..") for part in parts):
        raise InvalidStorageLocationError("Invalid private object key.")
    if len(parts) < 4 or parts[:2] != ("users", user_id):
        raise InvalidStorageLocationError("Object key does not belong to the authenticated user.")

    family = parts[2]
    if family == "ingestions":
        valid = bucket == buckets.wardrobe and len(parts) == 6 and parts[4] == "original"
    elif family == "items":
        role = parts[4] if len(parts) == 6 else None
        valid = (role == "crop" and bucket == buckets.wardrobe) or (
            role == "thumbnail" and bucket == buckets.thumbnails
        )
    elif family == "tryons":
        valid = bucket == buckets.tryon and len(parts) == 5 and parts[4] == "render.webp"
    else:
        valid = False

    if not valid:
        raise InvalidStorageLocationError("Object key does not match the private bucket purpose.")
    return parts


class LocalObjectStorage:
    def __init__(self, root: Path, buckets: StorageBuckets) -> None:
        self._root = root.resolve()
        self._buckets = buckets

    def _path_for(self, *, user_id: str, bucket: str, object_key: str) -> Path:
        parts = _validate_location(
            buckets=self._buckets,
            user_id=user_id,
            bucket=bucket,
            object_key=object_key,
        )
        target = self._root.joinpath(bucket, *parts).resolve()
        if not target.is_relative_to(self._root):
            raise InvalidStorageLocationError("Invalid private object key.")
        return target

    def put_object(
        self,
        *,
        user_id: str,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        del content_type
        target = self._path_for(user_id=user_id, bucket=bucket, object_key=object_key)
        temporary_path: Path | None = None

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, raw_temporary_path = mkstemp(prefix=".upload-", dir=target.parent)
            temporary_path = Path(raw_temporary_path)
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(data)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
        except OSError as error:
            raise ObjectStorageError("Private object write failed.") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def get_object(self, *, user_id: str, bucket: str, object_key: str) -> bytes:
        target = self._path_for(user_id=user_id, bucket=bucket, object_key=object_key)
        try:
            return target.read_bytes()
        except FileNotFoundError as error:
            raise ObjectNotFoundError("Private object was not found.") from error
        except OSError as error:
            raise ObjectStorageError("Private object read failed.") from error

    def object_exists(self, *, user_id: str, bucket: str, object_key: str) -> bool:
        target = self._path_for(user_id=user_id, bucket=bucket, object_key=object_key)
        return target.is_file()

    def delete_object(self, *, user_id: str, bucket: str, object_key: str) -> None:
        target = self._path_for(user_id=user_id, bucket=bucket, object_key=object_key)
        try:
            target.unlink()
        except FileNotFoundError as error:
            raise ObjectNotFoundError("Private object was not found.") from error
        except OSError as error:
            raise ObjectStorageError("Private object deletion failed.") from error


class MinioObjectStorage:
    _NOT_FOUND_CODES = frozenset(("NoSuchKey", "NoSuchObject"))

    def __init__(self, client: _MinioClient, buckets: StorageBuckets) -> None:
        self._client = client
        self._buckets = buckets

    @classmethod
    def from_settings(cls, settings: Settings) -> MinioObjectStorage:
        if settings.minio_access_key is None or settings.minio_secret_key is None:
            raise StorageConfigurationError("MinIO credentials are required.")

        endpoint_url = urlsplit(str(settings.minio_endpoint))
        if endpoint_url.hostname is None or endpoint_url.path not in ("", "/"):
            raise StorageConfigurationError("MINIO_ENDPOINT must not contain a path.")

        endpoint = endpoint_url.hostname
        if endpoint_url.port is not None:
            endpoint = f"{endpoint}:{endpoint_url.port}"

        client = Minio(
            endpoint,
            access_key=settings.minio_access_key.get_secret_value(),
            secret_key=settings.minio_secret_key.get_secret_value(),
            secure=settings.minio_secure,
        )
        return cls(client, StorageBuckets.from_settings(settings))

    @staticmethod
    def _raise_storage_error(error: Exception) -> None:
        if isinstance(error, S3Error) and error.code in MinioObjectStorage._NOT_FOUND_CODES:
            raise ObjectNotFoundError("Private object was not found.") from error
        raise ObjectStorageError("Private object storage operation failed.") from error

    def _validate(self, *, user_id: str, bucket: str, object_key: str) -> None:
        _validate_location(
            buckets=self._buckets,
            user_id=user_id,
            bucket=bucket,
            object_key=object_key,
        )

    def put_object(
        self,
        *,
        user_id: str,
        bucket: str,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> None:
        self._validate(user_id=user_id, bucket=bucket, object_key=object_key)
        try:
            self._client.put_object(
                bucket,
                object_key,
                BytesIO(data),
                len(data),
                content_type=content_type,
            )
        except Exception as error:
            self._raise_storage_error(error)

    def get_object(self, *, user_id: str, bucket: str, object_key: str) -> bytes:
        self._validate(user_id=user_id, bucket=bucket, object_key=object_key)
        response: _MinioResponse | None = None
        try:
            response = self._client.get_object(bucket, object_key)
            return response.read()
        except Exception as error:
            self._raise_storage_error(error)
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def object_exists(self, *, user_id: str, bucket: str, object_key: str) -> bool:
        self._validate(user_id=user_id, bucket=bucket, object_key=object_key)
        try:
            self._client.stat_object(bucket, object_key)
            return True
        except S3Error as error:
            if error.code in self._NOT_FOUND_CODES:
                return False
            self._raise_storage_error(error)
        except Exception as error:
            self._raise_storage_error(error)

    def delete_object(self, *, user_id: str, bucket: str, object_key: str) -> None:
        self._validate(user_id=user_id, bucket=bucket, object_key=object_key)
        try:
            self._client.stat_object(bucket, object_key)
            self._client.remove_object(bucket, object_key)
        except Exception as error:
            self._raise_storage_error(error)
