from employee_movements.ratelimit import RateLimiter


def test_blocks_after_limit_and_resets():
    limiter = RateLimiter(limit=2, window_seconds=60)
    assert limiter.allow('k') and limiter.allow('k')
    assert not limiter.allow('k')
    assert limiter.is_blocked('k')
    limiter.reset('k')
    assert limiter.allow('k')


def test_keys_are_independent():
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.allow('a')
    assert limiter.allow('b')


def test_window_expires(monkeypatch):
    import employee_movements.ratelimit as mod

    now = [1000.0]
    monkeypatch.setattr(mod.time, 'monotonic', lambda: now[0])
    limiter = RateLimiter(limit=1, window_seconds=10)
    assert limiter.allow('k')
    assert not limiter.allow('k')
    now[0] += 11
    assert limiter.allow('k')


class FakeRedisForLimiter:
    def __init__(self):
        self.calls = []
        self.deleted = []

    def ping(self):
        return True

    def eval(self, script, numkeys, key, *args):
        self.calls.append((script, numkeys, key, args))
        if 'ZADD' in script:
            return 1
        return 0

    def delete(self, key):
        self.deleted.append(key)
        return 1


def test_redis_backend_uses_hashed_keys_and_atomic_scripts():
    limiter = RateLimiter(limit=2, window_seconds=60, redis_url='redis://unused/0')
    fake = FakeRedisForLimiter()
    limiter._redis = fake

    assert limiter.allow('sensitive-user@example.invalid') is True
    assert limiter.is_blocked('sensitive-user@example.invalid') is False
    limiter.reset('sensitive-user@example.invalid')

    assert len(fake.calls) == 2
    assert 'sensitive-user@example.invalid' not in fake.calls[0][2]
    assert 'ZREMRANGEBYSCORE' in fake.calls[0][0]
    assert fake.deleted and 'sensitive-user@example.invalid' not in fake.deleted[0]
