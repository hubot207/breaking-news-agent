"""X (Twitter) adapter using tweepy v4's async client."""
from __future__ import annotations

import tweepy

from src.adapters.base import AdapterResult, BaseAdapter
from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)


class XAdapter(BaseAdapter):
    name = "x"

    def __init__(self) -> None:
        self._client: tweepy.Client | None = None

    def _get_client(self) -> tweepy.Client:
        if self._client is None:
            self._client = tweepy.Client(
                bearer_token=settings.x_bearer_token or None,
                consumer_key=settings.x_api_key or None,
                consumer_secret=settings.x_api_secret or None,
                access_token=settings.x_access_token or None,
                access_token_secret=settings.x_access_token_secret or None,
            )
        return self._client

    async def publish(self, content: str) -> AdapterResult:
        if settings.dry_run:
            log.info("x_dry_run", preview=content[:80])
            return AdapterResult(ok=True, platform_post_id="dryrun")

        # Truncate safety net
        text = content[:280]
        try:
            import asyncio

            def _post() -> tweepy.Response:
                return self._get_client().create_tweet(text=text)

            resp = await asyncio.to_thread(_post)
            post_id = str(resp.data["id"]) if resp.data else None
            return AdapterResult(ok=True, platform_post_id=post_id)
        except Exception as e:
            log.error("x_publish_failed", error=str(e))
            return AdapterResult(ok=False, error=str(e))

    async def fetch_metrics(self, platform_post_id: str) -> dict[str, int | float]:
        if settings.dry_run or not platform_post_id or platform_post_id == "dryrun":
            return {}
        try:
            import asyncio

            def _get() -> tweepy.Response:
                return self._get_client().get_tweet(
                    id=platform_post_id,
                    tweet_fields=["public_metrics", "non_public_metrics"],
                )

            resp = await asyncio.to_thread(_get)
            metrics = (resp.data.data or {}).get("public_metrics", {}) if resp.data else {}
            return {
                "impressions": metrics.get("impression_count", 0),
                "engagements": metrics.get("like_count", 0) + metrics.get("retweet_count", 0),
            }
        except Exception as e:
            log.warning("x_metrics_failed", error=str(e))
            return {}
