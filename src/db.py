"""Database models and session management.

Schema is intentionally flat: three tables only.
- news_items: one row per raw story we've seen. URL hash is the dedup key.
- posts:      one row per (news_item, platform) shipped. Idempotency key.
- metrics:    engagement/revenue data pulled back by the analytics collector.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    pass


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[Optional[str]] = mapped_column(Text, default=None)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Scoring fields populated by filter / LLM classifier
    is_breaking: Mapped[bool] = mapped_column(default=False)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Status: "new" -> "scored" -> "rewritten" -> "posted" -> "measured" -> "skipped"
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)

    # JSON blob of {platform: rewritten_text}
    variants_json: Mapped[Optional[str]] = mapped_column(Text, default=None)

    posts: Mapped[list["Post"]] = relationship(back_populates="news_item")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_item_id: Mapped[int] = mapped_column(ForeignKey("news_items.id"), index=True)
    platform: Mapped[str] = mapped_column(String(20), index=True)
    platform_post_id: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    content: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|posted|failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, default=None)

    news_item: Mapped[NewsItem] = relationship(back_populates="posts")

    __table_args__ = (
        UniqueConstraint("news_item_id", "platform", name="uq_post_item_platform"),
        Index("ix_posts_status", "status"),
    )


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    engagements: Mapped[int] = mapped_column(Integer, default=0)
    revenue_usd: Mapped[float] = mapped_column(Float, default=0.0)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# Engine / session
engine = create_engine(settings.database_url, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    Base.metadata.create_all(engine)
