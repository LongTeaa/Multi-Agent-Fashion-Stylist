from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.dependencies import get_db_session, get_object_storage
from app.main import app
from app.repositories.object_storage import ObjectNotFoundError, ObjectStorageError


def test_unhandled_exception_returns_standard_500_envelope() -> None:
    """Issue 3.5: Any unhandled exception must be captured and returned in the API error envelope."""

    def exploding_dependency():
        raise RuntimeError("Catastrophic internal worker failure")

    app.dependency_overrides[get_object_storage] = exploding_dependency
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            f"/api/v1/media/{uuid4()}",
            headers={"X-User-Id": str(uuid4())},
        )
        assert response.status_code == 500
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert "Catastrophic internal worker failure" not in response.text
        assert "request_id" in body["error"]["details"]
    finally:
        app.dependency_overrides.clear()


def test_storage_error_returns_standard_503_envelope() -> None:
    """Issue 3.5: Storage connectivity loss returns structured 503 STORAGE_ERROR envelope."""

    def failing_storage():
        mock_storage = MagicMock()
        mock_storage.get_object.side_effect = ObjectStorageError("MinIO connection timed out")
        return mock_storage

    def dummy_session():
        mock_session = MagicMock()
        mock_asset = MagicMock()
        mock_asset.deleted_at = None
        mock_asset.user_id = "test-user"
        mock_session.get.return_value = mock_asset
        return mock_session

    app.dependency_overrides[get_object_storage] = failing_storage
    app.dependency_overrides[get_db_session] = dummy_session
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            f"/api/v1/media/{uuid4()}",
            headers={"X-User-Id": "test-user"},
        )
        assert response.status_code == 503
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "STORAGE_ERROR"
        assert body["error"]["message"] == "Hệ thống lưu trữ tệp tạm thời gặp sự cố. Vui lòng thử lại sau."
        assert body["error"]["details"] is None
    finally:
        app.dependency_overrides.clear()


def test_database_integrity_error_returns_standard_409_envelope() -> None:
    """Issue 3.5: Uncaught DB unique/foreign-key collision returns 409 DATA_CONFLICT envelope."""

    def conflict_session():
        mock_session = MagicMock()
        mock_session.get.side_effect = IntegrityError(
            statement="SELECT 1",
            params={},
            orig=Exception("UNIQUE constraint failed"),
        )
        return mock_session

    app.dependency_overrides[get_db_session] = conflict_session
    app.dependency_overrides[get_object_storage] = lambda: MagicMock()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            f"/api/v1/media/{uuid4()}",
            headers={"X-User-Id": str(uuid4())},
        )
        assert response.status_code == 409
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "DATA_CONFLICT"
        assert body["error"]["details"] is None
    finally:
        app.dependency_overrides.clear()


def test_database_sqlalchemy_error_returns_standard_500_envelope() -> None:
    """Issue 3.5: Uncaught general database errors return 500 DATABASE_ERROR envelope."""

    def failing_db():
        mock_session = MagicMock()
        mock_session.get.side_effect = SQLAlchemyError("Database connection lost")
        return mock_session

    app.dependency_overrides[get_db_session] = failing_db
    app.dependency_overrides[get_object_storage] = lambda: MagicMock()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            f"/api/v1/media/{uuid4()}",
            headers={"X-User-Id": str(uuid4())},
        )
        assert response.status_code == 500
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "DATABASE_ERROR"
        assert body["error"]["message"] == "Đã xảy ra lỗi cơ sở dữ liệu. Vui lòng thử lại sau."
    finally:
        app.dependency_overrides.clear()


def test_object_not_found_returns_standard_404_envelope() -> None:
    """Issue 3.5: Missing media asset in object storage returns 404 envelope without leaking 500."""

    def missing_storage():
        mock_storage = MagicMock()
        mock_storage.get_object.side_effect = ObjectNotFoundError("Private object was not found")
        return mock_storage

    def dummy_session():
        mock_session = MagicMock()
        mock_asset = MagicMock()
        mock_asset.deleted_at = None
        mock_asset.user_id = "test-user"
        mock_session.get.return_value = mock_asset
        return mock_session

    app.dependency_overrides[get_object_storage] = missing_storage
    app.dependency_overrides[get_db_session] = dummy_session
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            f"/api/v1/media/{uuid4()}",
            headers={"X-User-Id": "test-user"},
        )
        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "MEDIA_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
