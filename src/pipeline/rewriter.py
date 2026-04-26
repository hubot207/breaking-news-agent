"""AI Rewriter - the brain of the pipeline.

One LLM call takes a news item and returns a JSON object with platform-specific
variants. This is the central cost-saver: we generate all outputs from one call.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.db import NewsItem
from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class PlatformVariants:
    x: str
    threads: str
    telegram: str
    youtube_script: str

    def to_dict(self) -> dict[str, str]:
        return {
            "x": self.x,
            "threads": self.threads,
            "telegram": self.telegram,
            "youtube": self.youtube_script,
        }


SYSTEM_PROMPT = """You are a breaking-news rewriter for a multi-platform news brand.
Given a news headline and summary, produce a JSON object with one variant for each platform.
Rules:
- NEVER quote the source verbatim. ALWAYS rewrite.
- Add a short analytical angle or implication where it's natural.
- Include the source link.
- Never fabricate facts not in the input.
- Tone must match each platform; see formats below.

Return ONLY valid JSON, nothing else. Shape:
{
  "x": "...",             // <=270 chars, punchy, ends with source link
  "threads": "...",       // <=480 chars, conversational
  "telegram": "...",      // <=800 chars, markdown, bold the verb ("*confirmed*")
  "youtube_script": "..." // 15-second spoken script, ~40 words, hook in first 3 sec
}
"""


class AIRewriter:
    """Thin abstraction over Anthropic / OpenAI."""

    def __init__(self) -> None:
        self.provider = settings.ai_provider
        self.model = settings.ai_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def rewrite(self, item: NewsItem) -> Optional[PlatformVariants]:
        user_prompt = self._build_user_prompt(item)
        try:
            raw = await self._call_llm(user_prompt)
            parsed = json.loads(raw)
            return PlatformVariants(
                x=parsed["x"],
                threads=parsed["threads"],
                telegram=parsed["telegram"],
                youtube_script=parsed["youtube_script"],
            )
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("rewriter_parse_failed", error=str(e), item_id=item.id)
            return None

    def _build_user_prompt(self, item: NewsItem) -> str:
        return (
            f"Headline: {item.title}\n"
            f"Source: {item.source}\n"
            f"URL: {item.url}\n"
            f"Summary: {item.summary or '(no summary)'}\n"
            "\nProduce the JSON now."
        )

    async def _call_llm(self, user_prompt: str) -> str:
        if self.provider == "anthropic":
            return await self._call_anthropic(user_prompt)
        if self.provider == "openai":
            return await self._call_openai(user_prompt)
        raise ValueError(f"Unknown AI provider: {self.provider}")

    async def _call_anthropic(self, user_prompt: str) -> str:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        # Content can be a list of blocks; take text from first block.
        text_blocks = [b.text for b in resp.content if hasattr(b, "text")]
        return "".join(text_blocks)

    async def _call_openai(self, user_prompt: str) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or "{}"
