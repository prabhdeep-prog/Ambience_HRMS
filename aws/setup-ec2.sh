#!/bin/bash
# =============================================================================
# Horilla HRMS — EC2 One-Time Bootstrap
# Run this ONCE on a fresh Ubuntu 22.04 EC2 instance.
#
# Usage:
#   chmod +x setup-ec2.sh
#   sudo ./setup-ec2.sh
#
# After this script completes:
#   1. Copy your .env file:  scp .env ubuntu@<EC2-IP>:/opt/horilla/.env
#   2. Start the app:        cd /opt/horilla && docker compose up -d --build
#   3. Check logs:           docker compose logs -f web
# =============================================================================
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
APP_DIR="/opt/horilla"
REPO_URL="${REPO_URL:-}"          # set via: REPO_URL=https://github.com/you/repo ./setup-ec2.sh
APP_USER="ubuntu"                 # EC2 default user

echo "═══════════════════════════════════════════════"
echo "  Horilla HRMS — EC2 Server Setup"
echo "  Ubuntu 22.04 LTS"
echo "═══════════════════════════════════════════════"

# ── 1. System update ──────────────────────────────────────────────────────────
echo ""
echo "[1/7] Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    curl \
    git \
    ca-certificates \
    gnupg \
    lsb-release \
    certbot \
    ufw \
    htop \
    unzip

# ── 2. Install Docker ─────────────────────────────────────────────────────────
echo ""
echo "[2/7] Installing Docker..."
if ! command -v docker &> /dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq \
        docker-ce \
        docker-ce-cli \
        containerd.io \
        docker-buildx-plugin \
        docker-compose-plugin
else
    echo "  Docker already installed — skipping."
fi

# Add app user to docker group (no sudo needed for docker commands)
usermod -aG docker "${APP_USER}"
echo "  ✓ Docker $(docker --version)"
echo "  ✓ Docker Compose $(docker compose version)"

# ── 3. Configure firewall ─────────────────────────────────────────────────────
echo ""
echo "[3/7] Configuring firewall (ufw)..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh        # port 22  — keep SSH access
ufw allow http       # port 80  — Nginx
ufw allow https      # port 443 — Nginx (SSL)
ufw --force enable
echo "  ✓ Firewall: SSH + HTTP + HTTPS allowed, everything else denied"

# ── 4. Create app directory ───────────────────────────────────────────────────
echo ""
echo "[4/7] Setting up application directory at ${APP_DIR}..."
mkdir -p "${APP_DIR}"
chown "${APP_USER}:${APP_USER}" "${APP_DIR}"

# Clone repo if URL provided, otherwise just create directory
if [[ -n "${REPO_URL}" ]]; then
    if [[ -d "${APP_DIR}/.git" ]]; then
        echo "  Repo already cloned — pulling latest..."
        git -C "${APP_DIR}" pull
    else
        echo "  Cloning ${REPO_URL}..."
        git clone "${REPO_URL}" "${APP_DIR}"
        chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
    fi
else
    echo "  No REPO_URL set — skipping git clone."
    echo "  Manually copy your project to ${APP_DIR} and re-run, or:"
    echo "    REPO_URL=https://github.com/you/horilla sudo ./setup-ec2.sh"
fi

# ── 5. Create required directories ───────────────────────────────────────────
echo ""
echo "[5/7] Creating runtime directories..."
mkdir -p "${APP_DIR}/nginx/ssl"
mkdir -p "${APP_DIR}/logs/nginx"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/logs"
echo "  ✓ nginx/ssl  (put your SSL certs here)"
echo "  ✓ logs/nginx (nginx access + error logs)"

# ── 6. Install systemd service (auto-start on reboot) ────────────────────────
echo ""
echo "[6/7] Installing systemd service..."
cat > /etc/systemd/system/horilla.service << EOF
[Unit]
Description=Horilla HRMS (Docker Compose)
Documentation=https://github.com/horilla-hrms
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=${APP_USER}
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose up -d --remove-orphans
ExecStop=/usr/bin/docker compose down
ExecReload=/usr/bin/docker compose up -d --remove-orphans
TimeoutStartSec=300
TimeoutStopSec=120
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable horilla.service
echo "  ✓ horilla.service enabled — app will auto-start on every reboot"

# ── 7. Set up log rotation ────────────────────────────────────────────────────
echo ""
echo "[7/7] Configuring log rotation..."
cat > /etc/logrotate.d/horilla << EOF
${APP_DIR}/logs/*.log
${APP_DIR}/logs/nginx/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 ${APP_USER} adm
    sharedscripts
    postrotate
        docker exec \$(docker compose -f ${APP_DIR}/docker-compose.yml ps -q nginx) \
            nginx -s reopen 2>/dev/null || true
    endscript
}
EOF
echo "  ✓ Logs rotate daily, kept for 14 days"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════"
echo "  Setup complete!"
echo "═══════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo ""
echo "  1. Copy your environment file to the server:"
echo "       scp .env ubuntu@<EC2-IP>:${APP_DIR}/.env"
echo ""
echo "  2. SSH into the server and start the app:"
echo "       ssh ubuntu@<EC2-IP>"
echo "       cd ${APP_DIR}"
echo "       docker compose up -d --build"
echo ""
echo "  3. Tail logs to confirm everything started:"
echo "       docker compose logs -f"
echo ""
echo "  4. (Optional) Add SSL with Let's Encrypt:"
echo "       sudo certbot certonly --standalone -d yourdomain.com"
echo "       sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ${APP_DIR}/nginx/ssl/"
echo "       sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem   ${APP_DIR}/nginx/ssl/"
echo "       # Then uncomment the HTTPS blocks in nginx/nginx.conf"
echo "       docker compose restart nginx"
echo ""
echo "  NOTE: Log out and back in for docker group membership to take effect."
echo "        (Or run: newgrp docker)"
echo ""
