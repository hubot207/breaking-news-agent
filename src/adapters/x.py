"""X (Twitter) adapter using tweepy v4's async client.

URL stripping: X charges $0.20 per post containing a URL vs $0.015 for plain
text posts (a 13x premium intended to discourage off-platform links). We
prompt the LLM to omit URLs from the x variant, but as a defense in depth
this adapter strips any URL that slips through before posting.
"""
from __future__ import annotations

import re

import tweepy

from src.adapters.base import AdapterResult, BaseAdapter
from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)

# Matches http(s) URLs and t.co shortened ones. Anchored to whitespace
# boundaries so partial text matches don't get destroyed.
_URL_PATTERN = re.compile(r"https?://\S+|t\.co/\S+", re.IGNORECASE)


def _strip_urls(text: str) -> tuple[str, int]:
    """Remove any URLs from text. Returns (cleaned_text, count_removed)."""
    matches = _URL_PATTERN.findall(text)
    if not matches:
        return text, 0
    cleaned = _URL_PATTERN.sub("", text)
    # Collapse the whitespace gap left behind by the removed URL.
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    # Remove dangling trailing punctuation left over from "... read more: <URL>"
    cleaned = re.sub(r"[\s:,;\-—–]+$", "", cleaned)
    return cleaned, len(matches)


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
        # Defense in depth: strip any URL before posting. The prompt tells the
        # LLM to omit URLs, but if one slips through we don't want to be billed
        # at the URL-post rate (13x more expensive).
        text, stripped = _strip_urls(content)
        if stripped:
            log.info("x_url_stripped", count=stripped, preview=text[:80])

        if settings.dry_run:
            log.info("x_dry_run", preview=text[:80])
            return AdapterResult(ok=True, platform_post_id="dryrun")

        # Truncate safety net
        text = text[:280]
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
