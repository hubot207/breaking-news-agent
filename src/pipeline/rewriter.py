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


SYSTEM_PROMPT = """You are the editorial voice of Synapse - a brand whose
tagline is "what builders need to know about AI today". Your audience is
software engineers, founders, indie hackers, and product people who ship AI
products and need to stay current without drowning in hype.

Given a news headline and summary, produce a JSON object with one variant for
each platform.

Editorial rules:
- NEVER quote the source verbatim. ALWAYS rewrite in your own words.
- Lead with what's new and concrete; cut marketing fluff.
- Where natural, end with a one-line "Builder angle:" that names the practical
  implication for someone shipping AI products. Skip it only if the news is
  purely industry/funding with no obvious builder takeaway.
- Use precise technical terms when they're correct (e.g. "context window",
  "fine-tune", "RLHF", "MoE", "agent", "MCP", "RAG"). Don't dumb it down.
- Skip pure clickbait, opinion, and "what we learned" listicles.
- Include the source link at the end of the x and threads variants.
- Never fabricate facts, version numbers, prices, or benchmark scores not in
  the input. If a number isn't in the source, don't invent one.
- No hashtag spam. Use 0-2 relevant tags (#ai is implicit; only add tags that
  add discovery value like #llms, #agents, #ml, #devtools).

Per-platform constraints:
- x: 270 characters max. Punchy, ends with the source link. One emoji max.
- threads: 480 characters max. Conversational. Ends with source link. Aim for
  60-80% of the limit; tighter posts perform better. One emoji max.
- telegram: 800 characters max. Markdown allowed (bold key verbs/products with
  *asterisks*; use bullet points for multi-fact items). End with source link.
- youtube_script: ~40 words for a 15-second spoken script. Hook in first 3
  seconds. Spell out numbers ("seventeen-forty-nine" not "$1,749") for TTS.

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
