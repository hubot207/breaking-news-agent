"""Publishability filter unit tests."""
from datetime import datetime, timedelta

from src.db import NewsItem
from src.pipeline.filter import BreakingNewsFilter


def _make_item(title: str, summary: str = "", age_minutes: int = 5) -> NewsItem:
    return NewsItem(
        url_hash="h",
        url="https://x/",
        source="s",
        title=title,
        summary=summary,
        published_at=datetime.utcnow() - timedelta(minutes=age_minutes),
    )


def test_plain_news_headline_passes():
    """Default-publishable: a normal headline with no flags should be kept."""
    f = BreakingNewsFilter()
    item = _make_item("Apple unveils new Vision Pro 2 with 50% lower price")
    assert f.is_breaking(item)


def test_explicit_breaking_keyword_passes():
    f = BreakingNewsFilter()
    item = _make_item("BREAKING: court confirms ruling on tech antitrust")
    assert f.is_breaking(item)


def test_opinion_dropped():
    f = BreakingNewsFilter()
    item = _make_item("Opinion: why we love new gadgets")
    assert not f.is_breaking(item)


def test_listicle_dropped():
    f = BreakingNewsFilter()
    item = _make_item("Top 10 cookbooks of 2026")
    assert not f.is_breaking(item)


def test_review_dropped():
    f = BreakingNewsFilter()
    item = _make_item("Review: the new Vision Pro is good but expensive")
    assert not f.is_breaking(item)


def test_stale_news_dropped():
    f = BreakingNewsFilter()
    very_old = _make_item("Apple unveils product", age_minutes=72 * 60)
    assert not f.is_breaking(very_old)


def test_recent_outscores_old():
    f = BreakingNewsFilter()
    recent = _make_item("Court confirms ruling", age_minutes=2)
    old = _make_item("Court confirms ruling", age_minutes=24 * 60)
    assert f.score(recent) > f.score(old)


def test_threshold_argument_overrides_default():
    f = BreakingNewsFilter()
    item = _make_item("Apple unveils new product")
    assert f.is_breaking(item, threshold=0.1)
    # with a very strict threshold, the same item is dropped
    assert not f.is_breaking(item, threshold=0.95)
