"""News source ingesters. Each ingester yields NewsItem dicts."""
from __future__ import annotations

from src.ingesters.base import BaseIngester, RawItem
from src.ingesters.rss import RSSIngester
from src.ingesters.newsapi import NewsAPIIngester

__all__ = ["BaseIngester", "RawItem", "RSSIngester", "NewsAPIIngester"]


def get_enabled_ingesters() -> list[BaseIngester]:
    """Returns a list of ingesters based on what's configured in settings."""
    from src.config import settings

    ingesters: list[BaseIngester] = []
    if settings.rss_feed_list:
        ingesters.append(RSSIngester(urls=settings.rss_feed_list))
    if settings.newsapi_key:
        ingesters.append(NewsAPIIngester(api_key=settings.newsapi_key))
    return ingesters
