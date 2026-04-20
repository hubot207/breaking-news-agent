"""beehiiv newsletter adapter.

Publishing strategy: accumulate blurbs in the DB and send a daily digest,
rather than sending an email per story (which would destroy deliverability).

This adapter appends the blurb to a 'draft' queue. A separate scheduled job
(see scripts/send_daily_digest.py) should assemble and send the digest.
"""
from __future__ import annotations

import httpx

from src.adapters.base import AdapterResult, BaseAdapter
from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)


class BeehiivAdapter(BaseAdapter):
    name = "beehiiv"
    BASE = "https://api.beehiiv.com/v2"

    async def publish(self, content: str) -> AdapterResult:
        """For beehiiv we don't send one email per item. Instead we record it for
        the daily digest. Returns 'queued' as the post id.
        """
        if settings.dry_run:
            log.info("beehiiv_dry_run", preview=content[:80])
            return AdapterResult(ok=True, platform_post_id="dryrun")

        # TODO: write to a BeehiivDigestEntry table and let the digest job
        # assemble the final post draft via the beehiiv API.
        log.info("beehiiv_queued", length=len(content))
        return AdapterResult(ok=True, platform_post_id="queued")

    async def send_digest(self, html_body: str, subject: str) -> AdapterResult:
        """Create and send a post via beehiiv Posts API."""
        if not settings.beehiiv_api_key or not settings.beehiiv_publication_id:
            return AdapterResult(ok=False, error="beehiiv credentials missing")

        url = f"{self.BASE}/publications/{settings.beehiiv_publication_id}/posts"
        headers = {"Authorization": f"Bearer {settings.beehiiv_api_key}"}
        payload = {
            "title": subject,
            "content_html": html_body,
            "status": "confirmed",  # or "draft"
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                post_id = resp.json().get("data", {}).get("id")
                return AdapterResult(ok=True, platform_post_id=post_id)
        except Exception as e:
            log.error("beehiiv_digest_failed", error=str(e))
            return AdapterResult(ok=False, error=str(e))
