"""Analytics collector.

Runs on a slower schedule (hourly or daily) than the posting loop.
For each Post without metrics, asks its adapter for current numbers and
writes a Metric row.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.adapters import get_adapter
from src.db import Metric, Post, SessionLocal
from src.utils.logger import get_logger

log = get_logger(__name__)


class AnalyticsCollector:
    async def run_once(self) -> None:
        with SessionLocal() as session:
            posts = session.execute(
                select(Post).where(Post.status == "posted").limit(200)
            ).scalars().all()
            log.info("analytics_start", count=len(posts))
            for post in posts:
                await self._measure(session, post)
            session.commit()

    async def _measure(self, session: Session, post: Post) -> None:
        if not post.platform_post_id or post.platform_post_id in {"dryrun", "queued"}:
            return
        try:
            adapter = get_adapter(post.platform)
            data = await adapter.fetch_metrics(post.platform_post_id)
            if not data:
                return
            session.add(
                Metric(
                    post_id=post.id,
                    impressions=int(data.get("impressions", 0)),
                    engagements=int(data.get("engagements", 0)),
                    revenue_usd=float(data.get("revenue_usd", 0.0)),
                    measured_at=datetime.utcnow(),
                )
            )
            log.info("metric_recorded", post_id=post.id, platform=post.platform, **data)
        except KeyError:
            log.warning("analytics_no_adapter", platform=post.platform)
        except Exception as e:
            log.warning("analytics_failed", post_id=post.id, error=str(e))


async def main() -> None:
    from src.utils.logger import configure_logging

    configure_logging()
    await AnalyticsCollector().run_once()


if __name__ == "__main__":
    asyncio.run(main())
