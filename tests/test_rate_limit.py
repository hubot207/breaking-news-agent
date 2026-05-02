"""Tests for the sliding-window async rate limiter."""
import asyncio
import time

import pytest

from src.utils.rate_limit import RateLimiter


async def test_under_limit_no_throttle():
    limiter = RateLimiter(max_requests=5, period_seconds=1.0)
    start = time.monotonic()
    for _ in range(5):
        await limiter.acquire()
    # 5 calls under a 5-per-second cap should not block
    assert time.monotonic() - start < 0.1


async def test_over_limit_throttles():
    limiter = RateLimiter(max_requests=2, period_seconds=0.5)
    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire()
    # The third call must wait for the window to slide
    assert time.monotonic() - start >= 0.4


async def test_disabled_when_zero():
    limiter = RateLimiter(max_requests=0, period_seconds=1.0)
    assert not limiter.enabled
    start = time.monotonic()
    for _ in range(100):
        await limiter.acquire()
    # All calls should pass through immediately
    assert time.monotonic() - start < 0.05


async def test_concurrent_acquire_serialised():
    limiter = RateLimiter(max_requests=3, period_seconds=0.3)

    async def call() -> float:
        await limiter.acquire()
        return time.monotonic()

    start = time.monotonic()
    times = await asyncio.gather(*(call() for _ in range(6)))
    elapsed = time.monotonic() - start
    # 6 calls at 3/window -> at least one full window of waiting
    assert elapsed >= 0.25
    # Calls 4-6 should be later than calls 1-3
    assert min(times[3:]) > max(times[:3])
