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
