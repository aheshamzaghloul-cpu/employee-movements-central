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
