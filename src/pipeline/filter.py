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

# Synapse is positioned as "what builders need to know about AI today."
# These keyword sets reflect that niche - boost AI/tech/dev/builder signals,
# down-rank politics, sports, lifestyle, and pure entertainment.
#
# All matching is substring (`kw in text`). Keep keywords distinctive enough
# to avoid false positives - "ai" by itself would match "said", "again", etc.
# Use base verb forms ("launch") so all conjugations match ("launched",
# "launches", "launching").

# Strong signals this is the AI/tech news our audience cares about.
NEWS_KEYWORDS = {
    # AI-specific terminology
    "llm", "gpt-", "claude", "gemini", "mistral", "llama",
    "fine-tune", "rlhf", "embedding", "transformer",
    "neural network", "deep learning", "machine learning",
    "artificial intelligence", "context window",
    "open-source", "open source", "open-weights",
    "agentic", "multimodal",
    # AI-orbit companies
    "openai", "anthropic", "deepmind", "perplexity",
    "cursor", "huggingface", "hugging face",
    "nvidia", "groq", "cerebras", "stability ai",
    # Dev / infra terms
    "framework", "benchmark", "github", "kubernetes",
    "python", "typescript", "rust",
    "saas", "startup", "yc-backed", "y combinator",
    # News-velocity verb stems
    "release", "launch", "unveil", "announce", "ship",
    "raise", "funding", "valuation", "acquire", "ipo",
}

# Strong signals this isn't for our builder audience.
NEGATIVE_KEYWORDS = {
    # Format flags
    "opinion:", "op-ed", "analysis:", "how to", "guide to",
    "review:", "best of", "top 10", "top ten", "listicle",
    "horoscope", "recipe", "gift guide", "deal alert",
    "sponsored", "advertisement", "promo code",
    # Off-niche topics our audience didn't sign up for
    "celebrity", "royal family", "kardashian",
    "premier league", "world cup", "nba", "nfl",
    "olympics", "match of the day",
    "weather forecast", "lottery",
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
        # opinion/listicle/review reliably fails the default 0.3 threshold,
        # even when the headline also matches a positive news verb).
        for kw in NEGATIVE_KEYWORDS:
            if kw in text:
                score -= 0.7
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
