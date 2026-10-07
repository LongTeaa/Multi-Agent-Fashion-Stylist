from __future__ import annotations

from collections.abc import Callable
import logging
import threading
import time
from typing import Any

from pydantic import SecretStr

logger = logging.getLogger(__name__)


class GeminiKeyPool:
    """Thread-safe round-robin manager for Gemini API keys with dynamic rate-limit cooldown.

    Features:
    - Round-robin rotation across active keys to distribute RPM quota evenly.
    - Automatic temporary cooldown (default 60s) for keys that receive HTTP 429.
    - Seamless fallback to the earliest-recovering key if all keys are cooling.
    - Thread-safe for concurrent async workers.
    """

    def __init__(
        self,
        api_keys: list[SecretStr],
        cooldown_seconds: float = 60.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._clock = clock
        self._cooldown_seconds = max(1.0, float(cooldown_seconds))
        self._lock = threading.Lock()

        # Deduplicate and filter non-empty keys
        seen_keys: set[str] = set()
        clean_keys: list[SecretStr] = []
        for k in api_keys:
            raw = k.get_secret_value().strip()
            if raw and raw not in seen_keys:
                seen_keys.add(raw)
                clean_keys.append(k)

        if not clean_keys:
            raise ValueError("GeminiKeyPool requires at least one non-empty API key.")

        self._keys: list[SecretStr] = clean_keys
        self._cooldown_until: dict[str, float] = {}  # raw_key -> timestamp
        self._index: int = 0

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    @property
    def keys(self) -> list[SecretStr]:
        return list(self._keys)

    def is_cooling(self, key: SecretStr) -> bool:
        """Check if a specific key is currently in cooldown."""
        with self._lock:
            now = self._clock()
            raw = key.get_secret_value()
            return raw in self._cooldown_until and now < self._cooldown_until[raw]

    @property
    def active_keys_count(self) -> int:
        """Count of keys currently eligible for immediate requests."""
        with self._lock:
            now = self._clock()
            return sum(
                1 for k in self._keys
                if k.get_secret_value() not in self._cooldown_until
                or now >= self._cooldown_until[k.get_secret_value()]
            )

    @property
    def cooling_keys_count(self) -> int:
        """Count of keys currently in rate-limit cooldown."""
        with self._lock:
            now = self._clock()
            return sum(
                1 for k in self._keys
                if k.get_secret_value() in self._cooldown_until
                and now < self._cooldown_until[k.get_secret_value()]
            )

    def get_next_key(self) -> SecretStr:
        """Select the next available key using round-robin.

        If all keys are currently cooling down, returns the key whose cooldown expires earliest.
        """
        with self._lock:
            now = self._clock()
            n = len(self._keys)

            # Try to find the next active key starting from self._index
            for offset in range(n):
                candidate_idx = (self._index + offset) % n
                candidate = self._keys[candidate_idx]
                raw = candidate.get_secret_value()
                expire_time = self._cooldown_until.get(raw, 0.0)

                if now >= expire_time:
                    # Found an active key
                    self._index = (candidate_idx + 1) % n
                    if raw in self._cooldown_until:
                        del self._cooldown_until[raw]
                    return candidate

            # All keys are currently cooling down. Select the one with earliest expiration.
            earliest_key = min(
                self._keys,
                key=lambda k: self._cooldown_until.get(k.get_secret_value(), float("inf")),
            )
            raw_earliest = earliest_key.get_secret_value()
            remaining = max(0.0, self._cooldown_until.get(raw_earliest, now) - now)
            logger.warning(
                "All %d Gemini API keys are in cooldown. Re-using earliest key (remaining cooldown: %.1fs).",
                n,
                remaining,
            )
            self._index = (self._keys.index(earliest_key) + 1) % n
            return earliest_key

    def mark_rate_limited(self, key: SecretStr, custom_cooldown: float | None = None) -> None:
        """Mark a key as rate-limited, placing it into cooldown."""
        with self._lock:
            now = self._clock()
            raw = key.get_secret_value()
            duration = custom_cooldown if custom_cooldown is not None else self._cooldown_seconds
            self._cooldown_until[raw] = now + max(1.0, duration)
            masked = f"{raw[:4]}...{raw[-4:]}" if len(raw) >= 8 else "***"
            logger.warning(
                "Gemini key [%s] marked rate-limited (429). Cooldown for %.1fs until %.1f.",
                masked,
                duration,
                self._cooldown_until[raw],
            )

    def get_pool_status(self) -> dict[str, Any]:
        """Return status snapshot of all keys in the pool."""
        with self._lock:
            now = self._clock()
            statuses: list[dict[str, Any]] = []
            for k in self._keys:
                raw = k.get_secret_value()
                masked = f"{raw[:4]}...{raw[-4:]}" if len(raw) >= 8 else "***"
                expire = self._cooldown_until.get(raw, 0.0)
                cooling = now < expire
                statuses.append({
                    "masked_key": masked,
                    "is_cooling": cooling,
                    "cooldown_remaining_seconds": max(0.0, expire - now) if cooling else 0.0,
                })
            return {
                "total_keys": len(self._keys),
                "active_keys": sum(1 for s in statuses if not s["is_cooling"]),
                "cooling_keys": sum(1 for s in statuses if s["is_cooling"]),
                "keys": statuses,
            }
