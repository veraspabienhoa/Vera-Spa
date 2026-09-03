from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
import time

from vera_web_v2_token_cache import VerifiedTokenCache


def test_verified_token_cache_reuses_a_recent_result():
    now = [10.0]
    calls = []
    cache = VerifiedTokenCache(ttl_seconds=30, clock=lambda: now[0])

    assert cache.get_or_load("secret-token", lambda: calls.append(1) or "user-id") == "user-id"
    assert cache.get_or_load("secret-token", lambda: calls.append(2) or "other-id") == "user-id"
    assert calls == [1]

    now[0] += 31
    assert cache.get_or_load("secret-token", lambda: calls.append(3) or "fresh-id") == "fresh-id"
    assert calls == [1, 3]


def test_verified_token_cache_coalesces_concurrent_verification():
    cache = VerifiedTokenCache(ttl_seconds=30)
    barrier = Barrier(8)
    calls = 0
    calls_lock = Lock()

    def load():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return "user-id"

    def read():
        barrier.wait()
        return cache.get_or_load("same-token", load)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: read(), range(8)))

    assert results == ["user-id"] * 8
    assert calls == 1


def test_verified_token_cache_does_not_cache_failures():
    cache = VerifiedTokenCache(ttl_seconds=30)
    calls = []

    def fail():
        calls.append("fail")
        raise RuntimeError("upstream unavailable")

    try:
        cache.get_or_load("token", fail)
    except RuntimeError:
        pass
    else:
        raise AssertionError("verification failure must be propagated")

    assert cache.get_or_load("token", lambda: calls.append("success") or "user-id") == "user-id"
    assert calls == ["fail", "success"]
