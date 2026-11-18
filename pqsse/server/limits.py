"""Request rate limits: a token bucket per key (a receiver credential, or a client address)."""
from __future__ import annotations

import threading
import time
from typing import Callable


class RateLimiter:
    """``per_minute`` requests per key, with bursts up to the same number. Thread safe."""

    def __init__(self, per_minute: int, clock: Callable[[], float] = time.monotonic, max_keys: int = 100_000) -> None:
        self.rate = per_minute / 60.0
        self.capacity = float(per_minute)
        self.clock = clock
        self.max_keys = max_keys
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        """(allowed, seconds to wait before the next request would be allowed)."""
        if self.rate <= 0:
            return True, 0.0
        now = self.clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                allowed, wait = True, 0.0
            else:
                self._buckets[key] = (tokens, now)
                allowed, wait = False, (1.0 - tokens) / self.rate
            if len(self._buckets) > self.max_keys:          # forget the oldest keys rather than grow without bound
                for old in sorted(self._buckets, key=lambda k: self._buckets[k][1])[: self.max_keys // 10]:
                    del self._buckets[old]
        return allowed, wait
