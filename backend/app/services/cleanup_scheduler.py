from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from time import monotonic

from app.services.cleanup_service import run_cleanup

logger = logging.getLogger("cleanup_scheduler")


@dataclass
class CleanupMetrics:
    last_run_at: str | None = None
    last_status: str = "idle"  # idle | success | warning | error
    total_runs: int = 0
    batches_expired_total: int = 0
    objects_deleted_total: int = 0
    failed_objects_total: int = 0
    last_run_duration_seconds: float = 0.0
    is_running: bool = False
    consecutive_failures: int = 0
    scheduler_active: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


_METRICS = CleanupMetrics()
_SCHEDULER_TASK: asyncio.Task | None = None


def get_cleanup_metrics() -> CleanupMetrics:
    """Return snapshot of runtime cleanup scheduler metrics."""
    return CleanupMetrics(**asdict(_METRICS))


def reset_cleanup_metrics() -> None:
    """Reset metrics for testing purposes."""
    global _METRICS
    _METRICS = CleanupMetrics()


def execute_scheduled_cleanup_cycle() -> dict:
    """Synchronously execute one cleanup cycle and update in-memory metrics."""
    global _METRICS

    started_at = monotonic()
    _METRICS.is_running = True
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        summary = run_cleanup()
        duration = round(monotonic() - started_at, 3)

        _METRICS.last_run_at = now_iso
        _METRICS.total_runs += 1
        _METRICS.last_run_duration_seconds = duration
        _METRICS.batches_expired_total += summary.batches_expired
        _METRICS.objects_deleted_total += summary.objects_deleted
        _METRICS.failed_objects_total += len(summary.failures)

        if summary.failures:
            _METRICS.last_status = "warning"
            _METRICS.consecutive_failures += 1
            logger.warning(
                "Scheduled cleanup cycle finished with %d retryable failures: %s",
                len(summary.failures),
                "; ".join(summary.failures[:3]),
            )
        else:
            _METRICS.last_status = "success"
            _METRICS.consecutive_failures = 0
            logger.info(
                "Scheduled cleanup cycle completed successfully in %.3fs (%d expired, %d deleted).",
                duration,
                summary.batches_expired,
                summary.objects_deleted,
            )

        return {
            "status": _METRICS.last_status,
            "batches_expired": summary.batches_expired,
            "objects_deleted": summary.objects_deleted,
            "failures": summary.failures,
            "duration_seconds": duration,
        }

    except Exception as exc:
        duration = round(monotonic() - started_at, 3)
        _METRICS.last_run_at = now_iso
        _METRICS.total_runs += 1
        _METRICS.last_run_duration_seconds = duration
        _METRICS.last_status = "error"
        _METRICS.consecutive_failures += 1
        logger.error("Catastrophic error in scheduled cleanup cycle: %s", exc, exc_info=True)
        return {
            "status": "error",
            "batches_expired": 0,
            "objects_deleted": 0,
            "failures": [str(exc)],
            "duration_seconds": duration,
        }
    finally:
        _METRICS.is_running = False


async def cleanup_scheduler_loop(interval_seconds: int) -> None:
    """Async background task that runs periodic cleanup cycles."""
    global _METRICS
    _METRICS.scheduler_active = True
    logger.info("Cleanup scheduler background worker started with interval=%ds", interval_seconds)

    try:
        while True:
            await asyncio.sleep(interval_seconds)
            # Offload synchronous DB + storage cleanup to threadpool to not block asyncio event loop
            await asyncio.to_thread(execute_scheduled_cleanup_cycle)
    except asyncio.CancelledError:
        logger.info("Cleanup scheduler background worker received cancellation.")
        raise
    finally:
        _METRICS.scheduler_active = False


def start_cleanup_scheduler(interval_seconds: int) -> asyncio.Task | None:
    """Launch the cleanup background loop if not already running."""
    global _SCHEDULER_TASK, _METRICS
    if _SCHEDULER_TASK is not None and not _SCHEDULER_TASK.done():
        return _SCHEDULER_TASK

    try:
        loop = asyncio.get_running_loop()
        _METRICS.scheduler_active = True
        _SCHEDULER_TASK = loop.create_task(cleanup_scheduler_loop(interval_seconds))
        return _SCHEDULER_TASK
    except RuntimeError:
        logger.warning("No running asyncio event loop; cleanup scheduler not started.")
        return None


async def stop_cleanup_scheduler() -> None:
    """Gracefully cancel and await the cleanup background loop."""
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK is not None and not _SCHEDULER_TASK.done():
        _SCHEDULER_TASK.cancel()
        try:
            await _SCHEDULER_TASK
        except asyncio.CancelledError:
            pass
        finally:
            _SCHEDULER_TASK = None
            _METRICS.scheduler_active = False
