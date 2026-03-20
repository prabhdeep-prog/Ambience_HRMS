"""
leave/tests.py

Unit tests for the Leave app.
Run with:  python manage.py test leave
"""

from django.contrib.auth.models import User
from django.test import TestCase


def _make_user(username="leaveuser", password="pass123"):
    return User.objects.create_user(username=username, password=password)


class LeaveTypeModelTest(TestCase):
    """Tests for LeaveType model."""

    def _make_leave_type(self, **kwargs):
        from leave.models import LeaveType

        # LeaveType only requires `name`; payment defaults to "unpaid",
        # total_days defaults to 1.  There is no `leave_type` field.
        defaults = dict(
            name="Annual Leave",
            payment="paid",
            total_days=20,
        )
        defaults.update(kwargs)
        return LeaveType.objects.create(**defaults)

    def test_create_leave_type(self):
        """LeaveType should be created with correct attributes."""
        lt = self._make_leave_type()
        self.assertEqual(lt.name, "Annual Leave")
        self.assertEqual(lt.total_days, 20)

    def test_leave_type_str(self):
        """LeaveType __str__ should not be empty."""
        lt = self._make_leave_type()
        self.assertTrue(len(str(lt)) > 0)

    def test_leave_type_is_active_default(self):
        """New leave types should be active by default."""
        lt = self._make_leave_type()
        self.assertTrue(lt.is_active)


class LeaveRequestViewTest(TestCase):
    """Tests for authentication enforcement on leave views."""

    def test_leave_request_view_requires_login(self):
        """Unauthenticated users are redirected from the leave request view."""
        # URL: path("request-view/", ...) under prefix "leave/"
        response = self.client.get("/leave/request-view/")
        self.assertIn(response.status_code, [301, 302])
        location = response.get("Location", "")
        self.assertIn("login", location.lower())

    def test_authenticated_user_not_rejected(self):
        """Authenticated user gets a valid response (200 or redirect), not 403/500."""
        _make_user()
        self.client.login(username="leaveuser", password="pass123")
        response = self.client.get("/leave/request-view/")
        self.assertNotIn(response.status_code, [403, 500])
