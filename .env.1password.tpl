# 1Password CLI template - rendered by `op inject`.
# Each secret reference points to an item in your "breaking-news-agent" vault.
# See docs/SECRETS.md for the vault layout.

LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./data/agent.db
POLL_INTERVAL_SECONDS=60

AI_PROVIDER=anthropic
AI_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY={{ op://breaking-news-agent/anthropic/credential }}
OPENAI_API_KEY={{ op://breaking-news-agent/openai/credential }}

RSS_FEEDS={{ op://breaking-news-agent/rss/feeds }}
NEWSAPI_KEY={{ op://breaking-news-agent/newsapi/credential }}

X_API_KEY={{ op://breaking-news-agent/x/api_key }}
X_API_SECRET={{ op://breaking-news-agent/x/api_secret }}
X_ACCESS_TOKEN={{ op://breaking-news-agent/x/access_token }}
X_ACCESS_TOKEN_SECRET={{ op://breaking-news-agent/x/access_token_secret }}
X_BEARER_TOKEN={{ op://breaking-news-agent/x/bearer_token }}

THREADS_ACCESS_TOKEN={{ op://breaking-news-agent/threads/access_token }}
THREADS_USER_ID={{ op://breaking-news-agent/threads/user_id }}

TELEGRAM_BOT_TOKEN={{ op://breaking-news-agent/telegram/bot_token }}
TELEGRAM_CHANNEL_ID={{ op://breaking-news-agent/telegram/channel_id }}

YOUTUBE_CLIENT_ID={{ op://breaking-news-agent/youtube/client_id }}
YOUTUBE_CLIENT_SECRET={{ op://breaking-news-agent/youtube/client_secret }}
YOUTUBE_REFRESH_TOKEN={{ op://breaking-news-agent/youtube/refresh_token }}
ELEVENLABS_API_KEY={{ op://breaking-news-agent/elevenlabs/credential }}
PEXELS_API_KEY={{ op://breaking-news-agent/pexels/credential }}

ENABLE_X=true
ENABLE_THREADS=false
ENABLE_TELEGRAM=true
ENABLE_YOUTUBE=false
DRY_RUN=false
