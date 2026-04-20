#!/usr/bin/env bash
# One-shot deploy for breaking-news-agent on a fresh Ubuntu 22.04 / 24.04 VPS.
#
# Usage (as root on a brand-new VPS):
#   export REPO_URL="git@github.com:yourname/breaking-news-agent.git"   # or https URL
#   curl -fsSL https://raw.githubusercontent.com/.../scripts/deploy.sh | sudo bash
#
# Or after SSH in:
#   sudo REPO_URL=... bash scripts/deploy.sh
#
# The script is IDEMPOTENT - safe to re-run. It will:
#   1. Install Docker + dependencies
#   2. Create a non-root deploy user `bna`
#   3. Enable UFW firewall + harden SSH
#   4. Clone / update the repo into /opt/breaking-news-agent
#   5. Create .env from template if missing (and halt so you can fill it in)
#   6. Build and start the agent via docker compose
#   7. Configure nightly SQLite backup to /var/backups/bna
#   8. Enable unattended security upgrades

set -euo pipefail

# ------------------------------------------------------------------
# Config (override with env vars)
# ------------------------------------------------------------------
REPO_URL="${REPO_URL:-}"
DEPLOY_USER="${DEPLOY_USER:-bna}"
APP_DIR="${APP_DIR:-/opt/breaking-news-agent}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/bna}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
log()  { printf '\033[1;34m[%s]\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
warn() { printf '\033[1;33m[%s] WARN\033[0m %s\n' "$(date '+%H:%M:%S')" "$*"; }
fail() { printf '\033[1;31m[%s] FAIL\033[0m %s\n' "$(date '+%H:%M:%S')" "$*" >&2; exit 1; }

require_root() {
  [[ $EUID -eq 0 ]] || fail "Run with sudo or as root."
}

require_repo_url() {
  if [[ -z "$REPO_URL" && ! -d "$APP_DIR/.git" ]]; then
    fail "REPO_URL not set and no existing checkout at $APP_DIR. Set REPO_URL=... and re-run."
  fi
}

# ------------------------------------------------------------------
# Steps
# ------------------------------------------------------------------
install_base_packages() {
  log "Installing base packages..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq \
    ca-certificates curl git ufw sqlite3 \
    unattended-upgrades apt-listchanges \
    fail2ban jq
}

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    log "Docker already installed ($(docker --version))"
    return
  fi
  log "Installing Docker..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | tee /etc/apt/keyrings/docker.asc >/dev/null
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
}

create_deploy_user() {
  if id "$DEPLOY_USER" >/dev/null 2>&1; then
    log "Deploy user '$DEPLOY_USER' exists"
  else
    log "Creating deploy user '$DEPLOY_USER'..."
    useradd -m -s /bin/bash "$DEPLOY_USER"
  fi
  usermod -aG docker "$DEPLOY_USER"
}

setup_firewall() {
  log "Configuring UFW firewall..."
  ufw --force reset >/dev/null
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow OpenSSH
  ufw --force enable >/dev/null
}

harden_ssh() {
  log "Hardening SSH (disabling password auth, disabling root login)..."
  if [[ ! -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]]; then
    warn "No authorized_keys for $DEPLOY_USER. SSH hardening SKIPPED to avoid lockout."
    warn "Copy your pubkey with: ssh-copy-id $DEPLOY_USER@<ip>  then re-run this script."
    return
  fi
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
  systemctl reload ssh || systemctl reload sshd || true
}

clone_or_update_repo() {
  if [[ -d "$APP_DIR/.git" ]]; then
    log "Updating repo at $APP_DIR..."
    sudo -u "$DEPLOY_USER" git -C "$APP_DIR" pull --ff-only
  else
    log "Cloning $REPO_URL into $APP_DIR..."
    mkdir -p "$(dirname "$APP_DIR")"
    git clone --depth 1 "$REPO_URL" "$APP_DIR"
    chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
  fi
  mkdir -p "$APP_DIR/data" "$APP_DIR/logs" "$APP_DIR/media"
  chown -R "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"
}

bootstrap_env_file() {
  if [[ -f "$APP_DIR/.env" ]]; then
    log ".env already present — keeping existing values"
    chmod 600 "$APP_DIR/.env"
    chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/.env"
    return 0
  fi
  log "Creating $APP_DIR/.env from template..."
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR/.env"
  cat <<EOF

==============================================================
  EDIT YOUR SECRETS NOW:
      sudo -u $DEPLOY_USER nano $APP_DIR/.env

  Minimum required to start posting:
      ANTHROPIC_API_KEY=...
      TELEGRAM_BOT_TOKEN=...
      TELEGRAM_CHANNEL_ID=@yourchannel
      DRY_RUN=false                  (keep true for first test)

  Then re-run:   sudo bash $APP_DIR/scripts/deploy.sh
==============================================================

EOF
  exit 0
}

start_stack() {
  log "Building and starting agent containers..."
  cd "$APP_DIR"
  sudo -u "$DEPLOY_USER" docker compose build
  sudo -u "$DEPLOY_USER" docker compose up -d
  sleep 3
  sudo -u "$DEPLOY_USER" docker compose ps
}

setup_nightly_backup() {
  log "Configuring nightly SQLite backup to $BACKUP_DIR..."
  mkdir -p "$BACKUP_DIR"
  cat > /etc/cron.daily/bna-backup <<EOF
#!/usr/bin/env bash
set -e
DB="$APP_DIR/data/agent.db"
DEST="$BACKUP_DIR"
TS=\$(date +%Y%m%d-%H%M%S)
if [[ -f "\$DB" ]]; then
  sqlite3 "\$DB" ".backup \$DEST/agent-\$TS.db"
  find "\$DEST" -name 'agent-*.db' -mtime +$BACKUP_RETENTION_DAYS -delete
fi
EOF
  chmod +x /etc/cron.daily/bna-backup
}

setup_auto_updates() {
  log "Enabling unattended security upgrades..."
  dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true
}

print_summary() {
  cat <<EOF

==============================================================
  DEPLOY COMPLETE

  App directory:   $APP_DIR
  Deploy user:     $DEPLOY_USER
  Backup dir:      $BACKUP_DIR
  Log tail:        sudo -u $DEPLOY_USER docker compose -f $APP_DIR/docker-compose.yml logs -f
  Restart:         sudo -u $DEPLOY_USER docker compose -f $APP_DIR/docker-compose.yml restart
  Update code:     cd $APP_DIR && git pull && docker compose up -d --build
==============================================================

EOF
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
main() {
  require_root
  install_base_packages
  install_docker
  create_deploy_user
  setup_firewall
  harden_ssh
  setup_auto_updates
  require_repo_url
  clone_or_update_repo
  bootstrap_env_file
  setup_nightly_backup
  start_stack
  print_summary
}

main "$@"
