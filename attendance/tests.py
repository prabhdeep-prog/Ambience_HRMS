"""
attendance/tests.py

Unit tests for the Attendance app.
Run with:  python manage.py test attendance
"""

from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_user(username="testuser", password="pass123"):
    return User.objects.create_user(username=username, password=password)


def _make_employee(user, first="Test", last="User"):
    from employee.models import Employee

    return Employee.objects.create(
        employee_first_name=first,
        employee_last_name=last,
        employee_user_id=user,
        email=f"{user.username}@example.com",
        phone="1234567890",
        gender="male",
    )


def _seed_shift_days():
    """
    Create the seven EmployeeShiftDay rows that Attendance.save() requires.

    The Attendance model resolves the weekday name of attendance_date to an
    EmployeeShiftDay FK.  These rows are normally loaded via a fixture in
    production; in the in-memory test database they must be created manually.
    """
    from base.models import EmployeeShiftDay

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for day in days:
        EmployeeShiftDay.objects.get_or_create(day=day)


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------

class AttendanceModelTest(TestCase):
    """Tests for the Attendance model."""

    @classmethod
    def setUpTestData(cls):
        """Seed shared data once for the whole test class."""
        _seed_shift_days()
        cls.user = _make_user()
        cls.employee = _make_employee(cls.user)

    def _make_attendance(self, **kwargs):
        from attendance.models import Attendance

        defaults = dict(
            employee_id=self.employee,
            attendance_date=date.today(),
            attendance_clock_in=time(9, 0),
            attendance_clock_in_date=date.today(),
            attendance_worked_hour="08:00",
            minimum_hour="08:00",
        )
        defaults.update(kwargs)
        return Attendance.objects.create(**defaults)

    # ------------------------------------------------------------------
    # Basic creation
    # ------------------------------------------------------------------

    def test_create_attendance_record(self):
        """Attendance record should be created with correct employee link."""
        att = self._make_attendance()
        self.assertEqual(att.employee_id, self.employee)
        self.assertEqual(att.attendance_date, date.today())

    def test_attendance_validated_defaults_false(self):
        """New attendance records should not be validated by default."""
        att = self._make_attendance()
        self.assertFalse(att.attendance_validated)

    # ------------------------------------------------------------------
    # Unique constraint (employee + date)
    # ------------------------------------------------------------------

    def test_duplicate_attendance_raises_integrity_error(self):
        """Two attendance records for the same employee on the same date must fail."""
        self._make_attendance()
        with self.assertRaises(IntegrityError):
            self._make_attendance()  # same employee, same date

    def test_different_dates_allowed(self):
        """Attendance records for the same employee on different dates are fine."""
        self._make_attendance(attendance_date=date.today())
        yesterday = date.today() - timedelta(days=1)
        att2 = self._make_attendance(
            attendance_date=yesterday,
            attendance_clock_in_date=yesterday,
        )
        self.assertIsNotNone(att2.pk)


class CanAccessAttendanceTest(TestCase):
    """Tests for the can_access_attendance() permission helper."""

    @classmethod
    def setUpTestData(cls):
        _seed_shift_days()

        # Owner of the attendance record
        cls.owner_user = _make_user("owner", "pass123")
        cls.owner_emp = _make_employee(cls.owner_user, "Owner", "Employee")

        # Unrelated employee
        cls.other_user = _make_user("other", "pass123")
        cls.other_emp = _make_employee(cls.other_user, "Other", "Employee")

    def setUp(self):
        # Reload users from DB each test so permission caches are fresh
        self.owner_user = User.objects.get(pk=self.owner_user.pk)
        self.other_user = User.objects.get(pk=self.other_user.pk)

    def _make_attendance_for(self, employee):
        from attendance.models import Attendance

        return Attendance.objects.create(
            employee_id=employee,
            attendance_date=date.today(),
            attendance_clock_in=time(9, 0),
            attendance_clock_in_date=date.today(),
            attendance_worked_hour="08:00",
            minimum_hour="08:00",
        )

    def _make_request(self, user):
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get("/")
        request.user = user
        return request

    def test_owner_can_access_own_attendance(self):
        """Employee can always access their own attendance record."""
        from attendance.methods.utils import can_access_attendance

        att = self._make_attendance_for(self.owner_emp)
        request = self._make_request(self.owner_user)
        self.assertTrue(can_access_attendance(request, att))

    def test_unrelated_user_denied(self):
        """An employee without permissions cannot access another's attendance."""
        from attendance.methods.utils import can_access_attendance

        att = self._make_attendance_for(self.owner_emp)
        request = self._make_request(self.other_user)
        self.assertFalse(can_access_attendance(request, att))

    def test_user_with_change_permission_can_access(self):
        """A user with attendance.change_attendance permission can access any record."""
        from attendance.methods.utils import can_access_attendance
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType
        from attendance.models import Attendance

        ct = ContentType.objects.get_for_model(Attendance)
        perm = Permission.objects.get(content_type=ct, codename="change_attendance")
        self.other_user.user_permissions.add(perm)
        # Refresh user from DB so permissions are loaded
        self.other_user = User.objects.get(pk=self.other_user.pk)

        att = self._make_attendance_for(self.owner_emp)
        request = self._make_request(self.other_user)
        self.assertTrue(can_access_attendance(request, att))


class AttendanceViewTest(TestCase):
    """Tests for authentication enforcement on attendance views."""

    def test_attendance_view_requires_login(self):
        """Unauthenticated users must be redirected from the attendance view."""
        response = self.client.get("/attendance/attendance-view/")
        self.assertIn(response.status_code, [301, 302])
        location = response.get("Location", "")
        self.assertIn("login", location.lower())
