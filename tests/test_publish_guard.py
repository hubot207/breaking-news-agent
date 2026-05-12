"""Tests for the per-platform publish guard."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings
from src.db import Base, NewsItem, Post
from src.publish.guard import can_publish


@pytest.fixture
def session():
    """In-memory SQLite session, fresh schema, cleaned up automatically."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as s:
        yield s


def _seed_post(session: Session, platform: str, posted_at: datetime, status: str = "posted") -> None:
    """Insert one Post row at a given timestamp.

    Each call creates a fresh NewsItem so the (news_item_id, platform) unique
    constraint on the posts table doesn't fire when seeding multiple posts to
    the same platform within a single test.
    """
    ts = posted_at.timestamp()
    item = NewsItem(
        url_hash=f"h-{platform}-{ts}",
        url=f"https://example.com/{platform}/{ts}",
        source="s",
        title="t",
    )
    session.add(item)
    session.flush()
    p = Post(
        news_item_id=item.id,
        platform=platform,
        content="x",
        status=status,
        posted_at=posted_at,
        platform_post_id=f"{platform}-{ts}",
    )
    session.add(p)
    session.commit()


def test_unknown_platform_allowed(session, monkeypatch):
    result = can_publish("unknown", session)
    assert result.allowed
    assert result.reason == ""


def test_no_history_allowed(session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_daily_post_limit", 5)
    monkeypatch.setattr(settings, "telegram_min_interval_min", 30)
    result = can_publish("telegram", session)
    assert result.allowed


def test_under_daily_cap_allowed(session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_daily_post_limit", 5)
    monkeypatch.setattr(settings, "telegram_min_interval_min", 0)
    now = datetime(2026, 5, 3, 12, 0, 0)
    # 3 posts earlier today
    _seed_post(session, "telegram", now - timedelta(hours=3))
    _seed_post(session, "telegram", now - timedelta(hours=2))
    _seed_post(session, "telegram", now - timedelta(hours=1))
    result = can_publish("telegram", session, now=now)
    assert result.allowed


def test_at_daily_cap_blocked(session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_daily_post_limit", 3)
    monkeypatch.setattr(settings, "telegram_min_interval_min", 0)
    now = datetime(2026, 5, 3, 12, 0, 0)
    for h in (3, 2, 1):
        _seed_post(session, "telegram", now - timedelta(hours=h))
    result = can_publish("telegram", session, now=now)
    assert not result.allowed
    assert "daily cap" in result.reason


def test_yesterday_posts_dont_count(session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_daily_post_limit", 3)
    monkeypatch.setattr(settings, "telegram_min_interval_min", 0)
    now = datetime(2026, 5, 3, 12, 0, 0)
    # 5 posts yesterday - should not block today
    yesterday = now - timedelta(days=1)
    for i in range(5):
        _seed_post(session, "telegram", yesterday - timedelta(hours=i))
    result = can_publish("telegram", session, now=now)
    assert result.allowed


def test_failed_posts_dont_count(session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_daily_post_limit", 3)
    monkeypatch.setattr(settings, "telegram_min_interval_min", 0)
    now = datetime(2026, 5, 3, 12, 0, 0)
    # 5 failed attempts today - shouldn't burn cap budget
    for i in range(5):
        _seed_post(session, "telegram", now - timedelta(hours=i + 1), status="failed")
    result = can_publish("telegram", session, now=now)
    assert result.allowed


def test_min_interval_not_met_blocked(session, monkeypatch):
    monkeypatch.setattr(settings, "threads_daily_post_limit", 100)
    monkeypatch.setattr(settings, "threads_min_interval_min", 90)
    monkeypatch.setattr(settings, "threads_jitter_min", 0)
    now = datetime(2026, 5, 3, 12, 0, 0)
    # last post 30 min ago, need 90 min
    _seed_post(session, "threads", now - timedelta(minutes=30))
    result = can_publish("threads", session, now=now)
    assert not result.allowed
    assert "min interval" in result.reason


def test_min_interval_met_allowed(session, monkeypatch):
    monkeypatch.setattr(settings, "threads_daily_post_limit", 100)
    monkeypatch.setattr(settings, "threads_min_interval_min", 90)
    monkeypatch.setattr(settings, "threads_jitter_min", 0)
    now = datetime(2026, 5, 3, 12, 0, 0)
    # last post 95 min ago, need 90 min
    _seed_post(session, "threads", now - timedelta(minutes=95))
    result = can_publish("threads", session, now=now)
    assert result.allowed


def test_zero_cap_means_unlimited(session, monkeypatch):
    monkeypatch.setattr(settings, "telegram_daily_post_limit", 0)
    monkeypatch.setattr(settings, "telegram_min_interval_min", 0)
    now = datetime(2026, 5, 3, 12, 0, 0)
    # 50 posts today - 0 cap means no limit
    for i in range(50):
        _seed_post(session, "telegram", now - timedelta(minutes=i + 1))
    result = can_publish("telegram", session, now=now)
    assert result.allowed


def test_jitter_is_deterministic_per_last_post(session, monkeypatch):
    """Same last_posted_at must produce same guard answer across calls."""
    monkeypatch.setattr(settings, "threads_daily_post_limit", 100)
    monkeypatch.setattr(settings, "threads_min_interval_min", 90)
    monkeypatch.setattr(settings, "threads_jitter_min", 30)
    now = datetime(2026, 5, 3, 12, 0, 0)
    _seed_post(session, "threads", now - timedelta(minutes=100))

    # Multiple calls with same data must agree.
    results = [can_publish("threads", session, now=now) for _ in range(5)]
    assert all(r.allowed == results[0].allowed for r in results)
    if not results[0].allowed:
        assert all(r.reason == results[0].reason for r in results)


def test_jitter_can_extend_blocking_past_base_interval(session, monkeypatch):
    """With jitter, effective interval can exceed the base min interval.

    Base=90, jitter=30 means effective is 90-120 min. A 100-min-old post may
    or may not be allowed depending on the jitter roll. This test seeds many
    different last_posted_at values to verify that at least one of them is
    blocked at 100 min (proving the interval can extend beyond 90).
    """
    monkeypatch.setattr(settings, "threads_daily_post_limit", 100)
    monkeypatch.setattr(settings, "threads_min_interval_min", 90)
    monkeypatch.setattr(settings, "threads_jitter_min", 30)
    blocked_count = 0
    for i in range(60):
        # Use different timestamps so different jitter seeds fire
        post_time = datetime(2026, 5, 3, 10, i, 0)
        now = post_time + timedelta(minutes=100)
        # Clear and re-seed each iteration
        session.query(Post).delete()
        session.commit()
        _seed_post(session, "threads", post_time)
        r = can_publish("threads", session, now=now)
        if not r.allowed:
            blocked_count += 1
    # With jitter 0-30 and elapsed=100, blocking should happen when jitter > 10
    # That's roughly 2/3 of seeds. Should see at least 20 out of 60 blocked.
    assert blocked_count > 20, f"expected >20 blocked, got {blocked_count}"
    assert blocked_count < 60, f"expected <60 blocked, got {blocked_count}"


def test_jitter_zero_is_same_as_no_jitter(session, monkeypatch):
    """jitter=0 falls back to plain min-interval behavior."""
    monkeypatch.setattr(settings, "threads_daily_post_limit", 100)
    monkeypatch.setattr(settings, "threads_min_interval_min", 90)
    monkeypatch.setattr(settings, "threads_jitter_min", 0)
    now = datetime(2026, 5, 3, 12, 0, 0)
    # exactly 90 min old: should be allowed (>= threshold)
    _seed_post(session, "threads", now - timedelta(minutes=91))
    assert can_publish("threads", session, now=now).allowed
    session.query(Post).delete()
    session.commit()
    # 89 min old: should be blocked
    _seed_post(session, "threads", now - timedelta(minutes=89))
    assert not can_publish("threads", session, now=now).allowed
