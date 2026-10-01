"""Small in-process sliding-window rate limiter.

State is per worker process, which is sufficient to blunt password guessing and
to cap paid LLM calls. Use a shared store (for example Redis) if strict global
limits are required.
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit, window_seconds):
        self.limit = limit
        self.window = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key, now):
        hits = self._hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        return hits

    def allow(self, key):
        """Record an attempt; return ``False`` once ``limit`` attempts fit in the window."""
        now = time.monotonic()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def is_blocked(self, key):
        now = time.monotonic()
        with self._lock:
            return len(self._prune(key, now)) >= self.limit

    def reset(self, key):
        with self._lock:
            self._hits.pop(key, None)
