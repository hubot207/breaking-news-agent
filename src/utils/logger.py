"""Structured logging setup. Human-readable in dev, JSON in prod.

Also silences noisy third-party HTTP loggers (httpx, openai, anthropic) which
log full request URLs at INFO level. Telegram's API design embeds the bot token
in the URL path (`/bot<TOKEN>/sendMessage`), so leaving those loggers at INFO
leaks the token to anyone with log access.
"""
from __future__ import annotations

import logging
import sys

import structlog

from src.config import settings

# Third-party libraries whose default INFO logs include credentials in URLs
# or other request metadata. We pin them to WARNING so only real failures
# surface, never normal request traffic.
_NOISY_LIBS = ("httpx", "httpcore", "openai", "anthropic", "urllib3")


def configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.log_level.upper(),
    )
    for name in _NOISY_LIBS:
        logging.getLogger(name).setLevel(logging.WARNING)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
