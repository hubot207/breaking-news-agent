"""Breaking-news relevance filter.

Rule-based pre-filter first (cheap), LLM classifier only for borderline cases.
This keeps AI costs predictable.
"""
from __future__ import annotations

from src.db import NewsItem
from src.utils.logger import get_logger

log = get_logger(__name__)

BREAKING_KEYWORDS = {
    "breaking", "just in", "urgent", "alert", "live",
    "announced", "confirmed", "reports", "exclusive",
}
NEGATIVE_KEYWORDS = {
    "opinion", "analysis", "how to", "review", "best of",
    "listicle", "horoscope", "recipe",
}


class BreakingNewsFilter:
    """Scores a NewsItem for 'is this breaking?'. Score in [0,1]."""

    def score(self, item: NewsItem) -> float:
        text = f"{item.title} {item.summary or ''}".lower()
        score = 0.0

        # Positive signal
        for kw in BREAKING_KEYWORDS:
            if kw in text:
                score += 0.3

        # Negative signal
        for kw in NEGATIVE_KEYWORDS:
            if kw in text:
                score -= 0.5

        # Recency bonus: newer = more breaking
        if item.published_at:
            from datetime import datetime, timedelta
            age = datetime.utcnow() - item.published_at.replace(tzinfo=None)
            if age < timedelta(hours=1):
                score += 0.4
            elif age < timedelta(hours=6):
                score += 0.2

        # Clamp
        return max(0.0, min(1.0, score))

    def is_breaking(self, item: NewsItem, threshold: float = 0.3) -> bool:
        return self.score(item) >= threshold
