"""Per-platform publish guards.

Before each adapter publish call, three checks are applied:

1. Daily cap: how many successful posts have we made to this platform today
   (UTC midnight reset)? If we're already at or above the configured limit,
   skip.
2. Min interval: how long since our last successful post to this platform?
   If less than the configured minimum, skip.
3. Jitter: an extra 0..jitter_max minutes is added to the min interval per
   post, seeded by the previous post's timestamp so the same input gives
   the same answer (retries are stable). This makes the actual gap between
   posts vary instead of being exactly N minutes every time, which is the
   biggest "this is a bot" tell to anti-spam classifiers.

Both checks read the existing `posts` table — no schema migration required.
A "successful post" is `posts.status == 'posted'`.

When a guard fails for one platform, the item still publishes to other
enabled platforms whose guards allow it. No queueing, no deferral — late
items just don't post until tomorrow's cap resets.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.config import settings
from src.db import Post
from src.utils.logger import get_logger

log = get_logger(__name__)


class GuardResult(NamedTuple):
    """Outcome of a publish-guard check."""

    allowed: bool
    reason: str  # empty when allowed; human-readable when blocked


# Maps platform name to (daily_cap_attr, min_interval_attr, jitter_attr).
_PLATFORM_CONFIG: dict[str, tuple[str, str, str]] = {
    "telegram": (
        "telegram_daily_post_limit",
        "telegram_min_interval_min",
        "telegram_jitter_min",
    ),
    "threads": (
        "threads_daily_post_limit",
        "threads_min_interval_min",
        "threads_jitter_min",
    ),
    "x": (
        "x_daily_post_limit",
        "x_min_interval_min",
        "x_jitter_min",
    ),
}


def _effective_interval_minutes(
    base_min: int, jitter_max: int, last_posted_at: datetime
) -> float:
    """Return min_interval plus a deterministic random 0..jitter_max minutes.

    Seeded on `last_posted_at` so the same previous-post timestamp always
    yields the same effective interval. This means:
      - Retries of the guard get the same answer (idempotent).
      - Successive posts get different intervals (different seeds), breaking
        the clockwork pattern.
    """
    if jitter_max <= 0:
        return float(base_min)
    # Seed with the last post's microsecond-precision timestamp.
    # Using timestamp() (float) preserves precision better than int().
    seed = last_posted_at.timestamp()
    rng = random.Random(seed)
    return base_min + rng.uniform(0, jitter_max)


def can_publish(platform: str, session: Session, now: datetime | None = None) -> GuardResult:
    """Check whether publishing to `platform` is allowed right now.

    `now` is injectable for tests; defaults to UTC now.
    Unknown platforms default to allowed (no guard configured).
    """
    if platform not in _PLATFORM_CONFIG:
        return GuardResult(True, "")

    cap_attr, interval_attr, jitter_attr = _PLATFORM_CONFIG[platform]
    daily_cap: int = getattr(settings, cap_attr)
    min_interval_min: int = getattr(settings, interval_attr)
    jitter_max_min: int = getattr(settings, jitter_attr, 0)

    now = now or datetime.utcnow()

    # Check 1: daily cap (0 = unlimited)
    if daily_cap > 0:
        today_start = datetime(now.year, now.month, now.day)
        daily_count = session.execute(
            select(func.count(Post.id)).where(
                Post.platform == platform,
                Post.status == "posted",
                Post.posted_at >= today_start,
            )
        ).scalar_one()
        if daily_count >= daily_cap:
            return GuardResult(
                False, f"daily cap reached ({daily_count}/{daily_cap})"
            )

    # Check 2: min interval (with optional deterministic jitter) since last
    # successful post. 0 = no interval check.
    if min_interval_min > 0:
        last_posted_at = session.execute(
            select(func.max(Post.posted_at)).where(
                Post.platform == platform,
                Post.status == "posted",
            )
        ).scalar()
        if last_posted_at is not None:
            effective_min = _effective_interval_minutes(
                min_interval_min, jitter_max_min, last_posted_at
            )
            elapsed = now - last_posted_at
            effective_interval = timedelta(minutes=effective_min)
            if elapsed < effective_interval:
                elapsed_min = elapsed.total_seconds() / 60
                remaining_min = (effective_interval - elapsed).total_seconds() / 60
                return GuardResult(
                    False,
                    f"min interval not met "
                    f"(last post {elapsed_min:.1f}min ago, "
                    f"need {effective_min:.0f}min, "
                    f"{remaining_min:.1f}min remaining)",
                )

    return GuardResult(True, "")
