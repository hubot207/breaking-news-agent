"""YouTube Shorts adapter.

The hardest of the five because it needs a sub-pipeline:
 1. Generate TTS audio from the script
 2. Fetch a relevant stock clip from Pexels
 3. Combine with ffmpeg into a vertical 9:16 MP4
 4. Upload via YouTube Data API v3

This module implements the scaffolding; the actual ffmpeg / upload work is
kept as explicit TODOs so you can fill them in when ready.
"""
from __future__ import annotations

from src.adapters.base import AdapterResult, BaseAdapter
from src.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__)


class YouTubeAdapter(BaseAdapter):
    name = "youtube"

    async def publish(self, content: str) -> AdapterResult:
        """content is the 15-second script. We'll turn it into a Short."""
        if settings.dry_run:
            log.info("youtube_dry_run", preview=content[:80])
            return AdapterResult(ok=True, platform_post_id="dryrun")

        if not settings.youtube_refresh_token:
            return AdapterResult(ok=False, error="YouTube credentials missing")

        # TODO: implement video assembly pipeline
        # 1. audio_path = await _synthesize_tts(content)
        # 2. clip_path  = await _fetch_pexels_clip(keywords)
        # 3. mp4_path   = _compose_short(audio_path, clip_path)
        # 4. video_id   = await _upload_to_youtube(mp4_path, title=..., description=...)
        # return AdapterResult(ok=True, platform_post_id=video_id)

        log.warning("youtube_not_implemented")
        return AdapterResult(ok=False, error="YouTube video pipeline not yet implemented")
