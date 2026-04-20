"""NewsAPI.org ingester. Paid tier for high coverage; the free tier works for dev."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

import httpx

from src.ingesters.base import BaseIngester, RawItem
from src.utils.logger import get_logger

log = get_logger(__name__)


class NewsAPIIngester(BaseIngester):
    name = "newsapi"
    BASE = "https://newsapi.org/v2/top-headlines"

    def __init__(self, api_key: str, country: str = "us") -> None:
        self.api_key = api_key
        self.country = country

    async def fetch(self) -> Iterable[RawItem]:
        params = {"country": self.country, "pageSize": 50, "apiKey": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(self.BASE, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            log.warning("newsapi_fetch_failed", error=str(e))
            return []

        items: list[RawItem] = []
        for art in data.get("articles", []):
            published = None
            if art.get("publishedAt"):
                try:
                    published = datetime.fromisoformat(art["publishedAt"].replace("Z", "+00:00"))
                except ValueError:
                    pass
            items.append(
                RawItem(
                    url=art.get("url", ""),
                    title=(art.get("title") or "").strip(),
                    source=(art.get("source") or {}).get("name", "newsapi"),
                    summary=art.get("description"),
                    published_at=published,
                )
            )
        log.info("newsapi_fetched", count=len(items))
        return items
