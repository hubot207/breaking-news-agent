"""Smoke-tests adapter contract: every adapter must honor dry_run and return AdapterResult."""
import pytest

from src.adapters import (
    TelegramAdapter,
    ThreadsAdapter,
    XAdapter,
    YouTubeAdapter,
)
from src.config import settings


@pytest.mark.parametrize(
    "adapter_cls",
    [XAdapter, TelegramAdapter, ThreadsAdapter],
)
async def test_adapter_dry_run_returns_ok(adapter_cls, monkeypatch):
    monkeypatch.setattr(settings, "dry_run", True)
    adapter = adapter_cls()
    result = await adapter.publish("test content")
    assert result.ok is True
    assert result.platform_post_id == "dryrun"


async def test_youtube_adapter_dry_run(monkeypatch):
    monkeypatch.setattr(settings, "dry_run", True)
    result = await YouTubeAdapter().publish("short script")
    assert result.ok is True
