#!/bin/bash
# =============================================================================
# Horilla HRMS — EC2 Deploy Script
# Builds the image locally → copies to EC2 → restarts containers.
# Run this from your LOCAL machine whenever you want to push new code.
#
# Usage:
#   ./aws/deploy-ec2.sh <EC2-IP> <path-to-pem-key>
#   ./aws/deploy-ec2.sh 54.123.45.67 ~/keys/horilla-ec2.pem
#
# Requirements (on your local machine):
#   - docker
#   - ssh + scp
#   - aws CLI (only if using ECR image pull — see OPTION B below)
# =============================================================================
set -euo pipefail

# ── Arguments ─────────────────────────────────────────────────────────────────
EC2_IP="${1:-}"
PEM_KEY="${2:-}"
EC2_USER="${EC2_USER:-ubuntu}"
APP_DIR="${APP_DIR:-/opt/horilla}"

if [[ -z "${EC2_IP}" || -z "${PEM_KEY}" ]]; then
    echo "Usage: $0 <EC2-IP> <path-to-pem-key>"
    echo "  e.g. $0 54.123.45.67 ~/keys/horilla-ec2.pem"
    exit 1
fi

SSH_OPTS="-i ${PEM_KEY} -o StrictHostKeyChecking=no -o ConnectTimeout=15"
SSH="ssh ${SSH_OPTS} ${EC2_USER}@${EC2_IP}"
SCP="scp ${SSH_OPTS}"

IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo "latest")}"

echo "═══════════════════════════════════════════════"
echo "  Horilla HRMS — Deploying to EC2"
echo "  Host   : ${EC2_USER}@${EC2_IP}"
echo "  Tag    : ${IMAGE_TAG}"
echo "  AppDir : ${APP_DIR}"
echo "═══════════════════════════════════════════════"

# ── 1. Test SSH connection ─────────────────────────────────────────────────────
echo ""
echo "[1/6] Testing SSH connection..."
$SSH "echo '  ✓ Connected to EC2'" || {
    echo "ERROR: Cannot connect to ${EC2_IP} — check IP, PEM key, and Security Group (port 22)."
    exit 1
}

# ── 2. Push latest code ────────────────────────────────────────────────────────
# OPTION A (default): copy changed files via rsync / git pull on server
# OPTION B: build image locally, push to ECR, then pull on EC2
#           Uncomment the ECR block below and comment out the git pull block.
echo ""
echo "[2/6] Syncing code to EC2..."

# ── OPTION A: git pull on EC2 server ─────────────────────────────────────────
# (Works if your EC2 has git access to the repo — SSH key or deploy token)
$SSH "
    cd ${APP_DIR}
    echo '  Pulling latest code...'
    git fetch --all
    git reset --hard origin/\$(git rev-parse --abbrev-ref HEAD)
    echo '  ✓ Code updated to: '\$(git rev-parse --short HEAD)
"

# ── OPTION B: build locally, push to ECR, pull on EC2 ────────────────────────
# Uncomment this block (and comment OPTION A above) for CI/CD usage.
# Requires: aws CLI configured locally + EC2 instance profile with ECR pull access.
#
# AWS_REGION="${AWS_REGION:-us-east-1}"
# AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
# ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/horilla-hrms"
#
# echo "  Building image..."
# docker build --platform linux/amd64 --target runtime \
#     -t "${ECR_REPO}:${IMAGE_TAG}" \
#     -t "${ECR_REPO}:latest" .
#
# echo "  Pushing to ECR..."
# aws ecr get-login-password --region "${AWS_REGION}" \
#     | docker login --username AWS --password-stdin "${ECR_REPO}"
# docker push "${ECR_REPO}:${IMAGE_TAG}"
# docker push "${ECR_REPO}:latest"
#
# echo "  Pulling on EC2..."
# $SSH "
#     aws ecr get-login-password --region ${AWS_REGION} \
#         | docker login --username AWS --password-stdin ${ECR_REPO}
#     cd ${APP_DIR}
#     docker compose pull
# "

# ── 3. Check .env file exists on server ───────────────────────────────────────
echo ""
echo "[3/6] Verifying .env file..."
ENV_EXISTS=$($SSH "test -f ${APP_DIR}/.env && echo yes || echo no")
if [[ "${ENV_EXISTS}" == "no" ]]; then
    echo ""
    echo "ERROR: .env file not found at ${APP_DIR}/.env on the server!"
    echo "Copy it first:"
    echo "  scp -i ${PEM_KEY} .env ${EC2_USER}@${EC2_IP}:${APP_DIR}/.env"
    exit 1
fi
echo "  ✓ .env file present"

# ── 4. Build image on EC2 (OPTION A only) ────────────────────────────────────
echo ""
echo "[4/6] Building Docker image on EC2..."
$SSH "
    cd ${APP_DIR}
    docker compose build --no-cache --quiet
    echo '  ✓ Image built: horilla-hrms:${IMAGE_TAG}'
"

# ── 5. Rolling restart ─────────────────────────────────────────────────────────
# Restarts services one at a time so the app stays up during deploys.
# Order: web first (runs migrations), then worker and beat.
echo ""
echo "[5/6] Performing rolling restart..."
$SSH "
    cd ${APP_DIR}

    echo '  Restarting nginx (config reload)...'
    docker compose up -d --no-deps --no-build nginx
    sleep 2

    echo '  Restarting web (runs migrations)...'
    docker compose up -d --no-deps --no-build web
    echo '  Waiting 60s for migrations + startup...'
    sleep 60

    echo '  Checking web health...'
    docker compose ps web

    echo '  Restarting worker...'
    docker compose up -d --no-deps --no-build worker
    sleep 5

    echo '  Restarting beat...'
    docker compose up -d --no-deps --no-build beat

    echo '  ✓ All services restarted'
"

# ── 6. Health check ───────────────────────────────────────────────────────────
echo ""
echo "[6/6] Running post-deploy health check..."
sleep 10

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time 15 \
    "http://${EC2_IP}/health/" 2>/dev/null || echo "000")

if [[ "${HTTP_STATUS}" == "200" ]]; then
    echo "  ✓ Health check passed (HTTP ${HTTP_STATUS})"
else
    echo "  ⚠ Health check returned HTTP ${HTTP_STATUS}"
    echo "  Check logs with:"
    echo "    ssh -i ${PEM_KEY} ${EC2_USER}@${EC2_IP} 'cd ${APP_DIR} && docker compose logs --tail=50 web'"
fi

# Print running services
echo ""
$SSH "cd ${APP_DIR} && docker compose ps"

echo ""
echo "═══════════════════════════════════════════════"
echo "  Deployment complete!"
echo "  App: http://${EC2_IP}"
echo "═══════════════════════════════════════════════"
echo ""
echo "Useful commands:"
echo "  Tail all logs:     ssh -i ${PEM_KEY} ${EC2_USER}@${EC2_IP} 'cd ${APP_DIR} && docker compose logs -f'"
echo "  Web logs only:     ssh -i ${PEM_KEY} ${EC2_USER}@${EC2_IP} 'cd ${APP_DIR} && docker compose logs -f web'"
echo "  Restart a service: ssh -i ${PEM_KEY} ${EC2_USER}@${EC2_IP} 'cd ${APP_DIR} && docker compose restart worker'"
echo ""
