"""
biometric/tasks.py

Celery tasks for biometric device synchronisation.

Why background tasks for biometrics?
─────────────────────────────────────
  Connecting to a ZKTeco / Dahua / COSEC device over TCP takes 100 ms–5 s
  depending on network conditions and the number of stored punch records.
  Syncing 50 devices serially in a web request would cause a 2–4 minute
  timeout.  These tasks:
    • Run in the high_priority queue (fast workers, short pre-fetch).
    • Sync each device independently so a single unresponsive device does not
      block the others.
    • Retry with back-off on network errors (the most common failure mode).
    • Route permanently failed devices to the dead_letter queue.

Queue routing
─────────────
  biometric.tasks.sync_biometric_device       → high_priority
  biometric.tasks.sync_all_biometric_devices  → high_priority

  (Configured in horilla/settings.py CELERY_TASK_ROUTES)
"""

import logging

from celery import group, shared_task

logger = logging.getLogger(__name__)

# ── Retry policy ──────────────────────────────────────────────────────────────
_DEVICE_MAX_RETRIES = 3      # per-device sync
_BULK_MAX_RETRIES = 1        # orchestrator


def _route_to_dlq(task_fn, kwargs: dict, task_progress_id=None):
    """Re-publish to dead_letter queue and mark TaskProgress if provided."""
    if task_progress_id:
        try:
            from base.models import TaskProgress
            TaskProgress.objects.filter(pk=task_progress_id).update(
                retries_exhausted=True, status="FAILURE"
            )
        except Exception:
            pass
    try:
        task_fn.apply_async(
            kwargs={**kwargs, "_dlq": True},
            queue="dead_letter",
            countdown=0,
            max_retries=0,
        )
        logger.warning(
            "[DLQ] %s routed to dead_letter. device_id=%s",
            task_fn.name,
            kwargs.get("device_id"),
        )
    except Exception as exc:
        logger.error("Failed to route biometric task to DLQ: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Single device sync
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="biometric.tasks.sync_biometric_device",
    queue="high_priority",
    max_retries=_DEVICE_MAX_RETRIES,
    soft_time_limit=270,   # 4.5 min soft (large device may have thousands of records)
    time_limit=360,        # 6 min hard kill
    acks_late=True,
)
def sync_biometric_device(
    self,
    device_id: int,
    task_progress_id: int = None,
    _dlq: bool = False,
):
    """
    Fetch attendance logs from a single biometric device and persist them as
    Attendance records.

    Delegates to the device-type-specific sync functions that are already
    implemented in biometric/views.py (zk_biometric_attendance_logs, etc.).

    Returns
    ───────
    dict with keys:
      status          "success" | "not_found" | "connection_error" | "dead_letter"
      device_id       int
      machine_type    str  (zk / anviz / cosec / dahua / etimeoffice)
      records_synced  int  (0 on error)
      error           str  (present on failure)
    """
    if _dlq:
        logger.warning("[DLQ] sync_biometric_device: device_id=%d", device_id)
        return {"status": "dead_letter", "device_id": device_id}

    from biometric.models import BiometricDevices

    # Import the sync functions that already exist in views.py
    # We call them directly (without an HttpRequest) by extracting the logic.
    # This avoids duplicating the ZK/COSEC/Dahua protocol handling.
    try:
        from biometric.views import (
            anviz_biometric_attendance_logs,
            cosec_biometric_attendance_logs,
            dahua_biometric_attendance_logs,
            etimeoffice_biometric_attendance_logs,
            zk_biometric_attendance_logs,
        )
    except ImportError as exc:
        logger.error("Could not import biometric sync functions: %s", exc)
        return {"status": "import_error", "device_id": device_id, "error": str(exc)}

    progress = None
    if task_progress_id:
        try:
            from base.models import TaskProgress
            progress = TaskProgress.objects.get(pk=task_progress_id)
        except Exception:
            pass

    try:
        device = BiometricDevices.objects.filter(pk=device_id).first()
        if not device:
            logger.warning("BiometricDevice pk=%d not found.", device_id)
            return {"status": "not_found", "device_id": device_id, "records_synced": 0}

        machine_type = device.machine_type
        logger.info(
            "Starting sync: device=%d type=%s ip=%s",
            device_id, machine_type, device.machine_ip,
        )

        # ── Dispatch to the correct protocol handler ──────────────────────────
        if machine_type == "zk":
            result = zk_biometric_attendance_logs(device)
            attendance_count, error_message = (
                result if isinstance(result, tuple) else (result, None)
            )
        elif machine_type == "anviz":
            attendance_count = anviz_biometric_attendance_logs(device)
            error_message = None if isinstance(attendance_count, int) else attendance_count
        elif machine_type == "cosec":
            attendance_count = cosec_biometric_attendance_logs(device)
            error_message = None if isinstance(attendance_count, int) else attendance_count
        elif machine_type == "dahua":
            attendance_count = dahua_biometric_attendance_logs(device)
            error_message = None if isinstance(attendance_count, int) else attendance_count
        elif machine_type == "etimeoffice":
            attendance_count = etimeoffice_biometric_attendance_logs(device)
            error_message = None if isinstance(attendance_count, int) else attendance_count
        else:
            logger.error("Unknown machine_type '%s' for device=%d", machine_type, device_id)
            return {
                "status": "unsupported_type",
                "device_id": device_id,
                "machine_type": machine_type,
                "records_synced": 0,
            }

        # ── Evaluate result ───────────────────────────────────────────────────
        if isinstance(attendance_count, int):
            logger.info(
                "Sync complete: device=%d type=%s records=%d",
                device_id, machine_type, attendance_count,
            )
            if progress:
                progress.increment_completed()
            return {
                "status": "success",
                "device_id": device_id,
                "machine_type": machine_type,
                "records_synced": attendance_count,
            }
        else:
            # Protocol returned an error string instead of an int.
            raise ConnectionError(
                f"Device {device_id} ({machine_type}) sync error: {error_message}"
            )

    except ConnectionError as exc:
        logger.warning(
            "sync_biometric_device connection error: device=%d attempt=%d/%d error=%s",
            device_id, self.request.retries + 1, self.max_retries + 1, exc,
        )
        if progress:
            progress.increment_failed()
        retry_kwargs = dict(device_id=device_id, task_progress_id=task_progress_id)
        if self.request.retries < self.max_retries:
            # Exponential back-off: 30 s, 60 s, 120 s
            raise self.retry(
                exc=exc,
                countdown=30 * (2 ** self.request.retries),
                kwargs=retry_kwargs,
            )
        _route_to_dlq(sync_biometric_device, retry_kwargs, task_progress_id)
        return {"status": "dead_letter", "device_id": device_id, "error": str(exc)}

    except Exception as exc:
        logger.exception("sync_biometric_device unexpected error: device=%d error=%s", device_id, exc)
        if progress:
            progress.increment_failed()
        retry_kwargs = dict(device_id=device_id, task_progress_id=task_progress_id)
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=30 * (2 ** self.request.retries),
                kwargs=retry_kwargs,
            )
        _route_to_dlq(sync_biometric_device, retry_kwargs, task_progress_id)
        return {"status": "dead_letter", "device_id": device_id, "error": str(exc)}


# ──────────────────────────────────────────────────────────────────────────────
# 2. Sync all scheduled devices (fan-out orchestrator)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="biometric.tasks.sync_all_biometric_devices",
    queue="high_priority",
    max_retries=_BULK_MAX_RETRIES,
    soft_time_limit=60,    # Finding devices is fast; the real work is in sub-tasks
    time_limit=90,
    acks_late=True,
)
def sync_all_biometric_devices(
    self,
    task_progress_id: int = None,
    _dlq: bool = False,
):
    """
    Fan-out orchestrator: finds all enabled devices that have a scheduler
    configured and dispatches one sync_biometric_device sub-task per device.

    Called by Celery Beat every 30 minutes (see CELERY_BEAT_SCHEDULE in
    settings.py).  Each device syncs independently so a single unreachable
    device does not delay the others.
    """
    if _dlq:
        logger.warning("[DLQ] sync_all_biometric_devices in dead_letter queue.")
        return {"status": "dead_letter"}

    from biometric.models import BiometricDevices

    try:
        scheduled_devices = BiometricDevices.objects.filter(
            is_scheduler=True
        ).values_list("id", flat=True)
        device_ids = list(scheduled_devices)

        if not device_ids:
            logger.info("sync_all_biometric_devices: no scheduled devices found.")
            return {"status": "success", "device_count": 0}

        # Update total so a TaskProgress bar (if provided) has a denominator.
        if task_progress_id:
            try:
                from base.models import TaskProgress
                TaskProgress.objects.filter(pk=task_progress_id).update(
                    total_items=len(device_ids)
                )
            except Exception:
                pass

        # Fire all device tasks in parallel — each runs in high_priority.
        tasks = group(
            sync_biometric_device.s(
                device_id=d_id,
                task_progress_id=task_progress_id,
            )
            for d_id in device_ids
        )
        tasks.apply_async()

        logger.info(
            "sync_all_biometric_devices: dispatched %d device tasks.",
            len(device_ids),
        )
        return {"status": "dispatched", "device_count": len(device_ids)}

    except Exception as exc:
        logger.exception("sync_all_biometric_devices failed: %s", exc)
        retry_kwargs = dict(task_progress_id=task_progress_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=30, kwargs=retry_kwargs)
        _route_to_dlq(sync_all_biometric_devices, retry_kwargs, task_progress_id)
        return {"status": "dead_letter"}
