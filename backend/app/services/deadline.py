"""Wall-clock deadlines for blocking provider calls.

httpx timeouts apply per phase (connect, each read, write, pool), so a server that
trickles bytes can keep one request open far longer than its configured timeout. This
helper bounds the total time the caller waits. The worker thread is not killed: it
finishes once httpx's own per-phase timeout fires, and its result is discarded.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TypeVar

T = TypeVar("T")

# Bounded so that a provider that keeps stalling cannot create unbounded threads; a
# queued call still times out from the moment it was submitted.
_EXECUTOR = ThreadPoolExecutor(max_workers=16, thread_name_prefix="provider-deadline")


def call_with_deadline(fn: Callable[[], T], seconds: float, *, message: str) -> T:
    """Return ``fn()`` or raise ``TimeoutError(message)`` after ``seconds`` of wall time."""
    if seconds <= 0:
        raise TimeoutError(message)
    future = _EXECUTOR.submit(fn)
    try:
        return future.result(timeout=seconds)
    except FutureTimeoutError:
        future.cancel()
        raise TimeoutError(message) from None
