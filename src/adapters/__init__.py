"""Platform adapters. Each implements `BaseAdapter.publish(content) -> post_id`."""
from __future__ import annotations

from src.adapters.base import AdapterResult, BaseAdapter
from src.adapters.beehiiv import BeehiivAdapter
from src.adapters.telegram import TelegramAdapter
from src.adapters.threads import ThreadsAdapter
from src.adapters.x import XAdapter
from src.adapters.youtube import YouTubeAdapter

__all__ = [
    "AdapterResult",
    "BaseAdapter",
    "BeehiivAdapter",
    "TelegramAdapter",
    "ThreadsAdapter",
    "XAdapter",
    "YouTubeAdapter",
]


def get_adapter(name: str) -> BaseAdapter:
    """Factory. Raises KeyError if unknown."""
    from src.config import settings

    mapping: dict[str, BaseAdapter] = {
        "x": XAdapter(),
        "threads": ThreadsAdapter(),
        "telegram": TelegramAdapter(),
        "youtube": YouTubeAdapter(),
        "beehiiv": BeehiivAdapter(),
    }
    return mapping[name]
