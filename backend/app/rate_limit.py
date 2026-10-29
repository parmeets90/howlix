from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
import time


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_seconds: int


class SlidingWindowRateLimiter:
    """Small in-process limiter for the explicitly local single-user deployment."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitResult:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(1, int(window_seconds - (now - events[0])) + 1)
                return RateLimitResult(False, retry_after)
            events.append(now)
            return RateLimitResult(True, 0)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


upload_rate_limiter = SlidingWindowRateLimiter()

