#!/usr/bin/env bash
# secrets-fetch.sh
# Pull secrets from a managed secret store and write them into .env (chmod 600).
#
# Usage:
#   bash scripts/secrets-fetch.sh doppler        # pulls from Doppler current config
#   bash scripts/secrets-fetch.sh sops           # decrypts secrets.enc.yaml via SOPS
#   bash scripts/secrets-fetch.sh 1password      # renders .env.1password.tpl via op
#   bash scripts/secrets-fetch.sh aws            # pulls from AWS Secrets Manager (BNA_SECRETS)
#
# See docs/SECRETS.md for setup instructions.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${REPO_DIR}/.env"
SOURCE="${1:-}"

log()  { printf "\033[1;34m[secrets]\033[0m %s\n" "$*"; }
fail() { printf "\033[1;31m[fail]\033[0m %s\n" "$*" >&2; exit 1; }

[[ -n "$SOURCE" ]] || fail "Usage: $0 <doppler|sops|1password|aws>"

case "$SOURCE" in
    doppler)
        command -v doppler >/dev/null || fail "Install Doppler CLI: https://docs.doppler.com/docs/install-cli"
        log "Fetching from Doppler..."
        doppler secrets download --no-file --format env > "$ENV_FILE"
        ;;

    sops)
        command -v sops >/dev/null || fail "Install SOPS: https://github.com/getsops/sops"
        local enc="${REPO_DIR}/secrets.enc.yaml"
        [[ -f "$enc" ]] || fail "secrets.enc.yaml not found at repo root"
        log "Decrypting via SOPS..."
        sops -d "$enc" | python3 -c '
import sys, yaml
data = yaml.safe_load(sys.stdin) or {}
for k, v in data.items():
    if v is None: continue
    print(f"{k}={v}")
' > "$ENV_FILE"
        ;;

    1password)
        command -v op >/dev/null || fail "Install 1Password CLI: https://developer.1password.com/docs/cli/get-started"
        local tpl="${REPO_DIR}/.env.1password.tpl"
        [[ -f "$tpl" ]] || fail ".env.1password.tpl not found - see docs/SECRETS.md"
        log "Rendering .env via 1Password CLI..."
        op inject -i "$tpl" -o "$ENV_FILE"
        ;;

    aws)
        command -v aws >/dev/null || fail "Install AWS CLI"
        local name="${BNA_SECRET_NAME:-BNA_SECRETS}"
        log "Fetching AWS Secrets Manager value: $name"
        aws secretsmanager get-secret-value --secret-id "$name" --query SecretString --output text \
          | python3 -c '
import sys, json
data = json.loads(sys.stdin.read())
for k, v in data.items():
    print(f"{k}={v}")
' > "$ENV_FILE"
        ;;

    *)
        fail "Unknown source: $SOURCE (expected: doppler|sops|1password|aws)"
        ;;
esac

chmod 600 "$ENV_FILE"
log "Wrote $ENV_FILE (chmod 600). Restart with: docker compose up -d --force-recreate"
