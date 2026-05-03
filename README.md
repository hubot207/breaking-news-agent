# Synapse — what builders need to know about AI today

An AI agent that ingests AI/tech news from curated RSS feeds and syndicates it
in real time to **X, Threads, Telegram, and YouTube Shorts** — from a single
content pipeline.

The brand voice is technical-but-accessible, written for software engineers,
founders, and product people who ship AI products. One LLM call per story
generates platform-specific variants with a "Builder angle:" line where it's
natural; each adapter ships its variant independently. The system is
idempotent, async, and fits in a $10/mo VPS.

## Architecture at a glance

```
[RSS / NewsAPI] → Ingester → Dedup → Filter → AI Rewriter
                                                   │
              ┌──────────────┬──────────┬──────────┴────────┐
              ▼              ▼          ▼                   ▼
          X adapter    Threads    Telegram          YouTube Shorts
                                       │
                                       ▼
                               Analytics Collector
                                (writes Metrics)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full walkthrough.

## Quick start

```bash
# 1. Clone + create venv
git clone <repo> breaking-news-agent && cd breaking-news-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# fill in ANTHROPIC_API_KEY + at least one platform's credentials
# keep DRY_RUN=true for your first run

# 3. Initialise the database
python -m src.main init-db

# 4. Run a single pass (safe, won't post if DRY_RUN=true)
python -m src.main once

# 5. Run the continuous loop
python -m src.main run
```

### Docker

```bash
docker compose up -d --build
docker compose logs -f
```

### One-shot VPS deploy

```bash
# On a fresh Ubuntu 22.04 / 24.04 VPS, as root:
export REPO_URL="git@github.com:yourname/breaking-news-agent.git"
sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/yourname/breaking-news-agent/main/scripts/deploy.sh)"
```

The script installs Docker, creates a non-root deploy user, hardens SSH, sets up
UFW firewall, clones the repo, bootstraps `.env`, configures nightly backups, and
starts the agent. Fully idempotent — safe to re-run.

See [`docs/SECRETS.md`](docs/SECRETS.md) for secret-storage options
(`.env` → SOPS → Doppler → Vault).

## Project layout

```
breaking-news-agent/
├── src/
│   ├── main.py              # entry point + async loop
│   ├── config.py            # Pydantic settings from .env
│   ├── db.py                # SQLAlchemy models (NewsItem, Post, Metric)
│   ├── ingesters/           # RSS, NewsAPI, ...
│   ├── pipeline/
│   │   ├── dedup.py         # URL-hash based deduplication
│   │   ├── filter.py        # rule-based "is this breaking?" scorer
│   │   └── rewriter.py      # single LLM call → 4 variants
│   ├── adapters/            # one file per platform
│   └── analytics/           # metrics pullback
├── tests/                   # pytest unit tests
├── scripts/
│   ├── deploy.sh            # one-shot VPS bootstrap
│   └── init_db.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   └── SECRETS.md
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Running tests

```bash
pytest
```

## Operational notes

- **Dry run first.** Keep `DRY_RUN=true` in `.env` until you've verified the rewriter output
  looks good on real feeds. In dry-run mode adapters log but never call external APIs.
- **Feature flags.** Enable platforms one at a time with `ENABLE_*` vars. Start with X +
  Telegram — these are the easiest to validate end-to-end.
- **Idempotency.** The `(news_item_id, platform)` unique constraint on `posts` prevents
  double-posting after crashes or retries.
- **Cost control.** The rule-based filter rejects ~60-80% of items before they hit the LLM.
  One LLM call per breaking-news item yields all platform variants.

## License

MIT — see [LICENSE](LICENSE).
