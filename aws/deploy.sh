#!/bin/bash
# =============================================================================
# Horilla HRMS — AWS ECS Deploy Script
# Usage: ./aws/deploy.sh [image-tag]
# Called by GitHub Actions on every push to main.
# =============================================================================
set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME="horilla-hrms"
CLUSTER="horilla-production"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}"
IMAGE_TAG="${1:-$(git rev-parse --short HEAD)}"

echo "════════════════════════════════════════"
echo " Horilla HRMS — Deploying to AWS ECS"
echo " Tag    : ${IMAGE_TAG}"
echo " Region : ${AWS_REGION}"
echo " Account: ${AWS_ACCOUNT_ID}"
echo "════════════════════════════════════════"

# ── 1. Login to ECR ───────────────────────────────────────────────────────────
echo "[1/5] Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin "${ECR_REPO}"

# ── 2. Build image ────────────────────────────────────────────────────────────
echo "[2/5] Building image..."
docker build \
    --platform linux/amd64 \
    --target runtime \
    --cache-from "${ECR_REPO}:latest" \
    -t "${APP_NAME}:${IMAGE_TAG}" \
    -t "${ECR_REPO}:${IMAGE_TAG}" \
    -t "${ECR_REPO}:latest" \
    .

# ── 3. Push to ECR ────────────────────────────────────────────────────────────
echo "[3/5] Pushing to ECR..."
docker push "${ECR_REPO}:${IMAGE_TAG}"
docker push "${ECR_REPO}:latest"

# ── 4. Register task definitions ──────────────────────────────────────────────
echo "[4/5] Registering task definitions..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for service in web worker beat; do
    # Substitute placeholders in task definition
    sed -e "s/ACCOUNT_ID/${AWS_ACCOUNT_ID}/g" \
        -e "s|horilla-hrms:latest|${ECR_REPO}:${IMAGE_TAG}|g" \
        "${SCRIPT_DIR}/task-${service}.json" > "/tmp/task-${service}-resolved.json"

    aws ecs register-task-definition \
        --cli-input-json "file:///tmp/task-${service}-resolved.json" \
        --region "${AWS_REGION}" > /dev/null

    echo "  ✓ task-${service} registered"
done

# ── 5. Update ECS services ────────────────────────────────────────────────────
echo "[5/5] Deploying to ECS..."

aws ecs update-service \
    --cluster "${CLUSTER}" \
    --service horilla-web \
    --task-definition horilla-web \
    --force-new-deployment \
    --region "${AWS_REGION}" > /dev/null

aws ecs update-service \
    --cluster "${CLUSTER}" \
    --service horilla-worker \
    --task-definition horilla-worker \
    --force-new-deployment \
    --region "${AWS_REGION}" > /dev/null

aws ecs update-service \
    --cluster "${CLUSTER}" \
    --service horilla-beat \
    --task-definition horilla-beat \
    --force-new-deployment \
    --region "${AWS_REGION}" > /dev/null

# ── Wait for web service to stabilise ─────────────────────────────────────────
echo "Waiting for web service to become stable..."
aws ecs wait services-stable \
    --cluster "${CLUSTER}" \
    --services horilla-web \
    --region "${AWS_REGION}"

echo ""
echo "════════════════════════════════════════"
echo " Deployment complete!"
echo " Image: ${ECR_REPO}:${IMAGE_TAG}"
echo "════════════════════════════════════════"
