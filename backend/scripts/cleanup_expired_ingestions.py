from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from sqlmodel import Session

from app.core.database import get_engine
from app.core.dependencies import get_object_storage
from app.repositories.object_storage import ObjectStorage
from app.services.cleanup_service import CleanupSummary, cleanup_expired_batches

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cleanup_expired_ingestions")


def run_cleanup(
    *,
    session: Session | None = None,
    storage: ObjectStorage | None = None,
    current_time: datetime | None = None,
) -> CleanupSummary:
    """Execute expired batches cleanup with provided or default session and storage."""
    active_storage = storage or get_object_storage()

    if session is not None:
        return cleanup_expired_batches(
            session=session,
            storage=active_storage,
            current_time=current_time,
        )

    engine = get_engine()
    with Session(engine) as active_session:
        return cleanup_expired_batches(
            session=active_session,
            storage=active_storage,
            current_time=current_time,
        )


def main(
    argv: list[str] | None = None,
    *,
    session: Session | None = None,
    storage: ObjectStorage | None = None,
) -> int:
    """CLI entrypoint to run scheduled or manual expired ingestion cleanup.

    Returns:
        0: If cleanup completed with zero failures.
        1: If any transient or retryable failures occurred.
        2: If command-line arguments are invalid.
    """
    parser = argparse.ArgumentParser(
        description="Clean up expired unconfirmed ingestion batches and delete transient media assets."
    )
    parser.add_argument(
        "--current-time",
        type=str,
        default=None,
        help="Optional ISO-formatted current time override for testing (e.g., 2026-09-08T12:00:00Z).",
    )
    args = parser.parse_args(argv)

    current_time: datetime | None = None
    if args.current_time:
        try:
            current_time = datetime.fromisoformat(args.current_time)
        except ValueError as err:
            logger.error("Invalid ISO format for --current-time: %s", err)
            return 2

    logger.info("Starting expired ingestion cleanup job...")
    try:
        summary = run_cleanup(
            session=session,
            storage=storage,
            current_time=current_time,
        )
    except Exception as err:
        logger.error("Catastrophic error running cleanup: %s", err)
        return 1

    logger.info(
        "Cleanup completed: %d batches expired, %d objects deleted, %d failure(s).",
        summary.batches_expired,
        summary.objects_deleted,
        len(summary.failures),
    )

    if summary.failures:
        for fail in summary.failures:
            logger.error("Retryable failure: %s", fail)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
