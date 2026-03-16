#!/bin/bash
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Horilla HRMS — container entrypoint
# ─────────────────────────────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════╗"
echo "║        Horilla HRMS — Starting up        ║"
echo "╚══════════════════════════════════════════╝"

# ── [0/4] Validate required environment variables ────────────────────────────
echo "[0/4] Validating environment..."

MISSING=""

for VAR in SECRET_KEY ADMIN_USERNAME ADMIN_EMAIL ADMIN_PASSWORD; do
    if [ -z "${!VAR:-}" ]; then
        echo "  ERROR: required environment variable '$VAR' is not set."
        MISSING="$MISSING $VAR"
    fi
done

if [ -n "$MISSING" ]; then
    echo ""
    echo "Startup aborted. Set the missing variables and restart the container."
    echo "See .env.example for reference."
    exit 1
fi

echo "  All required variables are present."

# ── [1/4] Apply database migrations ─────────────────────────────────────────
# NOTE: makemigrations is intentionally absent.
# Migration files are developer artifacts committed to git.
# Only 'migrate' (applying committed migrations) runs here.
echo "[1/4] Applying database migrations..."
python3 manage.py migrate --noinput
echo "  Migrations complete."

# ── [2/4] Collect static files ───────────────────────────────────────────────
echo "[2/4] Collecting static files..."
python3 manage.py collectstatic --noinput --clear
echo "  Static files collected."

# ── [3/4] Bootstrap admin user ───────────────────────────────────────────────
# createhorillauser is idempotent — it skips creation if the username exists.
echo "[3/4] Ensuring admin user exists..."
python3 manage.py createhorillauser \
    --first_name "${ADMIN_FIRST_NAME:-Admin}"  \
    --last_name  "${ADMIN_LAST_NAME:-User}"    \
    --username   "${ADMIN_USERNAME}"           \
    --password   "${ADMIN_PASSWORD}"           \
    --email      "${ADMIN_EMAIL}"              \
    --phone      "${ADMIN_PHONE:-0000000000}"
echo "  Admin user ready."

# ── [4/4] Start Gunicorn ─────────────────────────────────────────────────────
WORKERS=$((2 * $(nproc) + 1))

echo "[4/4] Starting Gunicorn with ${WORKERS} workers..."
exec gunicorn horilla.wsgi:application \
    --bind        0.0.0.0:8000         \
    --workers     "${WORKERS}"         \
    --worker-class gthread             \
    --threads     4                    \
    --timeout     120                  \
    --graceful-timeout 30              \
    --access-logfile  -                \
    --error-logfile   -                \
    --log-level   info
