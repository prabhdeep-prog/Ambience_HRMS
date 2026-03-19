#!/bin/bash
# =============================================================================
# Horilla HRMS — Web / Gunicorn entrypoint
# Runs: migrations → collectstatic → gunicorn
# =============================================================================
set -e

echo "──────────────────────────────────────────"
echo " Horilla HRMS — Starting Web Server"
echo "──────────────────────────────────────────"

echo "[1/4] Running database migrations..."
python manage.py migrate --noinput

echo "[2/4] Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "[3/4] Creating superuser (skipped if already exists)..."
python manage.py createhorillauser \
    --first_name "${ADMIN_FIRST_NAME:-Admin}" \
    --last_name "${ADMIN_LAST_NAME:-User}" \
    --username "${ADMIN_USERNAME:-admin}" \
    --password "${ADMIN_PASSWORD:-ChangeMe123!}" \
    --email "${ADMIN_EMAIL:-admin@example.com}" \
    --phone "${ADMIN_PHONE:-0000000000}" 2>/dev/null || true

echo "[4/4] Starting Gunicorn..."
exec gunicorn horilla.wsgi:application \
    --config /app/gunicorn.conf.py \
    --bind "0.0.0.0:${PORT:-8000}"
