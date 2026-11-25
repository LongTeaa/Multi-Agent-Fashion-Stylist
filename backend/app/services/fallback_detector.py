"""Detector that falls back to a secondary detector only when the primary one fails."""

from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Lock

from app.services.providers import DetectionResult, DetectorProtocol

logger = logging.getLogger(__name__)


class FallbackDetector:
    """Call the primary detector; on any exception, call the secondary detector once.

    A primary result without boxes is a valid answer and is returned unchanged. The
    secondary detector is built lazily, so its model is loaded only after the first
    primary failure. When the secondary also fails, the primary error is raised so the
    caller's manual-review fallback applies.
    """

    def __init__(
        self,
        primary: DetectorProtocol,
        secondary_factory: Callable[[], DetectorProtocol],
        *,
        primary_name: str,
        secondary_name: str,
    ) -> None:
        self._primary = primary
        self._secondary_factory = secondary_factory
        self._secondary: DetectorProtocol | None = None
        self._lock = Lock()
        self.primary_name = primary_name
        self.secondary_name = secondary_name

    def _get_secondary(self) -> DetectorProtocol:
        with self._lock:
            if self._secondary is None:
                self._secondary = self._secondary_factory()
            return self._secondary

    def detect(self, image_bytes: bytes) -> DetectionResult:
        try:
            return self._primary.detect(image_bytes)
        except Exception as primary_error:
            # Only the exception type is logged: provider messages may echo response bodies.
            logger.warning(
                "Detector '%s' failed (%s); falling back to '%s'.",
                self.primary_name,
                type(primary_error).__name__,
                self.secondary_name,
            )
            try:
                return self._get_secondary().detect(image_bytes)
            except Exception as secondary_error:
                logger.warning(
                    "Fallback detector '%s' also failed (%s).",
                    self.secondary_name,
                    type(secondary_error).__name__,
                )
                raise primary_error from secondary_error
