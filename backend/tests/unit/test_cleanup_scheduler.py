from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cleanup_scheduler import (
    CleanupMetrics,
    execute_scheduled_cleanup_cycle,
    get_cleanup_metrics,
    reset_cleanup_metrics,
    start_cleanup_scheduler,
    stop_cleanup_scheduler,
)
from app.services.cleanup_service import CleanupSummary


@pytest.fixture(autouse=True)
def reset_metrics_before_and_after():
    reset_cleanup_metrics()
    yield
    reset_cleanup_metrics()


def test_cleanup_scheduler_metrics_success():
    """Verify metrics update on successful cleanup run."""
    fake_summary = CleanupSummary(
        batches_expired=2,
        objects_deleted=5,
        failures=[],
    )

    with patch("app.services.cleanup_scheduler.run_cleanup", return_value=fake_summary):
        result = execute_scheduled_cleanup_cycle()

    assert result["status"] == "success"
    assert result["batches_expired"] == 2
    assert result["objects_deleted"] == 5
    assert result["failures"] == []

    metrics = get_cleanup_metrics()
    assert metrics.total_runs == 1
    assert metrics.last_status == "success"
    assert metrics.batches_expired_total == 2
    assert metrics.objects_deleted_total == 5
    assert metrics.failed_objects_total == 0
    assert metrics.consecutive_failures == 0
    assert metrics.last_run_at is not None
    assert metrics.last_run_duration_seconds >= 0.0


def test_cleanup_scheduler_metrics_with_retryable_failures():
    """Verify warning status and failure metric tracking when transient errors occur."""
    fake_summary = CleanupSummary(
        batches_expired=1,
        objects_deleted=2,
        failures=["Object storage timeout on user-1/item-1"],
    )

    with patch("app.services.cleanup_scheduler.run_cleanup", return_value=fake_summary):
        result = execute_scheduled_cleanup_cycle()

    assert result["status"] == "warning"
    assert len(result["failures"]) == 1

    metrics = get_cleanup_metrics()
    assert metrics.total_runs == 1
    assert metrics.last_status == "warning"
    assert metrics.failed_objects_total == 1
    assert metrics.consecutive_failures == 1


def test_cleanup_scheduler_catastrophic_error():
    """Verify error status when cleanup execution raises an unhandled exception."""
    with patch("app.services.cleanup_scheduler.run_cleanup", side_effect=RuntimeError("Database connection lost")):
        result = execute_scheduled_cleanup_cycle()

    assert result["status"] == "error"
    assert "Database connection lost" in result["failures"][0]

    metrics = get_cleanup_metrics()
    assert metrics.total_runs == 1
    assert metrics.last_status == "error"
    assert metrics.consecutive_failures == 1


def test_start_and_stop_cleanup_scheduler():
    """Verify background worker task starts and stops gracefully without leaking."""
    async def _run():
        task = start_cleanup_scheduler(interval_seconds=3600)
        assert task is not None
        assert not task.done()

        metrics = get_cleanup_metrics()
        assert metrics.scheduler_active is True

        await stop_cleanup_scheduler()
        assert task.done()

    asyncio.run(_run())


def test_system_cleanup_metrics_endpoint():
    """Verify GET /api/v1/system/cleanup-metrics returns current operational metrics."""
    client = TestClient(app)
    response = client.get("/api/v1/system/cleanup-metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert "last_status" in data["data"]
    assert "batches_expired_total" in data["data"]
    assert "objects_deleted_total" in data["data"]
    assert "failed_objects_total" in data["data"]
