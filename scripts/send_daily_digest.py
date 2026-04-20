"""Assemble and send the daily beehiiv digest.

Runs from cron once/day:
    0 13 * * *  cd /app && python scripts/send_daily_digest.py
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

from sqlalchemy import select

from src.adapters.beehiiv import BeehiivAdapter
from src.db import NewsItem, SessionLocal, init_db
from src.utils.logger import configure_logging, get_logger

log = get_logger(__name__)


def build_html(items: list[NewsItem]) -> str:
    body = ["<h1>Today's breaking news</h1>"]
    for it in items:
        variants = json.loads(it.variants_json or "{}")
        blurb = variants.get("beehiiv") or it.title
        body.append(f'<h3><a href="{it.url}">{it.title}</a></h3><p>{blurb}</p><hr/>')
    return "\n".join(body)


async def main() -> None:
    configure_logging()
    init_db()
    since = datetime.utcnow() - timedelta(hours=24)
    with SessionLocal() as session:
        items = session.execute(
            select(NewsItem)
            .where(NewsItem.status == "posted", NewsItem.created_at >= since)
            .order_by(NewsItem.relevance_score.desc())
            .limit(15)
        ).scalars().all()

    if not items:
        log.info("digest_empty")
        return

    html = build_html(items)
    subject = f"Breaking News Digest — {datetime.utcnow():%b %d, %Y}"
    result = await BeehiivAdapter().send_digest(html, subject)
    if result.ok:
        log.info("digest_sent", post_id=result.platform_post_id)
    else:
        log.error("digest_failed", error=result.error)


if __name__ == "__main__":
    asyncio.run(main())
