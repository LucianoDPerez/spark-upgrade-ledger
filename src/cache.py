"""Thread-safe in-memory TTL cache. Fail closed on errors."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, TypeVar

from .config import CACHE_TTL_SECONDS

T = TypeVar("T")


@dataclass(frozen=True)
class _Entry:
    value: Any
    expires_at: float


class TTLCache:
    def __init__(self, ttl: float = CACHE_TTL_SECONDS) -> None:
        self.ttl = ttl
        self._store: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if entry.expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = _Entry(value=value, expires_at=time.monotonic() + self.ttl)
