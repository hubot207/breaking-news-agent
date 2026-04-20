"""Threads adapter using Meta's Threads API (Graph API).

Posting on Threads is a 2-step flow:
 1. POST /me/threads  -> create media container
 2. POST /me/threads_publish -> publish the container
"""
from __future__ import annotations

import httpx

from src.adapters.base import AdapterResult, BaseAdapter
from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)


class ThreadsAdapter(BaseAdapter):
    name = "threads"
    BASE = "https://graph.threads.net/v1.0"

    async def publish(self, content: str) -> AdapterResult:
        if settings.dry_run:
            log.info("threads_dry_run", preview=content[:80])
            return AdapterResult(ok=True, platform_post_id="dryrun")

        if not settings.threads_access_token or not settings.threads_user_id:
            return AdapterResult(ok=False, error="Threads credentials missing")

        user = settings.threads_user_id
        token = settings.threads_access_token
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # 1. create container
                r1 = await client.post(
                    f"{self.BASE}/{user}/threads",
                    params={"access_token": token},
                    data={"media_type": "TEXT", "text": content[:500]},
                )
                r1.raise_for_status()
                container_id = r1.json().get("id")
                if not container_id:
                    return AdapterResult(ok=False, error="No container id returned")

                # 2. publish
                r2 = await client.post(
                    f"{self.BASE}/{user}/threads_publish",
                    params={"access_token": token},
                    data={"creation_id": container_id},
                )
                r2.raise_for_status()
                post_id = r2.json().get("id")
                return AdapterResult(ok=True, platform_post_id=post_id)
        except Exception as e:
            log.error("threads_publish_failed", error=str(e))
            return AdapterResult(ok=False, error=str(e))
