#!/usr/bin/env bash
# backup.sh - SQLite snapshot + optional remote upload (Backblaze B2 or S3-compatible).
#
# Local-only:   bash scripts/backup.sh
# With B2:      B2_BUCKET=mybucket bash scripts/backup.sh   # requires `b2` CLI logged in
# With S3:      S3_BUCKET=s3://mybucket/bna bash scripts/backup.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DB="${REPO_DIR}/data/agent.db"
BACKUP_DIR="${BACKUP_DIR:-${REPO_DIR}/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
TS="$(date -u +%Y%m%d-%H%M%S)"
DEST="${BACKUP_DIR}/agent-${TS}.db"

log() { printf "\033[1;34m[backup]\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31m[fail]\033[0m %s\n" "$*" >&2; exit 1; }

[[ -f "$DB" ]] || fail "Database not found at $DB"
mkdir -p "$BACKUP_DIR"

log "Snapshotting $DB -> $DEST"
sqlite3 "$DB" ".backup '$DEST'"
gzip "$DEST"
DEST="${DEST}.gz"
log "Local snapshot: $DEST ($(du -h "$DEST" | cut -f1))"

# Optional remote upload
if [[ -n "${B2_BUCKET:-}" ]]; then
    command -v b2 >/dev/null || fail "b2 CLI not installed"
    log "Uploading to B2 bucket: $B2_BUCKET"
    b2 file upload "$B2_BUCKET" "$DEST" "agent-backups/$(basename "$DEST")"
fi

if [[ -n "${S3_BUCKET:-}" ]]; then
    command -v aws >/dev/null || fail "aws CLI not installed"
    log "Uploading to S3: $S3_BUCKET"
    aws s3 cp "$DEST" "${S3_BUCKET}/$(basename "$DEST")"
fi

# Local retention sweep
log "Pruning local backups older than $RETENTION_DAYS days"
find "$BACKUP_DIR" -name 'agent-*.db.gz' -mtime "+$RETENTION_DAYS" -delete

log "DONE"
