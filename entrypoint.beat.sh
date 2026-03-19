#!/bin/bash
# =============================================================================
# Horilla HRMS — Celery Beat (scheduler) entrypoint
# Triggers: auto payslip generation, contract expiry, etc.
# Run exactly ONE instance of this — never scale it horizontally.
# =============================================================================
set -e

echo "──────────────────────────────────────────"
echo " Horilla HRMS — Starting Celery Beat"
echo "──────────────────────────────────────────"

echo "Waiting for web service to complete migrations..."
sleep 15

exec celery -A horilla beat \
    --loglevel="${CELERY_LOG_LEVEL:-info}" \
    --scheduler django_celery_beat.schedulers:DatabaseScheduler
