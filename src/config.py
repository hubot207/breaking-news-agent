"""Centralised configuration. Reads from environment / .env file via Pydantic."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    log_level: str = "INFO"
    database_url: str = "sqlite:///./data/agent.db"
    poll_interval_seconds: int = 60

    # AI
    ai_provider: str = "anthropic"  # "anthropic" or "openai"
    ai_model: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    # Optional override for OpenAI-compatible endpoints (Gemini, OpenRouter, DeepSeek, etc.).
    # Leave empty to use the default api.openai.com.
    openai_base_url: str = ""
    # Cap LLM calls per minute. Prevents burst-induced 429s and runaway cost.
    # Set to 0 to disable. Suggested: 12 for Gemini free tier, 60 for paid tiers.
    ai_rate_limit_rpm: int = 60

    # Score threshold for the publishability filter (0-1). Lower = more posts.
    # 0.3 = lets most fresh in-niche news through (used to be the default).
    # 0.5 = more selective; only stronger items pass.
    # 0.7 = only true breaking-news markers.
    # Items below threshold are dropped before the LLM, saving cost.
    breaking_filter_threshold: float = 0.5

    # Per-platform publish guards. Two checks are applied before each post:
    #
    # 1. Daily cap: max posts allowed per UTC day (0 = unlimited).
    # 2. Min interval: minimum minutes between consecutive posts to the same
    #    platform (0 = no interval check).
    #
    # When either check fails, the item is skipped for that platform but still
    # publishes to other enabled platforms whose guards allow it.
    #
    # Defaults reflect a brand-new account warming phase. Raise after 30 days
    # of clean operation when the algorithm has classified you as legitimate.
    telegram_daily_post_limit: int = 30
    telegram_min_interval_min: int = 20
    threads_daily_post_limit: int = 10
    threads_min_interval_min: int = 90
    x_daily_post_limit: int = 8
    x_min_interval_min: int = 90
    youtube_daily_post_limit: int = 3
    youtube_min_interval_min: int = 240

    # Sources
    rss_feeds: str = ""
    newsapi_key: str = ""

    # X
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_token_secret: str = ""
    x_bearer_token: str = ""

    # Threads
    threads_access_token: str = ""
    threads_user_id: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""

    # YouTube
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_refresh_token: str = ""
    elevenlabs_api_key: str = ""
    pexels_api_key: str = ""

    # Feature flags
    enable_x: bool = True
    enable_threads: bool = False
    enable_telegram: bool = True
    enable_youtube: bool = False
    dry_run: bool = True

    @property
    def rss_feed_list(self) -> list[str]:
        return [u.strip() for u in self.rss_feeds.split(",") if u.strip()]

    @property
    def enabled_adapters(self) -> list[str]:
        flags = {
            "x": self.enable_x,
            "threads": self.enable_threads,
            "telegram": self.enable_telegram,
            "youtube": self.enable_youtube,
        }
        return [name for name, on in flags.items() if on]


settings = Settings()
