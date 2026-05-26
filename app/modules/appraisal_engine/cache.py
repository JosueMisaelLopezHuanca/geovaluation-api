from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheItem:
    value: Any
    expires_at: float


class TTLMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, CacheItem] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if not item:
            return None
        if item.expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        return item.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> Any:
        self._store[key] = CacheItem(value=value, expires_at=time.monotonic() + ttl_seconds)
        return value

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> None:
        for key in list(self._store.keys()):
            if key.startswith(prefix):
                self._store.pop(key, None)


appraisal_cache = TTLMemoryCache()
