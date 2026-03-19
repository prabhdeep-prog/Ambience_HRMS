"""
payroll/views/task_views.py

Views for kicking off background Celery tasks and polling their progress.

The progress bar flow
─────────────────────
  1. User clicks "Generate Payroll for January" in the frontend.
  2. Frontend POSTs to /payroll/tasks/generate-monthly-payroll/.
  3. View creates a TaskProgress row, dispatches the Celery task with the
     TaskProgress.pk, and immediately returns {"task_id": "<uuid>"}.
  4. Frontend polls GET /payroll/tasks/status/<task_id>/ every 2 s.
  5. View returns TaskProgress.as_dict() including progress_percent (0–100).
  6. When status == "SUCCESS" or "FAILURE" the frontend stops polling and
     shows the result summary or error message.

Dead-letter queue endpoint
──────────────────────────
  GET /payroll/tasks/dead-letter/  — lists all TaskProgress rows with
  retries_exhausted=True so the ops team can inspect and re-queue.

  POST /payroll/tasks/dead-letter/<pk>/requeue/  — re-dispatches the task
  with fresh retry counts (admin-only).
"""

import uuid

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST

from base.models import TaskProgress
from horilla.decorators import login_required, permission_required


# ──────────────────────────────────────────────────────────────────────────────
# 1. Dispatch: generate monthly payroll
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@permission_required("payroll.add_payslip")
@require_POST
def start_monthly_payroll(request):
    """
    Kick off generate_monthly_payroll as a background Celery task.

    Expected POST body (JSON or form-encoded):
      start_date     "YYYY-MM-DD"
      end_date       "YYYY-MM-DD"
      company_ids    JSON list of company PKs, e.g. [1, 3]  (optional)
      all_companies  "true" / "false"  (optional, default false)
    """
    import json as _json

    from payroll.tasks import generate_monthly_payroll

    # Parse parameters
    try:
        if request.content_type and "application/json" in request.content_type:
            body = _json.loads(request.body)
        else:
            body = request.POST

        start_date = body.get("start_date", "")
        end_date = body.get("end_date", "")
        company_ids_raw = body.get("company_ids", "[]")
        all_companies = str(body.get("all_companies", "false")).lower() == "true"

        if isinstance(company_ids_raw, str):
            company_ids = _json.loads(company_ids_raw)
        else:
            company_ids = list(company_ids_raw)

        if not start_date or not end_date:
            return JsonResponse({"error": "start_date and end_date are required."}, status=400)

    except Exception as exc:
        return JsonResponse({"error": f"Invalid request body: {exc}"}, status=400)

    # Create progress tracker before dispatch so the UI can start polling
    # immediately (avoids a race where the frontend polls before the row exists).
    task_id = str(uuid.uuid4())
    progress = TaskProgress.objects.create(
        task_id=task_id,
        task_name="generate_monthly_payroll",
        description=f"Payroll {start_date} – {end_date}",
        status="PENDING",
        initiated_by=request.user,
    )

    generate_monthly_payroll.apply_async(
        kwargs=dict(
            start_date=start_date,
            end_date=end_date,
            company_ids=company_ids,
            all_companies=all_companies,
            task_progress_id=progress.pk,
        ),
        task_id=task_id,
    )

    return JsonResponse(
        {
            "task_id": task_id,
            "task_progress_id": progress.pk,
            "poll_url": f"/payroll/tasks/status/{task_id}/",
        },
        status=202,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 2. Dispatch: bulk PDF export
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@permission_required("payroll.view_payslip")
@require_POST
def start_bulk_pdf_export(request):
    """
    Kick off bulk_export_payslip_pdf for a list of payslip PKs.

    Expected POST body:
      payslip_ids   JSON list of Payslip PKs
    """
    import json as _json

    from payroll.tasks import bulk_export_payslip_pdf

    try:
        if request.content_type and "application/json" in request.content_type:
            body = _json.loads(request.body)
        else:
            body = request.POST

        raw = body.get("payslip_ids", "[]")
        payslip_ids = _json.loads(raw) if isinstance(raw, str) else list(raw)
        payslip_ids = [int(x) for x in payslip_ids]

        if not payslip_ids:
            return JsonResponse({"error": "payslip_ids must not be empty."}, status=400)

    except Exception as exc:
        return JsonResponse({"error": f"Invalid request body: {exc}"}, status=400)

    task_id = str(uuid.uuid4())
    progress = TaskProgress.objects.create(
        task_id=task_id,
        task_name="bulk_export_payslip_pdf",
        description=f"PDF export — {len(payslip_ids)} payslips",
        status="PENDING",
        total_items=len(payslip_ids),
        initiated_by=request.user,
    )

    bulk_export_payslip_pdf.apply_async(
        kwargs=dict(
            payslip_ids=payslip_ids,
            task_progress_id=progress.pk,
        ),
        task_id=task_id,
    )

    return JsonResponse(
        {
            "task_id": task_id,
            "task_progress_id": progress.pk,
            "poll_url": f"/payroll/tasks/status/{task_id}/",
        },
        status=202,
    )


# ──────────────────────────────────────────────────────────────────────────────
# 3. Progress polling endpoint
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@require_GET
def task_status(request, task_id: str):
    """
    Returns the current state of a TaskProgress row as JSON.

    The frontend polls this URL every 2 s while status == "PENDING" or
    "PROGRESS" and renders the progress bar from progress_percent.

    Response shape
    ──────────────
    {
        "task_id":          "abc123...",
        "task_name":        "generate_monthly_payroll",
        "description":      "Payroll 2025-01-01 – 2025-01-31",
        "status":           "PROGRESS",          // PENDING|PROGRESS|SUCCESS|FAILURE|REVOKED
        "total_items":      150,
        "completed_items":  73,
        "failed_items":     2,
        "progress_percent": 48.7,
        "retries_exhausted": false,
        "error_message":    "",
        "result_data":      {},
        "created_at":       "2025-01-31T09:00:00+05:30",
        "updated_at":       "2025-01-31T09:02:15+05:30"
    }
    """
    try:
        progress = TaskProgress.objects.get(task_id=task_id)
    except TaskProgress.DoesNotExist:
        # Row not yet created (race condition between dispatch and first poll).
        return JsonResponse(
            {"task_id": task_id, "status": "PENDING", "progress_percent": 0},
            status=202,
        )

    return JsonResponse(progress.as_dict())


# ──────────────────────────────────────────────────────────────────────────────
# 4. Dead-letter queue management
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@permission_required("base.view_taskprogress")
def dead_letter_list(request):
    """
    Lists all permanently failed tasks (retries_exhausted=True).
    Renders a simple table with task name, description, error, and requeue button.
    """
    failed_tasks = TaskProgress.objects.filter(retries_exhausted=True).order_by(
        "-updated_at"
    )
    return render(
        request,
        "payroll/tasks/dead_letter_list.html",
        {"failed_tasks": failed_tasks},
    )


@login_required
@permission_required("base.change_taskprogress")
@require_POST
def requeue_dead_letter(request, task_progress_id: int):
    """
    Re-dispatch a dead-letter task with fresh retry counts.

    This resets retries_exhausted=False and status=PENDING on the existing
    TaskProgress row, then calls the original task function again with the
    same parameters extracted from result_data.

    NOTE: The task itself must be idempotent (payroll tasks are, via the
    Payslip duplicate check).
    """
    try:
        progress = TaskProgress.objects.get(pk=task_progress_id, retries_exhausted=True)
    except TaskProgress.DoesNotExist:
        messages.error(request, _("Task not found or not in dead-letter state."))
        return redirect("dead-letter-list")

    # Reset the tracker
    new_task_id = str(uuid.uuid4())
    TaskProgress.objects.filter(pk=task_progress_id).update(
        task_id=new_task_id,
        status="PENDING",
        retries_exhausted=False,
        error_message="",
        completed_items=0,
        failed_items=0,
    )

    # Re-dispatch based on task_name
    task_fn = _resolve_task_fn(progress.task_name)
    if task_fn is None:
        messages.error(
            request, _(f"Cannot resolve task function for '{progress.task_name}'.")
        )
        return redirect("dead-letter-list")

    # Re-use parameters stored in result_data (best-effort).
    stored_kwargs = progress.result_data.get("original_kwargs", {})
    stored_kwargs["task_progress_id"] = task_progress_id

    task_fn.apply_async(
        kwargs=stored_kwargs,
        task_id=new_task_id,
    )

    messages.success(
        request,
        _(f"Task '{progress.description}' has been re-queued (new ID: {new_task_id[:8]}…)."),
    )
    return redirect("dead-letter-list")


def _resolve_task_fn(task_name: str):
    """Map a task_name string back to the Celery task callable."""
    from payroll.tasks import (
        bulk_export_payslip_pdf,
        generate_monthly_payroll,
        process_single_employee_payslip,
    )
    from biometric.tasks import sync_all_biometric_devices, sync_biometric_device

    _map = {
        "payroll.tasks.generate_monthly_payroll": generate_monthly_payroll,
        "payroll.tasks.process_single_employee_payslip": process_single_employee_payslip,
        "payroll.tasks.bulk_export_payslip_pdf": bulk_export_payslip_pdf,
        "biometric.tasks.sync_biometric_device": sync_biometric_device,
        "biometric.tasks.sync_all_biometric_devices": sync_all_biometric_devices,
    }
    return _map.get(task_name)
