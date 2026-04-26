# Architecture

This document explains the design decisions and data flow. Aimed at a developer who
will be extending the system.

## Design goals (in priority order)

1. **Speed from source to post.** Target: under 2 minutes from a news item appearing
   in an RSS feed to being posted on all enabled platforms.
2. **Cost predictability.** Rule-based filter before any LLM call; one LLM call per
   surviving item produces variants for all platforms in a single round-trip.
3. **Idempotency.** The loop must be safe to restart, retry, or crash mid-pass without
   double-posting.
4. **Platform isolation.** One platform's API outage must not block the others.
5. **Lean footprint.** Runs on a single $5-10/month VPS with SQLite.

## Data flow

```
┌────────────────┐       ┌──────────────┐       ┌───────────────┐
│  Ingesters     │──────▶│  Dedup       │──────▶│  Filter       │
│  (RSS/NewsAPI) │       │  (url_hash)  │       │  (rule-based) │
└────────────────┘       └──────────────┘       └──────┬────────┘
                                                       │ score>=0.3
                                                       ▼
                                              ┌──────────────────┐
                                              │  AI Rewriter     │
                                              │  (1 call → 4 vars)│
                                              └──────┬───────────┘
                                                     │
                       ┌────────────┬──────────┬─────┴──────┬─────────────┐
                       ▼            ▼          ▼            ▼             ▼
                  X adapter   Threads   Telegram   YouTube Shorts    (future)
                       │           │          │         │
                       └─────┬─────┴──────┬───┴─────┬───┘
                             │            │         │
                        ▼            ▼         ▼         ▼
                ┌─────────────────────────────────────────────┐
                │              Posts table                    │
                │ (news_item_id, platform) UNIQUE constraint  │
                └─────────────────────────────────────────────┘
                                  │
                                  ▼
                        ┌──────────────────┐
                        │  Analytics       │  (runs hourly; pulls impressions,
                        │  Collector       │   engagement, revenue per post)
                        └──────────────────┘
                                  │
                                  ▼
                          Metrics table
```

## Module responsibilities

### `ingesters/`

Each ingester implements `async fetch() -> Iterable[RawItem]`. Ingesters are pure — they
never touch the DB. New source? Add a new file and wire it into
`ingesters/__init__.py:get_enabled_ingesters`.

### `pipeline/dedup.py`

The dedup key is `sha256(normalised_url)` where `normalise` strips query strings,
fragments, trailing slashes, and lowercases the host. An in-memory LRU-ish cache
avoids DB roundtrips for the common case.

### `pipeline/filter.py`

Rule-based relevance scorer. Designed to catch ~70% of noise without an LLM. Scores
breakdown:

- +0.3 per positive keyword (breaking, urgent, confirmed, …)
- -0.5 per negative keyword (opinion, listicle, review, …)
- +0.4 if published within last hour; +0.2 if within 6 hours
- Final score clamped to [0, 1]; threshold 0.3 to promote to LLM.

When you need smarter filtering, call an LLM classifier in `_score_with_llm` and merge
the two scores (cheap model, few-shot).

### `pipeline/rewriter.py`

The heart of the cost model. Sends the news item to Claude Haiku (or GPT-4o-mini) with
a system prompt that asks for a JSON object containing:

```json
{
  "x": "<=270 char punchy tweet with link",
  "threads": "<=480 char conversational post",
  "telegram": "<=800 char markdown alert",
  "youtube_script": "40-word 15-sec script"
}
```

All four platforms in one round trip. Typical cost: $0.0005 per item with Haiku.
Parses with `json.loads`; retries on parse failure up to 3 times with exponential
backoff.

### `adapters/`

Each adapter implements:

```python
async def publish(content: str) -> AdapterResult
async def fetch_metrics(platform_post_id: str) -> dict
```

**Crucially**, the adapter respects `settings.dry_run`. When true, it logs and
returns `AdapterResult(ok=True, platform_post_id="dryrun")` without calling external
APIs. This lets you test the whole pipeline end-to-end safely.

Adapter contracts:

| Adapter | API | Auth | Notes |
|---|---|---|---|
| `x.py` | Tweepy v4 | OAuth 1.0a user context | v2 endpoint for create_tweet |
| `threads.py` | Meta Threads API | Long-lived access token | 2-step: container → publish |
| `telegram.py` | Bot API (HTTP) | Bot token | Direct HTTP, no library |
| `youtube.py` | YouTube Data v3 | OAuth refresh token | Scaffold only; video pipeline TODO |

### `main.py`

The orchestrator. `run_pipeline_once()` executes one full pass. `run_forever()` wraps
it in `while True` with `poll_interval_seconds` sleep between passes.

Exception handling strategy: the top-level `run_forever` loop catches everything and
logs. Per-item errors are caught inside `_process_item` so one bad story doesn't kill
the batch.

### `analytics/collector.py`

Runs on its own cron (hourly is fine). Selects `Post.status == "posted"` rows and calls
`adapter.fetch_metrics()` on each, writing a new `Metric` row. Over time you build a
rolling history that powers:

- Which platforms yield the best RPM?
- Which news sources drive the most engagement?
- Which rewrite angles go viral?

Future: feed these metrics back into filter scoring (supervised learning on post
engagement per keyword cluster).

## Schema

```sql
news_items(
  id, url_hash UNIQUE, url, source, title, summary,
  published_at, created_at,
  is_breaking, relevance_score,
  status CHECK IN ('new','scored','rewritten','posted','skipped'),
  variants_json
)

posts(
  id, news_item_id FK,
  platform CHECK IN ('x','threads','telegram','youtube'),
  platform_post_id,
  content,
  posted_at,
  status CHECK IN ('pending','posted','failed'),
  error_message,
  UNIQUE(news_item_id, platform)  -- IDEMPOTENCY KEY
)

metrics(
  id, post_id FK,
  impressions, engagements, revenue_usd,
  measured_at
)
```

## Idempotency contract

Three layers prevent double-posting:

1. **Dedup** prevents duplicate `news_items` rows.
2. **Unique constraint `(news_item_id, platform)`** prevents duplicate `posts` rows.
3. **Adapter-level check** — each `_publish` call first looks up an existing Post row;
   if status is already `posted`, it short-circuits.

As a result, a crash mid-loop + restart replays safely: the pending Post row is
re-used, and any successful posts are skipped.

## Scaling path

The current design holds up to roughly:

- 5,000 news items / day ingested
- 500 posts per platform per day
- SQLite concurrency is fine with WAL mode

Beyond that:
- Move to Postgres (one `DATABASE_URL` change)
- Split ingest, rewrite, and publish into three processes that share the DB
- Use Redis Streams instead of DB polling for the queue
- Add a worker pool (one per platform) for publish-side parallelism

## Extending the system

### Add a new platform

1. Create `src/adapters/<platform>.py` implementing `BaseAdapter`.
2. Register it in `src/adapters/__init__.py:get_adapter`.
3. Add `ENABLE_<PLATFORM>` flag in `config.py`.
4. Add a key for its variant in the AI Rewriter's JSON schema.
5. Add a smoke test in `tests/test_adapter_contract.py`.

### Add a new news source

1. Create `src/ingesters/<source>.py` implementing `BaseIngester`.
2. Register in `get_enabled_ingesters()`.

### Add a smarter filter

Extend `pipeline/filter.py` with `_score_with_llm()` that calls a cheap classifier
for borderline items only (current score between 0.1 and 0.3).
