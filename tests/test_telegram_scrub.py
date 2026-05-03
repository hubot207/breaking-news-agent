"""Telegram adapter must never leak the bot token into log output."""
from src.adapters.telegram import TelegramAdapter
from src.config import settings


def test_scrub_replaces_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "12345:fake_token_value")
    msg = (
        "Client error 403 Forbidden for url "
        "'https://api.telegram.org/bot12345:fake_token_value/sendMessage'"
    )
    out = TelegramAdapter._scrub(msg)
    assert "fake_token_value" not in out
    assert "<REDACTED>" in out


def test_scrub_passthrough_when_no_token(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    msg = "Some unrelated error message"
    assert TelegramAdapter._scrub(msg) == msg


def test_scrub_passthrough_when_token_absent(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "12345:fake_token_value")
    msg = "Connection timeout, nothing to redact here"
    assert TelegramAdapter._scrub(msg) == msg
