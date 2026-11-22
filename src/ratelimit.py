"""Thread-safe minimum-interval limiter. Fail closed on burst."""

from __future__ import annotations

import threading
import time

from .config import MIN_INTERVAL_SECONDS


class RateLimitError(Exception):
    """Raised when calls arrive faster than the configured interval."""


class MinIntervalLimiter:
    def __init__(self, interval: float = MIN_INTERVAL_SECONDS) -> None:
        self.interval = interval
        self._last = 0.0
        self._lock = threading.Lock()

    def check(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now - self._last < self.interval:
                raise RateLimitError("Too many requests. Try again shortly.")
            self._last = now
