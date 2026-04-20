"""Base adapter contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AdapterResult:
    ok: bool
    platform_post_id: Optional[str] = None
    error: Optional[str] = None


class BaseAdapter(ABC):
    """Each adapter ships one piece of content to its platform.

    Must be idempotent-safe at the call site - the main loop prevents double-posting
    via the (news_item_id, platform) unique constraint, but adapters should also be
    robust to transient errors (wrapped in tenacity retries where practical).
    """

    name: str = "base"

    @abstractmethod
    async def publish(self, content: str) -> AdapterResult:
        """Publish the content. Return AdapterResult with the platform's post id on success."""
        raise NotImplementedError

    async def fetch_metrics(self, platform_post_id: str) -> dict[str, int | float]:
        """Optional: return {'impressions': ..., 'engagements': ..., 'revenue_usd': ...}.
        Default returns empty; adapters that support analytics override this.
        """
        return {}
