"""Publishability filter.

Decides whether a fresh news item is worth sending to the LLM rewriter.

Design: default to "probably publishable" and subtract for clear non-news
markers (opinion, listicle, review). This matches how real news headlines
actually read - most don't include the word "breaking" but are still
genuinely newsworthy. The threshold is configurable via settings.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from src.config import settings
from src.db import NewsItem
from src.utils.logger import get_logger

log = get_logger(__name__)

# Strong signals an item IS time-sensitive news (small bonus on top of baseline).
NEWS_KEYWORDS = {
    "breaking", "just in", "urgent", "alert", "announced",
    "confirmed", "reports", "exclusive", "launches", "unveils",
    "reveals", "killed", "dies", "wins", "passes", "approves",
    "rejects", "resigns", "elected", "raids", "arrested",
}

# Strong signals an item is NOT time-sensitive news (opinion, evergreen, listicle).
NEGATIVE_KEYWORDS = {
    "opinion", "op-ed", "analysis: ", "how to", "guide to",
    "review:", "best of", "top 10", "top ten", "listicle",
    "horoscope", "recipe", "gift guide", "deal alert",
    "sponsored", "advertisement", "promo code",
}


class BreakingNewsFilter:
    """Scores a NewsItem for 'is this worth publishing?'. Score in [0, 1].

    Defaults to a baseline of 0.5 (publishable), then nudges up for news
    markers and down for non-news markers, with recency factored in.
    """

    BASELINE = 0.5

    def score(self, item: NewsItem) -> float:
        text = f"{item.title} {item.summary or ''}".lower()
        score = self.BASELINE

        # Positive signal: explicit news verbs/markers
        for kw in NEWS_KEYWORDS:
            if kw in text:
                score += 0.15
                break  # one bonus is enough; don't pile up

        # Negative signal: clear non-news markers (strong penalty so a recent
        # opinion/listicle/review reliably fails the default 0.3 threshold).
        for kw in NEGATIVE_KEYWORDS:
            if kw in text:
                score -= 0.5
                break

        # Recency: bonus for fresh, penalty for stale.
        if item.published_at:
            age = datetime.utcnow() - item.published_at.replace(tzinfo=None)
            if age < timedelta(hours=2):
                score += 0.2
            elif age < timedelta(hours=12):
                score += 0.05
            elif age > timedelta(hours=48):
                score -= 0.4  # stale

        return max(0.0, min(1.0, score))

    def is_breaking(self, item: NewsItem, threshold: float | None = None) -> bool:
        t = threshold if threshold is not None else settings.breaking_filter_threshold
        return self.score(item) >= t
