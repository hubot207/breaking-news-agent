#!/usr/bin/env bash
# bootstrap-vps.sh
# Run ONCE on a fresh Ubuntu 22.04 / 24.04 VPS as root (or with sudo).
# Provisions Docker, firewall, automatic security updates, and the `bna` app user.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<you>/breaking-news-agent/main/scripts/bootstrap-vps.sh | sudo bash
#   OR
#   sudo bash scripts/bootstrap-vps.sh
set -euo pipefail

APP_USER="${APP_USER:-bna}"
APP_HOME="/home/${APP_USER}"
SSH_PORT="${SSH_PORT:-22}"

log() { printf "\n\033[1;34m[bootstrap]\033[0m %s\n" "$*"; }
fail() { printf "\n\033[1;31m[fail]\033[0m %s\n" "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Run as root: sudo bash $0"

log "1/7  apt update + base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg lsb-release ufw fail2ban \
    git sqlite3 unattended-upgrades

log "2/7  install Docker engine + Compose plugin"
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

log "3/7  create app user '${APP_USER}'"
if ! id -u "$APP_USER" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "$APP_USER"
fi
usermod -aG docker "$APP_USER"
mkdir -p "$APP_HOME/.ssh"
chmod 700 "$APP_HOME/.ssh"
if [[ -f /root/.ssh/authorized_keys ]]; then
    cp /root/.ssh/authorized_keys "$APP_HOME/.ssh/authorized_keys"
    chmod 600 "$APP_HOME/.ssh/authorized_keys"
    chown -R "$APP_USER:$APP_USER" "$APP_HOME/.ssh"
fi

log "4/7  configure UFW firewall (allow SSH only)"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow "${SSH_PORT}"/tcp comment "ssh"
ufw --force enable

log "5/7  enable automatic security updates"
dpkg-reconfigure -f noninteractive unattended-upgrades || true
cat > /etc/apt/apt.conf.d/20auto-upgrades <<EOF
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

log "6/7  fail2ban (SSH brute-force protection)"
systemctl enable --now fail2ban

log "7/7  harden SSH (disable password auth)"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh

log "DONE"
cat <<EOF

  Bootstrap complete.

  Next steps (run as ${APP_USER}, not root):

    su - ${APP_USER}
    git clone <your-repo> ~/breaking-news-agent
    cd ~/breaking-news-agent
    bash scripts/deploy.sh

EOF
