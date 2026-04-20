"""Filter unit tests."""
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


def test_breaking_keywords_score_high():
    f = BreakingNewsFilter()
    item = _make_item("BREAKING: court confirmed ruling")
    assert f.is_breaking(item)


def test_opinion_scored_low():
    f = BreakingNewsFilter()
    item = _make_item("Opinion: why we love X", age_minutes=5)
    assert not f.is_breaking(item)


def test_old_news_less_breaking():
    f = BreakingNewsFilter()
    recent = _make_item("Court confirmed", age_minutes=2)
    old = _make_item("Court confirmed", age_minutes=10_000)
    assert f.score(recent) > f.score(old)
