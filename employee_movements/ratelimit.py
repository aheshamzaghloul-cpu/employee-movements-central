"""Sliding-window rate limiter with optional Redis-backed shared state.

When REDIS_URL is configured, a Redis sorted set enforces one atomic sliding
window across application workers/instances. If Redis temporarily fails, the
limiter falls back to this process and emits a warning; this is a degraded mode,
not a globally enforced limit. Restarting workers clears only the local fallback.
"""

import hashlib
import logging
import secrets
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

_ALLOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  redis.call('PEXPIRE', key, window)
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('PEXPIRE', key, window)
return 1
"""

_BLOCKED_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count == 0 then redis.call('DEL', key) else redis.call('PEXPIRE', key, window) end
if count >= limit then return 1 else return 0 end
"""


class RateLimiter:
    def __init__(self, limit, window_seconds, redis_url=None, key_prefix='employee-movements'):
        self.limit = max(1, int(limit))
        self.window = max(1, int(window_seconds))
        self.redis_url = (redis_url or '').strip() or None
        self.key_prefix = ''.join(c for c in str(key_prefix) if c.isalnum() or c in ':-_') or 'employee-movements'
        self._redis = None
        self._redis_init_attempted = False
        self._redis_retry_after = 0.0
        self._redis_warned = False
        self._hits = {}
        self._cleanup_operations = 0
        self._lock = threading.Lock()

    def _redis_client(self):
        if not self.redis_url or time.monotonic() < self._redis_retry_after:
            return None
        if self._redis is not None:
            return self._redis
        self._redis_init_attempted = True
        try:
            import redis
            self._redis = redis.Redis.from_url(
                self.redis_url,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
                health_check_interval=30,
                decode_responses=False,
            )
            # Fail early on a malformed URL/auth issue; do not wait for a user action.
            self._redis.ping()
            return self._redis
        except Exception as exc:
            self._mark_redis_failure(exc)
            return None

    def _mark_redis_failure(self, exc):
        self._redis = None
        self._redis_retry_after = time.monotonic() + 30.0
        if not self._redis_warned:
            logger.warning(
                'Shared rate-limit Redis backend unavailable; using per-process fallback for up to 30 seconds (%s).',
                type(exc).__name__,
            )
            self._redis_warned = True

    @staticmethod
    def _normalized_key(key):
        # Keep keys bounded and avoid storing raw usernames/IP addresses in Redis or RAM.
        raw = str(key).encode('utf-8', 'replace')[:2048]
        return hashlib.sha256(raw).hexdigest()

    def _try_redis(self, operation, key, *args):
        client = self._redis_client()
        if client is None:
            return None, False
        redis_key = f'{self.key_prefix}:{key}'
        try:
            now_ms = time.time_ns() // 1_000_000
            if operation == 'allow':
                member = f'{now_ms}:{secrets.token_hex(12)}'
                result = client.eval(_ALLOW_LUA, 1, redis_key, now_ms, self.window * 1000, self.limit, member)
            elif operation == 'blocked':
                result = client.eval(_BLOCKED_LUA, 1, redis_key, now_ms, self.window * 1000, self.limit)
            elif operation == 'reset':
                client.delete(redis_key)
                result = 1
            else:
                return None, False
            return result, True
        except Exception as exc:
            self._mark_redis_failure(exc)
            return None, False

    def _cleanup_expired_keys(self, now):
        """Bound stale per-process keys created by clients that never return."""
        self._cleanup_operations += 1
        if self._cleanup_operations % 64:
            return
        for stored_key, stored_hits in list(self._hits.items()):
            while stored_hits and now - stored_hits[0] > self.window:
                stored_hits.popleft()
            if not stored_hits:
                self._hits.pop(stored_key, None)

    def _prune(self, key, now):
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if not hits:
            self._hits.pop(key, None)
        return hits

    def allow(self, key):
        """Record an attempt; return False once limit hits fit in the window."""
        normalized_key = self._normalized_key(key)
        if self.redis_url:
            result, handled = self._try_redis('allow', normalized_key)
            if handled:
                return bool(result)
        now = time.monotonic()
        with self._lock:
            self._cleanup_expired_keys(now)
            hits = self._prune(normalized_key, now)
            if len(hits) >= self.limit:
                return False
            if normalized_key not in self._hits:
                self._hits[normalized_key] = hits
            hits.append(now)
            return True

    def is_blocked(self, key):
        normalized_key = self._normalized_key(key)
        if self.redis_url:
            result, handled = self._try_redis('blocked', normalized_key)
            if handled:
                return bool(result)
        now = time.monotonic()
        with self._lock:
            self._cleanup_expired_keys(now)
            return len(self._prune(normalized_key, now)) >= self.limit

    def reset(self, key):
        normalized_key = self._normalized_key(key)
        if self.redis_url:
            _, handled = self._try_redis('reset', normalized_key)
            if handled:
                return
        with self._lock:
            self._hits.pop(normalized_key, None)
