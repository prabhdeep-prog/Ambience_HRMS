# =============================================================================
# Horilla HRMS — Production Dockerfile
# Multi-stage build: builder installs deps, runtime is lean and secure
# =============================================================================

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.10-slim-bullseye AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps needed to compile native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libcairo2-dev \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    wkhtmltopdf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

# Install all Python dependencies into an isolated prefix
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.10-slim-bullseye AS runtime

LABEL maintainer="horilla-hrms" \
      version="1.0" \
      description="Horilla HRMS Production Image"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Tells Django not to use development server
    DJANGO_SETTINGS_MODULE=horilla.settings \
    # Where collectstatic writes files
    STATIC_ROOT=/app/staticfiles \
    # Media files mount point
    MEDIA_ROOT=/app/media \
    PORT=8000

# Minimal runtime system libraries (no dev headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpq5 \
    wkhtmltopdf \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    # Create non-root user for security
    && groupadd --gid 1001 horilla \
    && useradd --uid 1001 --gid horilla --shell /bin/bash --create-home horilla

# Copy compiled packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Copy application source
COPY --chown=horilla:horilla . .

# Create directories that need to be writable
RUN mkdir -p /app/staticfiles /app/media /app/logs \
    && chown -R horilla:horilla /app/staticfiles /app/media /app/logs \
    && chmod +x /app/entrypoint.sh /app/entrypoint.worker.sh /app/entrypoint.beat.sh

# Switch to non-root user
USER horilla

EXPOSE 8000

# Health check — hits Django's /health/ endpoint every 30s
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

CMD ["/app/entrypoint.sh"]
