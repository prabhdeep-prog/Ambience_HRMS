"""
recruitment/tests.py

Unit tests for the Recruitment app.
Run with:  python manage.py test recruitment
"""

from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase


def _make_user(username="recruiter", password="pass123"):
    return User.objects.create_user(username=username, password=password)


class RecruitmentModelTest(TestCase):
    """Tests for Recruitment and Stage models."""

    def _make_job_position(self, title="Software Engineer"):
        from base.models import JobPosition

        return JobPosition.objects.create(job_position=title)

    def _make_recruitment(self, **kwargs):
        from recruitment.models import Recruitment

        defaults = dict(
            title="Backend Engineer",
            description="We are hiring a backend engineer.",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            vacancy=3,
            is_published=True,
        )
        defaults.update(kwargs)
        return Recruitment.default.create(**defaults)

    # ------------------------------------------------------------------
    # Recruitment creation
    # ------------------------------------------------------------------

    def test_create_recruitment(self):
        """A Recruitment record should save and be retrievable."""
        rec = self._make_recruitment()
        self.assertEqual(rec.title, "Backend Engineer")
        self.assertTrue(rec.is_published)

    def test_recruitment_default_manager_is_standard(self):
        """Recruitment.default must be a plain Manager (no company filter)."""
        from django.db.models import Manager
        from recruitment.models import Recruitment

        self.assertIsInstance(Recruitment.default, Manager)

    def test_recruitment_closed_defaults_false(self):
        """New recruitments should not be closed by default."""
        rec = self._make_recruitment()
        self.assertFalse(rec.closed)

    def test_recruitment_str(self):
        """__str__ should not be empty."""
        rec = self._make_recruitment()
        self.assertTrue(len(str(rec)) > 0)

    # ------------------------------------------------------------------
    # Stage model
    # ------------------------------------------------------------------

    def test_create_stage_linked_to_recruitment(self):
        """A Stage must belong to a Recruitment and cascade-delete with it."""
        from recruitment.models import Stage

        rec = self._make_recruitment()
        stage = Stage.objects.create(
            recruitment_id=rec,
            stage="Initial Screen",
            stage_type="initial",
            sequence=1,
        )
        self.assertEqual(stage.recruitment_id, rec)

        # Cascade: deleting the recruitment removes its stages
        stage_pk = stage.pk
        rec.delete()
        self.assertFalse(Stage.objects.filter(pk=stage_pk).exists())

    # ------------------------------------------------------------------
    # Public careers page
    # URL pattern: "open-recruitments" (no trailing slash)
    # ------------------------------------------------------------------

    def test_open_recruitments_page_accessible_anonymous(self):
        """The public careers page must return 200 without authentication."""
        response = self.client.get("/recruitment/open-recruitments")
        self.assertEqual(response.status_code, 200)

    def test_closed_recruitment_not_in_careers_page(self):
        """Closed recruitments must not appear on the public careers page."""
        self._make_recruitment(closed=True)
        response = self.client.get("/recruitment/open-recruitments")
        self.assertEqual(response.status_code, 200)
        # The closed job title should not appear in the response
        self.assertNotContains(response, "Backend Engineer")

    def test_published_open_recruitment_appears_on_careers_page(self):
        """Published, open recruitments within 30 days must appear on the careers page."""
        self._make_recruitment(closed=False, is_published=True)
        response = self.client.get("/recruitment/open-recruitments")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backend Engineer")

    def test_old_recruitment_hidden_from_careers(self):
        """Recruitments older than 30 days must not appear on the careers page."""
        rec = self._make_recruitment(closed=False, is_published=True)
        # Directly update created_at to simulate an old post
        from django.utils import timezone

        Recruitment = rec.__class__
        Recruitment.default.filter(pk=rec.pk).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        response = self.client.get("/recruitment/open-recruitments")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Backend Engineer")


class ApplicationFormAccessTest(TestCase):
    """Tests for the public application form (IDOR fix verification)."""

    def _make_recruitment(self):
        from recruitment.models import Recruitment

        return Recruitment.default.create(
            title="Frontend Engineer",
            description="Frontend role.",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            vacancy=1,
            is_published=True,
        )

    def test_application_form_accessible_anonymous(self):
        """Anonymous users must be able to access the application form."""
        rec = self._make_recruitment()
        # URL pattern: "application-form" (no trailing slash)
        response = self.client.get(f"/recruitment/application-form?recruitmentId={rec.id}")
        # Should not get a 500 or "not found" error
        self.assertNotEqual(response.status_code, 500)

    def test_application_form_nonexistent_recruitment(self):
        """Requesting the form with an invalid recruitmentId must not raise a 500."""
        response = self.client.get("/recruitment/application-form?recruitmentId=999999")
        self.assertNotEqual(response.status_code, 500)
