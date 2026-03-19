"""
horilla/celery.py

Celery application entry point for Horilla HRMS.

Queue architecture
──────────────────
  high_priority    → Biometric device pings, critical alerts.
                     Workers: 4 concurrency, short ack timeout.
  bulk_processing  → Monthly payroll generation, bulk PDF export.
                     Workers: 2 concurrency, generous soft/hard time limit.
  default          → Everything else (single payslip PDF, notifications).
  dead_letter      → Tasks routed here after max_retries exhausted.
                     Workers: 1 concurrency, human review required.

Starting workers (example)
──────────────────────────
  # One terminal per queue (or use supervisord/systemd in production)
  celery -A horilla worker -Q high_priority    -c 4 -n high@%h    --loglevel=info
  celery -A horilla worker -Q bulk_processing  -c 2 -n bulk@%h    --loglevel=info
  celery -A horilla worker -Q default          -c 4 -n default@%h --loglevel=info
  celery -A horilla worker -Q dead_letter      -c 1 -n dlq@%h     --loglevel=warning

  # Beat scheduler (replaces APScheduler for periodic tasks)
  celery -A horilla beat --loglevel=info

Monitor
───────
  celery -A horilla flower --port=5555
"""

import os

from celery import Celery
from celery.signals import task_failure, task_prerun, task_success
from celery.utils.log import get_task_logger

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "horilla.settings")

app = Celery("horilla")

# Pull all CELERY_* keys from Django settings (namespace strips the prefix).
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in every INSTALLED_APP.
app.autodiscover_tasks()

# Retry broker connection on worker startup instead of crashing
# (important when starting workers before Redis is fully up in Docker).
app.conf.broker_connection_retry_on_startup = True

logger = get_task_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Signals — sync task state into TaskProgress DB row so the frontend can poll
# ──────────────────────────────────────────────────────────────────────────────


@task_prerun.connect
def on_task_prerun(task_id, task, *args, **kwargs):
    """Mark TaskProgress row as PROGRESS when a worker picks up the task."""
    # Avoid circular import — import inside signal handler.
    try:
        from base.models import TaskProgress

        TaskProgress.objects.filter(task_id=task_id).update(status="PROGRESS")
    except Exception:
        pass  # Never crash a worker because of a signal handler


@task_success.connect
def on_task_success(sender, result, **kwargs):
    """Mark TaskProgress row as SUCCESS on completion."""
    try:
        from base.models import TaskProgress

        TaskProgress.objects.filter(task_id=sender.request.id).update(
            status="SUCCESS",
            result_data=result if isinstance(result, dict) else {"result": str(result)},
        )
    except Exception:
        pass


@task_failure.connect
def on_task_failure(task_id, exception, traceback, sender, **kwargs):
    """Mark TaskProgress row as FAILURE and store the error message."""
    try:
        from base.models import TaskProgress

        TaskProgress.objects.filter(task_id=task_id).update(
            status="FAILURE",
            error_message=f"{type(exception).__name__}: {exception}",
        )
    except Exception:
        pass
