"""RSS feed ingester. Free, reliable, universally supported."""
from __future__ import annotations

import asyncio
from datetime import datetime
from time import mktime
from typing import Iterable

import feedparser

from src.ingesters.base import BaseIngester, RawItem
from src.utils.logger import get_logger

log = get_logger(__name__)


class RSSIngester(BaseIngester):
    name = "rss"

    def __init__(self, urls: list[str]) -> None:
        self.urls = urls

    async def fetch(self) -> Iterable[RawItem]:
        """Fetch all configured feeds in parallel (feedparser is sync, so use a thread)."""
        items: list[RawItem] = []
        results = await asyncio.gather(
            *(asyncio.to_thread(self._fetch_one, url) for url in self.urls),
            return_exceptions=True,
        )
        for url, result in zip(self.urls, results):
            if isinstance(result, Exception):
                log.warning("rss_fetch_failed", url=url, error=str(result))
                continue
            items.extend(result)
        log.info("rss_fetched", count=len(items), feeds=len(self.urls))
        return items

    def _fetch_one(self, url: str) -> list[RawItem]:
        feed = feedparser.parse(url)
        out: list[RawItem] = []
        for entry in feed.entries:
            published: datetime | None = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime.fromtimestamp(mktime(entry.published_parsed))
            out.append(
                RawItem(
                    url=entry.get("link", ""),
                    title=entry.get("title", "").strip(),
                    source=feed.feed.get("title", url),
                    summary=entry.get("summary"),
                    published_at=published,
                )
            )
        return out
