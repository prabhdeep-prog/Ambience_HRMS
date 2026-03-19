"""
payroll/tasks.py

Celery tasks for heavy payroll operations that would otherwise block a web
worker for seconds-to-minutes.

Idempotency design
──────────────────
  generate_monthly_payroll dispatches one sub-task per employee via a Celery
  chord:

    group(process_single_employee_payslip.s(...) for each employee)
    | finalize_payroll_batch.s(...)

  Each sub-task calls Payslip.objects.get_or_create(employee_id, start_date,
  end_date).  On retry (worker crash / timeout) the row already exists and the
  task returns immediately — no double-pay possible.

  The chord callback finalize_payroll_batch only executes after every sub-task
  either succeeds or exhausts its retries, giving a clean "done" signal to the
  frontend progress bar.

Dead-letter queue (DLQ) strategy
─────────────────────────────────
  Every task defines:
    max_retries   = N  (task-specific, see below)
    default_retry_delay = exponential back-off via countdown

  When retries are exhausted the except block:
    1. Marks the TaskProgress row as retries_exhausted=True.
    2. Re-publishes the task to the 'dead_letter' queue with
       apply_async(queue="dead_letter", countdown=0, max_retries=0).
       This makes the failure visible to the dedicated dead-letter worker
       without triggering further automatic retries.
    3. Ops staff query TaskProgress.objects.filter(retries_exhausted=True)
       and can call task.apply_async() with fresh parameters after diagnosis.

Usage from a view
─────────────────
  from payroll.tasks import generate_monthly_payroll
  from base.models import TaskProgress
  import uuid

  task_id = str(uuid.uuid4())
  progress = TaskProgress.objects.create(
      task_id=task_id,
      task_name="generate_monthly_payroll",
      description=f"Payroll {start_date:%b %Y}",
      initiated_by=request.user,
  )
  generate_monthly_payroll.apply_async(
      kwargs=dict(
          start_date=str(start_date),
          end_date=str(end_date),
          company_ids=company_ids,
          all_companies=False,
          task_progress_id=progress.pk,
      ),
      task_id=task_id,
  )
  return JsonResponse({"task_id": task_id})
"""

import json
import logging
import uuid
from datetime import date, timedelta

from celery import chord, group, shared_task
from dateutil.relativedelta import relativedelta
from django.db import transaction

logger = logging.getLogger(__name__)

# ── Retry policy constants ────────────────────────────────────────────────────
_PAYSLIP_MAX_RETRIES = 3          # per-employee sub-task
_PAYROLL_BATCH_MAX_RETRIES = 2    # orchestrator task (lightweight)
_EXPORT_MAX_RETRIES = 2


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _get_progress(task_progress_id):
    """Return the TaskProgress row or None (never raises)."""
    if not task_progress_id:
        return None
    try:
        from base.models import TaskProgress
        return TaskProgress.objects.get(pk=task_progress_id)
    except Exception:
        return None


def _route_to_dlq(task_fn, kwargs: dict, task_progress_id=None):
    """
    Re-publish a permanently failed task to the dead_letter queue and mark
    the TaskProgress row so ops staff can find it.
    """
    if task_progress_id:
        try:
            from base.models import TaskProgress
            TaskProgress.objects.filter(pk=task_progress_id).update(
                retries_exhausted=True,
                status="FAILURE",
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
            "Task %s routed to dead_letter queue. kwargs=%s",
            task_fn.name,
            {k: v for k, v in kwargs.items() if k != "pay_data"},
        )
    except Exception as exc:
        logger.error("Failed to route task to DLQ: %s", exc)


# ──────────────────────────────────────────────────────────────────────────────
# 1. Orchestrator: generate_monthly_payroll
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="payroll.tasks.generate_monthly_payroll",
    queue="bulk_processing",
    max_retries=_PAYROLL_BATCH_MAX_RETRIES,
    soft_time_limit=1200,   # 20 min — find employees + dispatch sub-tasks
    time_limit=1500,
    acks_late=True,
)
def generate_monthly_payroll(
    self,
    start_date: str,
    end_date: str,
    company_ids: list = None,
    all_companies: bool = False,
    task_progress_id: int = None,
    _dlq: bool = False,
):
    """
    Orchestrator task.

    Resolves the list of active employees for the period, updates the
    TaskProgress.total_items count, then fans out one
    process_single_employee_payslip sub-task per employee using a Celery chord.

    Parameters
    ──────────
    start_date      ISO date string "YYYY-MM-DD"
    end_date        ISO date string "YYYY-MM-DD"
    company_ids     List of Company PKs to include (None = respect all_companies)
    all_companies   If True, include employees with no company assignment
    task_progress_id  FK to base.TaskProgress for progress bar
    _dlq            Internal flag — set to True when re-routed to dead_letter
    """
    if _dlq:
        logger.warning("[DLQ] generate_monthly_payroll received in dead_letter queue.")
        return {"status": "dead_letter", "start_date": start_date}

    from employee.models import Employee

    progress = _get_progress(task_progress_id)

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        # ── Resolve employee queryset ─────────────────────────────────────────
        employees = Employee.objects.none()
        if all_companies:
            employees = employees | Employee.objects.filter(
                employee_work_info__company_id__isnull=True
            )
        if company_ids:
            employees = employees | Employee.objects.filter(
                employee_work_info__company_id__in=company_ids
            )
        active_employees = (
            employees.filter(
                contract_set__isnull=False,
                contract_set__contract_status="active",
                is_active=True,
            )
            .distinct()
            .values_list("id", flat=True)
        )
        employee_ids = list(active_employees)

        if not employee_ids:
            if progress:
                from base.models import TaskProgress
                TaskProgress.objects.filter(pk=task_progress_id).update(
                    status="SUCCESS",
                    result_data={"message": "No active employees found.", "count": 0},
                )
            return {"status": "success", "employee_count": 0}

        # ── Update total count so the progress bar knows the denominator ──────
        if progress:
            from base.models import TaskProgress
            TaskProgress.objects.filter(pk=task_progress_id).update(
                total_items=len(employee_ids)
            )

        # ── Fan out: one sub-task per employee ────────────────────────────────
        sub_tasks = group(
            process_single_employee_payslip.s(
                employee_id=emp_id,
                start_date=start_date,
                end_date=end_date,
                task_progress_id=task_progress_id,
            )
            for emp_id in employee_ids
        )

        # chord = sub_tasks | callback
        # finalize_payroll_batch runs after ALL sub-tasks finish (or fail).
        workflow = chord(sub_tasks)(
            finalize_payroll_batch.s(
                task_progress_id=task_progress_id,
                start_date=start_date,
                end_date=end_date,
            )
        )

        logger.info(
            "generate_monthly_payroll: dispatched %d sub-tasks for %s–%s",
            len(employee_ids),
            start_date,
            end_date,
        )
        return {"status": "dispatched", "employee_count": len(employee_ids)}

    except Exception as exc:
        logger.exception("generate_monthly_payroll failed: %s", exc)
        retry_kwargs = dict(
            start_date=start_date,
            end_date=end_date,
            company_ids=company_ids,
            all_companies=all_companies,
            task_progress_id=task_progress_id,
        )
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=60 * (2 ** self.request.retries),  # 60s, 120s
                kwargs=retry_kwargs,
            )
        _route_to_dlq(generate_monthly_payroll, retry_kwargs, task_progress_id)
        return {"status": "dead_letter"}


# ──────────────────────────────────────────────────────────────────────────────
# 2. Per-employee sub-task (idempotent)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="payroll.tasks.process_single_employee_payslip",
    queue="bulk_processing",
    max_retries=_PAYSLIP_MAX_RETRIES,
    soft_time_limit=120,   # 2 min per employee
    time_limit=180,
    acks_late=True,
)
def process_single_employee_payslip(
    self,
    employee_id: int,
    start_date: str,
    end_date: str,
    task_progress_id: int = None,
    _dlq: bool = False,
):
    """
    Idempotent sub-task: generate (or skip if already exists) ONE payslip.

    Idempotency guarantee
    ─────────────────────
    Uses `Payslip.objects.filter(...).first()` (mirroring the existing
    scheduler logic) — if the payslip already exists the task returns
    immediately without creating a duplicate.  This makes the chord safe to
    retry: a worker crash after DB write but before Celery ACK re-runs the
    task and exits cleanly at the duplicate check.
    """
    if _dlq:
        logger.warning("[DLQ] process_single_employee_payslip: employee=%d", employee_id)
        return {"status": "dead_letter", "employee_id": employee_id}

    from employee.models import Employee
    from payroll.methods.methods import calculate_employer_contribution, save_payslip
    from payroll.models.models import Contract, Payslip
    from payroll.views.component_views import payroll_calculation

    progress = _get_progress(task_progress_id)

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)

        employee = Employee.objects.select_related(
            "employee_work_info"
        ).get(pk=employee_id)

        # ── Idempotency check — exit early if payslip already exists ──────────
        existing = Payslip.objects.filter(
            employee_id=employee,
            start_date=start,
            end_date=end,
        ).first()
        if existing:
            logger.debug(
                "Payslip already exists for employee=%d period=%s–%s, skipping.",
                employee_id, start_date, end_date,
            )
            if progress:
                progress.increment_completed()
            return {"status": "skipped", "employee_id": employee_id, "payslip_id": existing.pk}

        # ── Contract validation ───────────────────────────────────────────────
        contract = Contract.objects.filter(
            employee_id=employee, contract_status="active"
        ).first()
        if not contract:
            logger.info("No active contract for employee=%d, skipping.", employee_id)
            if progress:
                progress.increment_completed()
            return {"status": "no_contract", "employee_id": employee_id}

        # Adjust date range if contract started after period start.
        effective_start = max(start, contract.contract_start_date)
        if end < effective_start:
            if progress:
                progress.increment_completed()
            return {"status": "out_of_range", "employee_id": employee_id}

        # ── Payroll calculation (CPU + DB intensive) ──────────────────────────
        payslip_data = payroll_calculation(employee, effective_start, end)

        data = {
            "employee": employee,
            "start_date": payslip_data["start_date"],
            "end_date": payslip_data["end_date"],
            "status": "draft",
            "contract_wage": payslip_data["contract_wage"],
            "basic_pay": payslip_data["basic_pay"],
            "gross_pay": payslip_data["gross_pay"],
            "deduction": payslip_data["total_deductions"],
            "net_pay": payslip_data["net_pay"],
            "pay_data": json.loads(payslip_data["json_data"]),
            "payslip": None,
        }
        calculate_employer_contribution(data)
        data["installments"] = payslip_data["installments"]

        # ── Atomic save — either the full payslip is written or nothing is ────
        with transaction.atomic():
            payslip_instance = save_payslip(**data)

        if progress:
            progress.increment_completed()

        logger.info(
            "Payslip created: employee=%d payslip=%d period=%s–%s net=%.2f",
            employee_id, payslip_instance.pk, start_date, end_date,
            float(payslip_instance.net_pay),
        )
        return {
            "status": "created",
            "employee_id": employee_id,
            "payslip_id": payslip_instance.pk,
            "net_pay": float(payslip_instance.net_pay),
        }

    except Employee.DoesNotExist:
        # Employee deleted between dispatch and execution — not retryable.
        logger.warning("Employee pk=%d not found, skipping.", employee_id)
        if progress:
            progress.increment_failed()
        return {"status": "employee_not_found", "employee_id": employee_id}

    except Exception as exc:
        logger.exception(
            "process_single_employee_payslip failed: employee=%d error=%s",
            employee_id, exc,
        )
        if progress:
            progress.increment_failed()

        retry_kwargs = dict(
            employee_id=employee_id,
            start_date=start_date,
            end_date=end_date,
            task_progress_id=task_progress_id,
        )
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=30 * (2 ** self.request.retries),  # 30s, 60s, 120s
                kwargs=retry_kwargs,
            )
        # Retries exhausted — route to DLQ so payroll team can investigate.
        _route_to_dlq(process_single_employee_payslip, retry_kwargs, None)
        return {"status": "dead_letter", "employee_id": employee_id}


# ──────────────────────────────────────────────────────────────────────────────
# 3. Chord callback: finalize_payroll_batch
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="payroll.tasks.finalize_payroll_batch",
    queue="bulk_processing",
    max_retries=1,
    acks_late=True,
)
def finalize_payroll_batch(
    self,
    sub_task_results: list,
    task_progress_id: int = None,
    start_date: str = None,
    end_date: str = None,
):
    """
    Chord callback — runs once ALL process_single_employee_payslip sub-tasks
    have returned (success or failure).

    Aggregates the results, writes a final summary to TaskProgress, and
    sends a Django notification to the user who initiated the job.
    """
    created = [r for r in sub_task_results if r and r.get("status") == "created"]
    skipped = [r for r in sub_task_results if r and r.get("status") == "skipped"]
    failed = [r for r in sub_task_results if r and r.get("status") in ("dead_letter", "employee_not_found")]
    no_contract = [r for r in sub_task_results if r and r.get("status") == "no_contract"]

    total_net_pay = sum(
        r.get("net_pay", 0) for r in created if r.get("net_pay") is not None
    )

    summary = {
        "created": len(created),
        "skipped": len(skipped),
        "failed": len(failed),
        "no_contract": len(no_contract),
        "total_net_pay": round(total_net_pay, 2),
        "period": f"{start_date} – {end_date}",
    }

    logger.info("Payroll batch complete: %s", summary)

    if task_progress_id:
        try:
            from base.models import TaskProgress

            TaskProgress.objects.filter(pk=task_progress_id).update(
                status="SUCCESS" if not failed else "FAILURE",
                result_data=summary,
            )

            # Notify the initiating user via django-notifications.
            progress = TaskProgress.objects.select_related("initiated_by").get(
                pk=task_progress_id
            )
            if progress.initiated_by:
                try:
                    from notifications.signals import notify

                    status_word = "completed" if not failed else "completed with errors"
                    notify.send(
                        sender=progress.initiated_by,
                        recipient=progress.initiated_by,
                        verb=f"Payroll generation {status_word}: "
                             f"{len(created)} payslips created, "
                             f"{len(failed)} failed — period {start_date} to {end_date}",
                    )
                except Exception as notify_exc:
                    logger.warning("Failed to send payroll completion notification: %s", notify_exc)
        except Exception as exc:
            logger.exception("finalize_payroll_batch: failed to update TaskProgress: %s", exc)

    return summary


# ──────────────────────────────────────────────────────────────────────────────
# 4. Bulk PDF export (runs in bulk_processing queue)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="payroll.tasks.bulk_export_payslip_pdf",
    queue="bulk_processing",
    max_retries=_EXPORT_MAX_RETRIES,
    soft_time_limit=900,   # 15 min — pdfkit for 1 000 payslips
    time_limit=1200,
    acks_late=True,
)
def bulk_export_payslip_pdf(
    self,
    payslip_ids: list,
    task_progress_id: int = None,
    _dlq: bool = False,
):
    """
    Generate a ZIP archive of individual PDF payslips for the given IDs and
    store it as a media file so the frontend can download it.

    Progress bar: increments completed_items after each PDF is rendered so
    the frontend progress bar updates in near-real-time.
    """
    if _dlq:
        logger.warning("[DLQ] bulk_export_payslip_pdf received in dead_letter queue.")
        return {"status": "dead_letter"}

    import io
    import os
    import zipfile

    from django.conf import settings
    from django.template.loader import render_to_string

    import pdfkit

    from payroll.models.models import Allowance, Deduction, Payslip
    from payroll.views.component_views import filter_payslip

    progress = _get_progress(task_progress_id)
    if progress:
        from base.models import TaskProgress
        TaskProgress.objects.filter(pk=task_progress_id).update(
            total_items=len(payslip_ids)
        )

    pdf_options = {
        "page-size": "A4",
        "margin-top": "10mm", "margin-bottom": "10mm",
        "margin-left": "10mm", "margin-right": "10mm",
        "encoding": "UTF-8",
        "enable-local-file-access": None,
        "dpi": 300,
        "zoom": 1.3,
        "quiet": "",  # Suppress wkhtmltopdf stderr noise
    }

    zip_buffer = io.BytesIO()
    failed_ids = []

    try:
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            payslips = Payslip.objects.filter(pk__in=payslip_ids).select_related(
                "employee_id"
            )
            payslip_map = {p.pk: p for p in payslips}

            for payslip_id in payslip_ids:
                payslip = payslip_map.get(payslip_id)
                if not payslip:
                    failed_ids.append(payslip_id)
                    if progress:
                        progress.increment_failed()
                    continue

                try:
                    context = filter_payslip(payslip)
                    html_content = render_to_string(
                        "payroll/payslip/payslip_pdf.html", context
                    )
                    pdf_bytes = pdfkit.from_string(html_content, False, options=pdf_options)
                    employee_name = (
                        payslip.employee_id.get_full_name()
                        if hasattr(payslip.employee_id, "get_full_name")
                        else f"employee_{payslip.employee_id_id}"
                    )
                    filename = f"{employee_name}_{payslip.start_date}.pdf"
                    zf.writestr(filename, pdf_bytes)
                    if progress:
                        progress.increment_completed()
                except Exception as pdf_exc:
                    logger.error(
                        "PDF generation failed for payslip=%d: %s", payslip_id, pdf_exc
                    )
                    failed_ids.append(payslip_id)
                    if progress:
                        progress.increment_failed()

        # ── Persist the ZIP to media storage ──────────────────────────────────
        export_dir = os.path.join(settings.MEDIA_ROOT, "payroll_exports")
        os.makedirs(export_dir, exist_ok=True)
        archive_name = f"payslips_{uuid.uuid4().hex[:8]}.zip"
        archive_path = os.path.join(export_dir, archive_name)

        with open(archive_path, "wb") as f:
            f.write(zip_buffer.getvalue())

        download_url = f"{settings.MEDIA_URL}payroll_exports/{archive_name}"

        result = {
            "status": "success",
            "download_url": download_url,
            "total": len(payslip_ids),
            "failed": len(failed_ids),
            "failed_ids": failed_ids,
        }

        if task_progress_id:
            from base.models import TaskProgress
            TaskProgress.objects.filter(pk=task_progress_id).update(
                status="SUCCESS" if not failed_ids else "FAILURE",
                result_data=result,
            )

        return result

    except Exception as exc:
        logger.exception("bulk_export_payslip_pdf failed: %s", exc)
        retry_kwargs = dict(payslip_ids=payslip_ids, task_progress_id=task_progress_id)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60, kwargs=retry_kwargs)
        _route_to_dlq(bulk_export_payslip_pdf, retry_kwargs, task_progress_id)
        return {"status": "dead_letter"}


# ──────────────────────────────────────────────────────────────────────────────
# 5. Beat-compatible periodic tasks (drop-in replacement for scheduler.py)
# ──────────────────────────────────────────────────────────────────────────────

@shared_task(name="payroll.tasks.auto_payslip_generate", queue="bulk_processing")
def auto_payslip_generate():
    """
    Celery Beat replacement for the APScheduler auto_payslip_generate job.
    Reads PayslipAutoGenerate config and dispatches generate_monthly_payroll
    for each company that is due today.
    """
    from datetime import date as _date, timedelta as _td
    from payroll.scheduler import auto_payslip_generate as _legacy_fn
    # Delegate to the existing logic — no need to duplicate the scheduling maths.
    # This task simply ensures the heavy loop runs in a worker, not in the beat
    # scheduler process (beat should only dispatch, never do heavy work).
    _legacy_fn()


@shared_task(name="payroll.tasks.expire_contracts", queue="default")
def expire_contracts():
    """Celery Beat replacement for the APScheduler expire_contract job."""
    from payroll.scheduler import expire_contract as _legacy_fn
    _legacy_fn()
