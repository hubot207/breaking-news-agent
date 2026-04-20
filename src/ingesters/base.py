"""Base ingester contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional


@dataclass
class RawItem:
    """A raw news item before dedup / scoring."""

    url: str
    title: str
    source: str
    summary: Optional[str] = None
    published_at: Optional[datetime] = None


class BaseIngester(ABC):
    """Adapters fetch raw items from a news source.

    Subclasses should be side-effect free (no DB writes); the pipeline
    stage handles persistence and deduplication.
    """

    name: str = "base"

    @abstractmethod
    async def fetch(self) -> Iterable[RawItem]:
        """Return an iterable of freshly-fetched raw items."""
        raise NotImplementedError
