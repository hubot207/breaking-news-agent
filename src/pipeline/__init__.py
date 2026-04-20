"""Pipeline stages: dedup -> filter -> rewrite."""
from src.pipeline.dedup import Deduplicator, url_hash
from src.pipeline.filter import BreakingNewsFilter
from src.pipeline.rewriter import AIRewriter, PlatformVariants

__all__ = [
    "Deduplicator",
    "url_hash",
    "BreakingNewsFilter",
    "AIRewriter",
    "PlatformVariants",
]
