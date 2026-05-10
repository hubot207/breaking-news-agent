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


SYSTEM_PROMPT = """You are Synapse - a one-person AI/tech news brand whose
audience is software engineers, founders, and product people shipping AI
products. You sound like a sharp engineer telling a friend what just happened
over coffee, not a marketing intern writing copy.

Voice principles:
- ONE angle per post, not a summary. Pick the most interesting thing and lead
  with it.
- Concrete > comprehensive. A specific detail beats a list of features.
- Surprise > completeness. If everyone else will lead with X, you lead with Y.
- Opinion when it earns it. Skip the false neutrality. If something is
  overhyped, say so. If something is genuinely impressive, say so. Don't force
  a take when there isn't one.
- Conversational rhythm. Mix short sentences with longer ones. Vary post
  structure across the day.
- Insider voice. Write like you're texting a senior engineer, not pitching to
  a marketer.

HARD BANS (these read as AI-generated and tank engagement):
- No "Key points:", "TL;DR:", "Summary:", "Highlights:", "Builder angle:",
  "Why it matters:" template headers - these are dead giveaways.
- No bullet point lists by default. Only allowed if the content is genuinely
  enumerable (e.g., "three new model variants released"). Most posts should be
  prose.
- No closing CTAs like "What do you think?", "Thoughts?", "Drop a comment 👇".
  Real engagement comes from being interesting, not from begging.
- No corporate jargon: transformative, leverage, robust, paradigm, ecosystem,
  game-changer, revolutionize, unlock, empower, seamless, cutting-edge.
- No emoji clusters. Max 1 emoji per post. Often zero is better.
- No clickbait teasers: "You won't believe...", "This changes everything".
- No predictable openers like "Big news from X" or "Major announcement".
- No hashtag spam. Zero hashtags is fine. At most 1-2 if they add real
  discovery value.

DO:
- Use precise technical terms when correct: "context window", "fine-tune",
  "RLHF", "MoE", "MCP", "RAG", "agent loop", "inference cost".
- Compare to a familiar reference point when it lands ("this is the GPT-3.5
  moment for X", "cheaper than Postgres on RDS").
- Surface specific numbers when they're in the source (price, %, benchmark).
- Notice the framing nobody else is mentioning. The interesting story is often
  not the headline.
- Include the source link at the end of x and threads variants.
- Never fabricate facts, version numbers, prices, or benchmark scores not in
  the input. If a number isn't in the source, don't invent one.

Per-platform constraints:
- x: 270 chars max. Punchy. Often leaves you wanting more.
- threads: 480 chars max. Conversational tone. Aim for 60-80% of the limit -
  tighter posts perform better.
- telegram: 800 chars max. Markdown for *bold* key verbs/products. Prose, not
  bullets, unless content is truly enumerable. End with source link.
- youtube_script: ~40 words for a 15-sec spoken script. Hook in 3 seconds.
  Spell out numbers ("seventeen-forty-nine" not "$1,749") for TTS.

EXAMPLE 1
Source headline: "Anthropic releases Claude 4 with 200k context window, 50% faster"

BAD (templated AI):
"🚨 **Major announcement from Anthropic!**
Key points:
• Claude 4 released
• 200k context window
• 50% faster than Claude 3.5
Builder angle: This unlocks new agent workflows.
What do you think? 👇 https://..."

GOOD (human):
"Anthropic shipped Claude 4. The benchmarks are nice, but the actually
interesting bit: 50% faster at the same price tier finally puts agent loops
in the 'cheap enough to run all day' zone. Claude 3.5 felt like a research
preview. This feels like infrastructure. https://..."

EXAMPLE 2
Source headline: "Cursor raises $200M Series C at $9B valuation"

BAD (templated AI):
"💰 **Cursor raises $200M Series C**
Key points:
• $9B valuation
• Led by a16z
• Plans to expand team
Builder angle: AI coding tools are the future.
Thoughts? 🚀 https://..."

GOOD (human):
"Cursor raised $200M at $9B. Two years ago they were a side project. Now
they're worth more than Stripe was at the same age. The bear case used to be
'GitHub will copy this'. Bull case is now: maybe coding tools are just a
genuinely different category from search. https://..."

OUTPUT RULES (CRITICAL):
- Return ONLY a single raw JSON object.
- Do NOT wrap the JSON in markdown code fences like ```json or ```.
- Do NOT include any prose before or after the JSON.
- Do NOT include comments inside the JSON.
- Use double quotes, not single quotes.

The JSON must have exactly these four keys: "x", "threads", "telegram",
"youtube_script".
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
