from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from recruitment.models import (
    CandidateDocument,
    CandidateDocumentRequest,
    Recruitment,
    Stage,
)


DEFAULT_STAGES = [
    {"stage": "Applied", "stage_type": "applied", "sequence": 0},
    {"stage": "Screening", "stage_type": "initial", "sequence": 1},
    {"stage": "Interview", "stage_type": "interview", "sequence": 2},
    {"stage": "Offer", "stage_type": "test", "sequence": 3},
    {"stage": "Hired", "stage_type": "hired", "sequence": 4},
    {"stage": "Rejected", "stage_type": "cancelled", "sequence": 5},
]


@receiver(post_save, sender=Recruitment)
def create_initial_stage(sender, instance, created, **kwargs):
    """
    Post-save signal: automatically creates the default pipeline stages
    whenever a new Recruitment record is created.
    """
    if created:
        for stage_data in DEFAULT_STAGES:
            Stage.objects.create(
                recruitment_id=instance,
                stage=stage_data["stage"],
                stage_type=stage_data["stage_type"],
                sequence=stage_data["sequence"],
            )


@receiver(m2m_changed, sender=CandidateDocumentRequest.candidate_id.through)
def document_request_m2m_changed(sender, instance, action, **kwargs):
    if action == "post_add":
        candidate_document_create(instance)

    elif action == "post_remove":
        candidate_document_create(instance)


def candidate_document_create(instance):
    candidates = instance.candidate_id.all()
    for candidate in candidates:
        document, created = CandidateDocument.objects.get_or_create(
            candidate_id=candidate,
            document_request_id=instance,
            defaults={"title": f"Upload {instance.title}"},
        )
        document.title = f"Upload {instance.title}"
        document.save()
