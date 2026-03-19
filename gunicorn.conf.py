"""
gunicorn.conf.py

Production Gunicorn configuration for Horilla HRMS.
Target server: 8 CPU cores, 16 GB RAM.

Worker class choice: gthread
─────────────────────────────
Django is a synchronous WSGI framework that mixes I/O-bound work (DB queries,
Redis calls, file reads) with CPU-bound work (payroll calculation, pdfkit PDF
rendering).  Three options exist:

  sync     — 1 request per worker at a time.  Simplest but wastes CPU during
             I/O wait.  For 8 cores you'd need 17 workers just to keep the
             CPUs busy during blocking DB calls.  Memory: 17 × ~150 MB = 2.5 GB.

  gevent   — Async greenlets.  Excellent for pure I/O apps.  Django's ORM and
             most middleware are NOT greenlet-safe (no asyncio support).
             Psycopg2 requires monkey-patching.  Risk of subtle data-race bugs.

  gthread  — Each worker spawns a pool of OS threads.  Threads share the
             process heap (lower memory than extra workers) and Python's GIL is
             released during I/O waits (DB, Redis, file), so threads stay busy.
             This is the correct choice for Django + PostgreSQL under load.

Worker and thread count calculation
────────────────────────────────────
  Formula for gthread:
    workers = (CPU cores) + 1           = 9
    threads = 2–4 per worker            = 4
    Total concurrent requests           = 9 × 4 = 36

  Why not use the async formula (2 × cores + 1 = 17 workers)?
    → With gthread, each worker handles multiple requests via threads.
      17 workers × 1 thread = same concurrency as 9 workers × 4 threads (≈36),
      but 17 workers × 150 MB = 2.55 GB vs 9 workers × 150 MB = 1.35 GB.
      Threads are ~10 MB each: 9 × 4 = 36 threads × 10 MB = 360 MB.
      Total memory with gthread: ~1.71 GB vs 2.55 GB sync — saves ~840 MB.

  Why not more threads (e.g. 8)?
    → Django uses database connections per thread (not per process with gthread).
      9 workers × 8 threads = 72 DB connections.  At CONN_MAX_AGE=60 these
      stay open, and PostgreSQL's default max_connections=100 would be at risk.
      With threads=4: 9 × 4 = 36 connections — safe headroom for pgBouncer too.

  Memory budget check (16 GB server):
    OS + system services:  ~2 GB
    PostgreSQL:            ~2 GB
    Redis:                 ~1 GB
    9 Gunicorn workers:    ~1.35 GB (9 × 150 MB base)
    Thread overhead:       ~0.36 GB (36 threads × 10 MB)
    Celery workers (bulk): ~0.30 GB (2 workers × 150 MB)
    Celery workers (high): ~0.60 GB (4 workers × 150 MB)
    Celery beat:           ~0.15 GB
    Nginx/reverse proxy:   ~0.05 GB
    ─────────────────────────────
    Total:                 ~7.81 GB   ← well within 16 GB, ~8 GB headroom
                                          for OS cache and traffic spikes.

Thundering Herd during cache stampede
──────────────────────────────────────
  Gunicorn itself is not involved in stampede prevention — that's handled by
  horilla/cache_utils.py StampedeProtectedCache.  Each of the 9 worker
  processes races for the Redis lock via cache.add() (SET NX EX).  Only the
  winner recomputes; the other 8 serve the stale copy instantly.

  With 9 workers × 4 threads = 36 concurrent requests hitting an expired
  dashboard cache, only 1 DB query fires.  The other 35 requests return in
  <1 ms from Redis (stale copy).

Request timeout strategy
────────────────────────
  timeout=120     Standard requests (API, page loads, dashboard) must finish
                  within 2 minutes before Gunicorn kills the worker.

  IMPORTANT: Bulk payroll PDF generation (pdfkit × 1 000 employees) takes
  much longer.  Those views dispatch to Celery instead of running in-process.
  See payroll/tasks.py → bulk_export_payslip_pdf.  Never serve long-running
  jobs synchronously through Gunicorn.

  graceful_timeout=30   On SIGTERM (rolling deploy), workers finish their
                        current requests within 30 s before shutting down.
                        This ensures zero dropped requests during deployments.

max_requests + jitter
─────────────────────
  pdfkit spawns a wkhtmltopdf subprocess that leaks memory slightly over time.
  max_requests=1000 recycles a worker after 1 000 requests.  Without the
  jitter all 9 workers would recycle simultaneously (thundering herd for the
  process pool).  max_requests_jitter=100 spreads the recycling over ±100
  requests so at most 1–2 workers restart at any moment.
"""

import multiprocessing
import os

# ── Binding ────────────────────────────────────────────────────────────────────
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# ── Worker class ──────────────────────────────────────────────────────────────
worker_class = "gthread"

# ── Worker and thread count ───────────────────────────────────────────────────
# Reads CPU count at runtime so the same config file works on any server size.
# Hard-coded for 8-core / 16 GB as calculated above; override with env vars.
workers = int(os.environ.get("GUNICORN_WORKERS", multiprocessing.cpu_count() + 1))
threads = int(os.environ.get("GUNICORN_THREADS", 4))

# ── Timeouts ──────────────────────────────────────────────────────────────────
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 120))
graceful_timeout = 30
keepalive = 5           # seconds to keep idle HTTP/1.1 connections open

# ── Worker recycling (memory leak prevention) ─────────────────────────────────
max_requests = 1000
max_requests_jitter = 100

# ── Logging ───────────────────────────────────────────────────────────────────
# "-" sends logs to stdout/stderr — correct for Docker / systemd journal.
# Set GUNICORN_ACCESS_LOG to a file path to write to disk instead.
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# ── Process naming ────────────────────────────────────────────────────────────
proc_name = "horilla"

# ── Security ──────────────────────────────────────────────────────────────────
# Limit request line length (protects against certain header-overflow attacks).
limit_request_line = 8190
limit_request_fields = 100

# ── Server hooks ──────────────────────────────────────────────────────────────

def on_starting(server):
    server.log.info(
        "Horilla Gunicorn starting — workers=%d threads=%d worker_class=%s",
        workers, threads, worker_class,
    )


def worker_exit(server, worker):
    """Close Django DB connections cleanly when a worker exits."""
    from django.db import connections
    for conn in connections.all():
        conn.close()
