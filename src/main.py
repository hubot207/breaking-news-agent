"""Main loop. Wires everything together.

Run:
    python -m src.main run      # Continuous loop
    python -m src.main once     # Single pass (useful for debugging)
    python -m src.main analytics # Run analytics collector pass
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.adapters import get_adapter
from src.analytics import AnalyticsCollector
from src.config import settings
from src.db import NewsItem, Post, SessionLocal, init_db
from src.ingesters import get_enabled_ingesters
from src.pipeline import AIRewriter, BreakingNewsFilter, Deduplicator
from src.utils.logger import configure_logging, get_logger

log = get_logger(__name__)


async def run_pipeline_once() -> None:
    """A single end-to-end pass: ingest -> dedup -> score -> rewrite -> publish."""
    ingesters = get_enabled_ingesters()
    if not ingesters:
        log.warning("no_ingesters_configured")
        return

    # 1. Ingest
    all_raw = []
    for ing in ingesters:
        items = await ing.fetch()
        all_raw.extend(items)

    if not all_raw:
        log.info("no_items_this_pass")
        return

    rewriter = AIRewriter()
    filter_ = BreakingNewsFilter()

    with SessionLocal() as session:
        # 2. Dedup
        dedup = Deduplicator(session)
        new_items = dedup.filter_new(all_raw)

        # 3. Persist + score
        news_rows: list[NewsItem] = []
        for url_h, raw in new_items:
            row = NewsItem(
                url_hash=url_h,
                url=raw.url,
                source=raw.source,
                title=raw.title,
                summary=raw.summary,
                published_at=raw.published_at,
                status="new",
            )
            row.relevance_score = filter_.score(row)
            row.is_breaking = row.relevance_score >= 0.3
            row.status = "scored" if row.is_breaking else "skipped"
            session.add(row)
            if row.is_breaking:
                news_rows.append(row)
        session.commit()
        log.info("scored", scored=len(new_items), breaking=len(news_rows))

        # 4. Rewrite + publish (parallel per item, serial across items to keep costs predictable)
        for row in news_rows:
            await _process_item(session, row, rewriter)
        session.commit()


async def _process_item(session: Session, item: NewsItem, rewriter: AIRewriter) -> None:
    variants = await rewriter.rewrite(item)
    if variants is None:
        item.status = "skipped"
        log.warning("rewrite_failed", item_id=item.id)
        return

    item.variants_json = json.dumps(variants.to_dict())
    item.status = "rewritten"
    session.flush()

    # Publish to enabled platforms in parallel, respecting per-platform daily caps.
    variant_map = variants.to_dict()
    tasks = []
    for platform in settings.enabled_adapters:
        content = variant_map.get(platform)
        if not content:
            continue
        if not _under_daily_cap(session, platform):
            log.info("daily_cap_reached_skipping", platform=platform)
            continue
        tasks.append(_publish(session, item.id, platform, content))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    item.status = "posted"


def _under_daily_cap(session: Session, platform: str) -> bool:
    """Returns True if today's post count for `platform` is below the configured cap.

    A cap of 0 means unlimited. Day boundary is UTC 00:00. Counts only posts
    that actually shipped (status='posted'), so failed attempts don't burn
    cap budget.
    """
    cap = getattr(settings, f"{platform}_daily_post_limit", 0)
    if cap <= 0:
        return True
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    count = session.execute(
        select(func.count(Post.id)).where(
            Post.platform == platform,
            Post.posted_at >= today_start,
            Post.status == "posted",
        )
    ).scalar() or 0
    return count < cap


async def _publish(session: Session, news_item_id: int, platform: str, content: str) -> None:
    """Insert a pending Post row, call the adapter, update on result.
    The (news_item_id, platform) unique constraint prevents double-posting on retries.
    """
    # Idempotency check
    existing = session.execute(
        select(Post).where(Post.news_item_id == news_item_id, Post.platform == platform)
    ).scalar_one_or_none()
    if existing and existing.status == "posted":
        return

    if existing is None:
        existing = Post(
            news_item_id=news_item_id,
            platform=platform,
            content=content,
            status="pending",
        )
        session.add(existing)
        session.flush()

    try:
        adapter = get_adapter(platform)
        result = await adapter.publish(content)
    except Exception as e:
        existing.status = "failed"
        existing.error_message = f"adapter_exception: {e}"
        log.error("publish_exception", platform=platform, error=str(e))
        return

    if result.ok:
        existing.status = "posted"
        existing.platform_post_id = result.platform_post_id
        existing.posted_at = datetime.utcnow()
        log.info("published", platform=platform, post_id=result.platform_post_id)
    else:
        existing.status = "failed"
        existing.error_message = result.error
        log.warning("publish_failed", platform=platform, error=result.error)


async def run_forever() -> None:
    # Mask the base URL host so it's grep-able but reads sensibly when default.
    base_url = settings.openai_base_url or "default"
    log.info(
        "agent_starting",
        enabled_platforms=settings.enabled_adapters,
        dry_run=settings.dry_run,
        ai_provider=settings.ai_provider,
        ai_model=settings.ai_model,
        ai_base_url=base_url,
    )
    while True:
        try:
            await run_pipeline_once()
        except Exception as e:
            log.error("loop_error", error=str(e), exc_info=True)
        await asyncio.sleep(settings.poll_interval_seconds)


def cli() -> None:
    parser = argparse.ArgumentParser(description="Breaking News Agent")
    parser.add_argument(
        "command",
        choices=["run", "once", "analytics", "init-db"],
        help="run: loop forever. once: single pass. analytics: collector run. init-db: create tables.",
    )
    args = parser.parse_args()

    configure_logging()
    init_db()

    if args.command == "init-db":
        log.info("db_initialized")
        return
    if args.command == "once":
        asyncio.run(run_pipeline_once())
        return
    if args.command == "analytics":
        asyncio.run(AnalyticsCollector().run_once())
        return
    asyncio.run(run_forever())


if __name__ == "__main__":
    cli()
