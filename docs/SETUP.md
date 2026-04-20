# Setup Guide

Step-by-step from zero to first post.

## 1. Get the code running locally

```bash
git clone <repo>
cd breaking-news-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m src.main init-db
pytest
```

The tests should all pass. If they don't, stop here and fix before going further.

## 2. Minimum viable first run (no credentials needed)

Even without any API keys, you can run the pipeline in dry-run mode:

```bash
# Keep DRY_RUN=true in .env
# Add at least one RSS feed (the example file has two).
python -m src.main once
```

Expected output: ingester logs, dedup stats, filter scores, and adapter dry-run logs.
No external APIs called, no posts made.

## 3. Wire up your first real platform: Telegram (easiest)

Why Telegram first? Bot creation is 2 minutes, no app review, and messages ship
instantly.

1. Message `@BotFather` on Telegram → `/newbot` → follow prompts. Copy the bot token.
2. Create a channel, add the bot as an administrator with "Post messages" permission.
3. Find your channel handle (e.g. `@my_news_channel`).
4. Fill in `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_CHANNEL_ID=@my_news_channel
   ENABLE_TELEGRAM=true
   DRY_RUN=false
   ```
5. Run:
   ```bash
   python -m src.main once
   ```
   You should see a post in your channel within seconds.

## 4. Add X

X requires a developer account and a project with the "write" scope.

1. Apply at https://developer.x.com. Basic tier is required for posting.
2. Create an app inside a project, generate OAuth 1.0a user context tokens.
3. Fill in `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`.
4. Set `ENABLE_X=true`.

## 5. Get an AI provider key

Either Anthropic or OpenAI:

- Anthropic: https://console.anthropic.com → API Keys → Create
- OpenAI: https://platform.openai.com/api-keys

The default model is Claude Haiku (cheapest Anthropic model that handles JSON well).
Expect ~$0.0005 per news item rewritten.

## 6. Deploy

### Option A: Docker on a VPS

```bash
# On the VPS
git clone <repo>
cd breaking-news-agent
cp .env.example .env  # edit credentials
docker compose up -d --build
```

Logs: `docker compose logs -f`
Stop: `docker compose down`

### Option B: systemd service

```ini
# /etc/systemd/system/bna.service
[Unit]
Description=Breaking News Agent
After=network.target

[Service]
Type=simple
User=bna
WorkingDirectory=/opt/breaking-news-agent
EnvironmentFile=/opt/breaking-news-agent/.env
ExecStart=/opt/breaking-news-agent/.venv/bin/python -m src.main run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now bna
sudo journalctl -u bna -f
```

## 7. Schedule the analytics collector (optional)

```bash
# crontab -e
0 * * * * cd /opt/breaking-news-agent && .venv/bin/python -m src.analytics.collector
0 13 * * * cd /opt/breaking-news-agent && .venv/bin/python scripts/send_daily_digest.py
```

## 8. Monitor

A few things to watch in the first week:

- `logs/*.log` — look for `rewriter_parse_failed` (prompt needs tuning) or
  `publish_failed` (credentials issue).
- SQLite: `sqlite3 data/agent.db 'SELECT platform, status, COUNT(*) FROM posts GROUP BY 1,2'`
- Platform dashboards (X Analytics, Telegram Analytics, beehiiv Stats).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `rewriter_parse_failed` repeatedly | Model returning prose, not JSON. Switch to a JSON-mode model or tighten the prompt. |
| X returns 403 | App lacks write permission or user tokens are read-only. Regenerate with OAuth 1.0a user context. |
| Telegram returns "chat not found" | Bot isn't added to the channel as admin. |
| Threads container creation fails | Access token expired. Long-lived tokens need refresh every 60 days. |
| Many duplicate posts on restart | The unique constraint is missing — run `init-db` to recreate schema. |
