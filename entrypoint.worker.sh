#!/bin/bash
# =============================================================================
# Horilla HRMS — Celery Worker entrypoint
# Handles: payroll generation, PDF export, biometric sync
# =============================================================================
set -e

echo "──────────────────────────────────────────"
echo " Horilla HRMS — Starting Celery Worker"
echo "──────────────────────────────────────────"

echo "Waiting for web service to complete migrations..."
sleep 10

exec celery -A horilla worker \
    --loglevel="${CELERY_LOG_LEVEL:-info}" \
    --queues="high_priority,bulk_processing,default,dead_letter" \
    --concurrency="${CELERY_CONCURRENCY:-4}" \
    --max-tasks-per-child="${CELERY_MAX_TASKS:-50}" \
    --without-gossip \
    --without-mingle \
    --without-heartbeat
