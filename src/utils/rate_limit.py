"""Async sliding-window rate limiter.

Used to cap LLM API calls below the provider's per-minute quota, preventing
both burst-induced 429s and accidental cost spikes from a runaway loop.

Usage:

    limiter = RateLimiter(max_requests=60, period_seconds=60.0)
    async def call_api():
        await limiter.acquire()
        return await openai_client.chat.completions.create(...)
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Optional

from src.utils.logger import get_logger

log = get_logger(__name__)


class RateLimiter:
    """Sliding-window limiter. At most max_requests calls in any rolling window
    of period_seconds. Calls beyond that block until the window slides forward.
    """

    def __init__(self, max_requests: int, period_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.period = period_seconds
        self._timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.max_requests > 0

    async def acquire(self) -> None:
        """Block until a slot is available, then record the call."""
        if not self.enabled:
            return
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self.period
            # Drop expired entries
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) >= self.max_requests:
                # Wait until the oldest call exits the window
                wait_for = self._timestamps[0] + self.period - now + 0.05
                log.info(
                    "rate_limit_throttled",
                    waiting_seconds=round(wait_for, 2),
                    in_window=len(self._timestamps),
                    max_requests=self.max_requests,
                )
                await asyncio.sleep(wait_for)
                # Recompute after sleeping
                now = time.monotonic()
                cutoff = now - self.period
                while self._timestamps and self._timestamps[0] <= cutoff:
                    self._timestamps.popleft()
            self._timestamps.append(now)


# Process-wide singleton (created lazily so settings is fully imported first)
_LLM_LIMITER: Optional[RateLimiter] = None


def get_llm_limiter() -> RateLimiter:
    """Returns the shared LLM limiter, configured from settings."""
    global _LLM_LIMITER
    if _LLM_LIMITER is None:
        from src.config import settings

        _LLM_LIMITER = RateLimiter(
            max_requests=settings.ai_rate_limit_rpm, period_seconds=60.0
        )
    return _LLM_LIMITER
