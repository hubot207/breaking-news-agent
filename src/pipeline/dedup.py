"""Deduplication layer. The URL hash is the source of truth for `have I seen this?`."""
from __future__ import annotations

import hashlib
from typing import Iterable
from urllib.parse import urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import NewsItem
from src.ingesters.base import RawItem
from src.utils.logger import get_logger

log = get_logger(__name__)


def _normalize_url(url: str) -> str:
    """Strip query strings & fragments so equivalent URLs hash equally."""
    p = urlparse(url.strip().lower())
    return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(_normalize_url(url).encode()).hexdigest()


class Deduplicator:
    """Keeps a short in-memory cache of recent hashes to avoid hitting the DB every time."""

    def __init__(self, session: Session, cache_size: int = 2000) -> None:
        self.session = session
        self._cache: set[str] = set()
        self._cache_size = cache_size

    def filter_new(self, raw_items: Iterable[RawItem]) -> list[tuple[str, RawItem]]:
        """Return list of (url_hash, RawItem) for items NOT already in the DB or cache."""
        candidates: list[tuple[str, RawItem]] = []
        seen_in_batch: set[str] = set()
        for item in raw_items:
            if not item.url:
                continue
            h = url_hash(item.url)
            if h in self._cache or h in seen_in_batch:
                continue
            seen_in_batch.add(h)
            candidates.append((h, item))

        if not candidates:
            return []

        hashes = [h for h, _ in candidates]
        existing = set(
            self.session.execute(
                select(NewsItem.url_hash).where(NewsItem.url_hash.in_(hashes))
            ).scalars()
        )

        new_items = [(h, item) for h, item in candidates if h not in existing]
        self._remember([h for h, _ in candidates])
        log.info("dedup", candidates=len(candidates), new=len(new_items), existing=len(existing))
        return new_items

    def _remember(self, hashes: list[str]) -> None:
        self._cache.update(hashes)
        if len(self._cache) > self._cache_size:
            # trim oldest-ish by recreating; cheap enough
            self._cache = set(list(self._cache)[-self._cache_size :])
