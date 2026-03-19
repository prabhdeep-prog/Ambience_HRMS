"""
dashboard.py

This module is used to write dashboard related views
"""

import datetime

from django.core import serializers
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from base.models import Department, JobPosition
from employee.models import EmployeeWorkInformation
from horilla.decorators import login_required
from recruitment.decorators import manager_can_enter
from recruitment.models import Candidate, Recruitment, SkillZone, Stage


def stage_type_candidate_count(rec, stage_type):
    """
    This method is used find the count of candidate in recruitment
    """
    candidates_count = 0
    for stage_obj in rec.stage_set.filter(stage_type=stage_type):
        candidates_count = candidates_count + len(
            stage_obj.candidate_set.filter(is_active=True)
        )
    return candidates_count


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def dashboard(request):
    """
    Recruitment dashboard — aggregate stats cached 5 min with stampede protection.

    Previous implementation fired 5N queries (N = JobPosition count) for the
    per-job stage breakdown, plus separate loops for manager mapping and
    vacancy totals.

    New implementation collapses the 5N per-stage queries into ONE annotated
    query using conditional COUNT expressions.  The full context dict
    (minus live querysets) is cached; only two lightweight queryset evals
    (onboard_candidates, skill_zone) remain outside the cache.
    """
    from horilla.cache_utils import stampede_cache

    def _compute_stats():
        # ── Per-job stage breakdown: 5N → 1 query ─────────────────────────────
        # Annotate each JobPosition with candidate counts per stage type in a
        # single SQL query instead of 5 separate loops.
        jobs_qs = JobPosition.objects.annotate(
            initial_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="initial"), distinct=True
            ),
            test_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="test"), distinct=True
            ),
            interview_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="interview"), distinct=True
            ),
            hired_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="hired"), distinct=True
            ),
            cancelled_count=Count(
                "candidate", filter=Q(candidate__stage_id__stage_type="cancelled"), distinct=True
            ),
        ).values_list(
            "job_position",
            "initial_count", "test_count", "interview_count",
            "hired_count", "cancelled_count",
        )
        # job_data is a list of (name, initial, test, interview, hired, cancelled)
        job_data = list(jobs_qs)

        # ── Open recruitments ──────────────────────────────────────────────────
        recruitment_qs = (
            Recruitment.objects.filter(closed=False)
            .prefetch_related("recruitment_managers", "stage_set__candidate_set")
        )
        ongoing_recruitments = recruitment_qs.count()
        dep_vacancy = 1 if Recruitment.objects.filter(
            closed=False, is_event_based=False
        ).exists() else 0

        # Stage chart: does ANY open recruitment have ≥1 candidate?
        stage_chart_count = 0
        for rec in recruitment_qs:
            for stage_obj in rec.stage_set.all():
                if stage_obj.candidate_set.filter(is_active=True).exists():
                    stage_chart_count = 1
                    break
            if stage_chart_count:
                break

        # Manager mapping (uses prefetched M2M — no extra queries)
        recruitment_manager_mapping = {}
        total_vacancy = 0
        for rec in recruitment_qs:
            recruitment_manager_mapping[rec.title] = [
                m.get_full_name() for m in rec.recruitment_managers.all()
            ]
            if rec.vacancy:
                total_vacancy += rec.vacancy

        # ── Candidate aggregates ───────────────────────────────────────────────
        candidate_totals = Candidate.objects.aggregate(
            total=Count("id"),
            hired=Count("id", filter=Q(Q(hired=True) | Q(stage_id__stage_type="hired"))),
            accepted=Count("id", filter=Q(offer_letter_status="accepted")),
        )
        total_candidates = candidate_totals["total"]
        total_hired_candidates = candidate_totals["hired"]
        accepted_count = candidate_totals["accepted"]

        # ── Has any employee joined? (single existence check) ─────────────────
        joining = 1 if EmployeeWorkInformation.objects.filter(
            date_joining__isnull=False
        ).exists() else 0

        # ── Ratio calculations ────────────────────────────────────────────────
        conversion_ratio = (
            f"{(total_hired_candidates / total_candidates * 100):.1f}"
            if total_candidates else 0
        )
        hired_ratio = (
            f"{(total_hired_candidates / total_vacancy * 100):.1f}"
            if total_vacancy else 0
        )
        total_candidate_ratio = (
            f"{(total_candidates / total_vacancy * 100):.1f}"
            if total_vacancy else 0
        )
        acceptance_ratio = (
            f"{(accepted_count / total_hired_candidates * 100):.1f}"
            if total_hired_candidates else 0
        )

        return {
            "ongoing_recruitments": ongoing_recruitments,
            "total_candidate_ratio": total_candidate_ratio,
            "total_hired_candidates": total_hired_candidates,
            "conversion_ratio": conversion_ratio,
            "acceptance_ratio": acceptance_ratio,
            "job_data": job_data,
            "total_vacancy": total_vacancy,
            "recruitment_manager_mapping": recruitment_manager_mapping,
            "hired_ratio": hired_ratio,
            "joining": joining,
            "dep_vacancy": dep_vacancy,
            "stage_chart_count": stage_chart_count,
            "total_candidates": total_candidates,
        }

    stats = stampede_cache.get_or_compute(
        key="horilla:dashboard:recruitment:main",
        compute_fn=_compute_stats,
        timeout=300,
    )

    # Live querysets that are not serialisable — fetched fresh but cheap.
    hired_candidates = Candidate.objects.filter(
        Q(hired=True) | Q(stage_id__stage_type="hired")
    ).distinct()
    onboard_candidates = hired_candidates.filter(onboarding_stage__isnull=False)
    skill_zone = SkillZone.objects.filter(is_active=True)

    return render(
        request,
        "dashboard/dashboard.html",
        {
            **stats,
            "onboard_candidates": onboard_candidates,
            "onboarding_count": onboard_candidates.count(),
            "skill_zone": skill_zone,
        },
    )


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def dashboard_pipeline(request):
    """
    This method is used generate recruitment dataset for the dashboard
    """
    recruitment_obj = Recruitment.objects.filter(closed=False)
    data_set = []
    labels = [type[1] for type in Stage.stage_types]
    for rec in recruitment_obj:
        data = [stage_type_candidate_count(rec, type[0]) for type in Stage.stage_types]
        if rec.candidate.all():
            data_set.append(
                {
                    "label": (
                        rec.title
                        if rec.title is not None
                        else f"""{rec.job_position_id}
                    {rec.start_date}"""
                    ),
                    "data": data,
                }
            )
    return JsonResponse(
        {
            "dataSet": data_set,
            "labels": labels,
            "message": _("No records available at the moment."),
        }
    )


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def dashboard_hiring(request):
    """
    This method is used generate employee joining status for the dashboard
    """

    selected_year = request.GET.get("id")

    employee_info = EmployeeWorkInformation.objects.filter(
        date_joining__year=selected_year
    )

    # Create a list to store the count of employees for each month
    employee_count_per_month = [0] * 12  # Initialize with zeros for all months

    # Count the number of employees who joined in each month for the selected year
    for info in employee_info:
        if isinstance(info.date_joining, datetime.date):
            month_index = info.date_joining.month - 1  # Month index is zero-based
            employee_count_per_month[
                month_index
            ] += 1  # Increment the count for the corresponding month

    labels = [
        _("January"),
        _("February"),
        _("March"),
        _("April"),
        _("May"),
        _("June"),
        _("July"),
        _("August"),
        _("September"),
        _("October"),
        _("November"),
        _("December"),
    ]

    data_set = [
        {
            "label": _("Employees joined in %(year)s") % {"year": selected_year},
            "data": employee_count_per_month,
            "backgroundColor": "rgba(236, 131, 25)",
        }
    ]

    return JsonResponse({"dataSet": data_set, "labels": labels})


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def dashboard_vacancy(_request):
    """
    This method is used to generate a recruitment vacancy chart for the dashboard
    """

    recruitment_obj = Recruitment.objects.filter(closed=False, is_event_based=False)
    department = Department.objects.all()
    label = []
    data_set = [{"label": _("Openings"), "data": []}]

    for dep in department:
        vacancies_for_department = recruitment_obj.filter(
            job_position_id__department_id=dep
        )
        for rec in vacancies_for_department:
            if rec.vacancy is not None:
                label.append(dep.department)

        vacancies = [
            int(rec.vacancy) if rec.vacancy is not None else 0
            for rec in vacancies_for_department
        ]

        data_set[0]["data"].append([sum(vacancies)])

    return JsonResponse({"dataSet": data_set, "labels": label})


def get_open_position(request):
    """
    This is an ajax method to render the open position to the recruitment

    Returns:
        obj: it returns the list of job positions
    """
    rec_id = request.GET["recId"]
    recruitment_obj = Recruitment.objects.get(id=rec_id)
    queryset = recruitment_obj.open_positions.all()
    job_info = serializers.serialize("json", queryset)
    rec_info = serializers.serialize("json", [recruitment_obj])
    return JsonResponse({"openPositions": job_info, "recruitmentInfo": rec_info})


@login_required
@manager_can_enter(perm="recruitment.view_recruitment")
def candidate_status(_request):
    """
    This method is used to generate a CAndidate status chart for the dashboard
    """

    not_sent_candidates = Candidate.objects.filter(
        offer_letter_status="not_sent"
    ).count()
    sent_candidates = Candidate.objects.filter(offer_letter_status="sent").count()
    accepted_candidates = Candidate.objects.filter(
        offer_letter_status="accepted"
    ).count()
    rejected_candidates = Candidate.objects.filter(
        offer_letter_status="rejected"
    ).count()
    joined_candidates = Candidate.objects.filter(offer_letter_status="joined").count()

    data_set = []
    labels = ["Not Sent", "Sent", "Accepted", "Rejected", "Joined"]
    data = [
        not_sent_candidates,
        sent_candidates,
        accepted_candidates,
        rejected_candidates,
        joined_candidates,
    ]

    for i in range(len(data)):

        data_set.append({"label": labels[i], "data": data[i]})

    # for i in range(len(data)):
    #     if data[i] != 0:
    #         data_set.append({
    #             "label": labels[i],
    #             "data": data[i]
    #         })

    # # Remove labels corresponding to data points with value 0
    # labels = [label for label, d in zip(labels, data) if d != 0]

    return JsonResponse({"dataSet": data_set, "labels": labels})
