"""Telegram channel adapter. Uses the Bot API directly - no library dependency required."""
from __future__ import annotations

import httpx

from src.adapters.base import AdapterResult, BaseAdapter
from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)


class TelegramAdapter(BaseAdapter):
    name = "telegram"
    BASE = "https://api.telegram.org"

    async def publish(self, content: str) -> AdapterResult:
        if settings.dry_run:
            log.info("telegram_dry_run", preview=content[:80])
            return AdapterResult(ok=True, platform_post_id="dryrun")

        if not settings.telegram_bot_token or not settings.telegram_channel_id:
            return AdapterResult(ok=False, error="Telegram credentials missing")

        url = f"{self.BASE}/bot{settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": settings.telegram_channel_id,
            "text": content[:4000],
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
            if not data.get("ok"):
                return AdapterResult(ok=False, error=data.get("description"))
            post_id = str(data["result"]["message_id"])
            return AdapterResult(ok=True, platform_post_id=post_id)
        except Exception as e:
            log.error("telegram_publish_failed", error=str(e))
            return AdapterResult(ok=False, error=str(e))
