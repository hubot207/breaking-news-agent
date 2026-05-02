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
from src.utils.rate_limit import get_llm_limiter

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


SYSTEM_PROMPT = """You are a breaking-news rewriter for a multi-platform news brand named Synapse.
Given a news headline and summary, produce a JSON object with one variant for each platform.

Rules:
- NEVER quote the source verbatim. ALWAYS rewrite.
- Add a short analytical angle or implication where it's natural.
- Include the source link at the end of the x and threads variants.
- Never fabricate facts not in the input.
- Tone must match each platform.

Per-platform constraints:
- x: 270 characters max. Punchy, ends with the source link.
- threads: 480 characters max. Conversational, ends with the source link.
- telegram: 800 characters max. Markdown formatting allowed (bold key verbs with *asterisks*).
- youtube_script: ~40 words for a 15-second spoken script. Hook in first 3 seconds.

Output rules (CRITICAL):
- Return ONLY a single raw JSON object.
- Do NOT wrap the JSON in markdown code fences like ```json or ```.
- Do NOT include any prose before or after the JSON.
- Do NOT include comments inside the JSON.
- Use double quotes, not single quotes.

The JSON must have exactly these four keys: "x", "threads", "telegram", "youtube_script".
"""


def _extract_json(raw: str) -> str:
    """Pull the JSON object out of a possibly-decorated LLM response.

    Handles common wrappings:
    - Markdown code fences: ```json\\n{...}\\n``` or ```\\n{...}\\n```
    - Leading/trailing prose: "Here is the JSON:\\n{...}\\nHope this helps!"
    - Stray whitespace.

    Returns the substring from the first { to the last } (matching depth-1
    boundaries). If no JSON object is detected, returns the original string
    so json.loads raises a useful error.
    """
    if not raw:
        return raw
    s = raw.strip()
    # Strip markdown code fences if present
    if s.startswith("```"):
        # remove opening fence (```json or just ```)
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        # remove trailing fence
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3].rstrip()
    # Find the outermost JSON object boundaries
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end < start:
        return s
    return s[start : end + 1]


class AIRewriter:
    """Thin abstraction over Anthropic / OpenAI."""

    def __init__(self) -> None:
        self.provider = settings.ai_provider
        self.model = settings.ai_model

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        reraise=True,
    )
    async def rewrite(self, item: NewsItem) -> Optional[PlatformVariants]:
        user_prompt = self._build_user_prompt(item)
        raw = ""
        try:
            await get_llm_limiter().acquire()
            raw = await self._call_llm(user_prompt)
            cleaned = _extract_json(raw)
            parsed = json.loads(cleaned)
            return PlatformVariants(
                x=parsed["x"],
                threads=parsed["threads"],
                telegram=parsed["telegram"],
                youtube_script=parsed["youtube_script"],
            )
        except (json.JSONDecodeError, KeyError) as e:
            # Log a short preview of the offending response to make this debuggable.
            preview = raw[:200].replace("\n", " ") if raw else "(empty)"
            log.warning(
                "rewriter_parse_failed",
                error=str(e),
                item_id=item.id,
                response_preview=preview,
            )
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

        # Allow pointing at any OpenAI-compatible endpoint (Gemini, OpenRouter,
        # DeepSeek, Together, etc.) via OPENAI_BASE_URL. Empty = default OpenAI.
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
        )
        resp = await client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or "{}"
