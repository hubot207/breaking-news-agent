#!/usr/bin/env bash
# update.sh - quick redeploy: git pull + rebuild + restart
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_DIR"

log() { printf "\033[1;34m[update]\033[0m %s\n" "$*"; }

log "git pull"
git pull --ff-only

log "rebuild image"
docker compose build

log "restart with new image"
docker compose up -d

log "ps"
docker compose ps

log "tailing last 30 lines"
docker compose logs --tail=30
