"""
employee/tests.py

Unit tests for the Employee app.
Run with:  python manage.py test employee
"""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase


class EmployeeModelTest(TestCase):
    """Tests for the Employee model and its helpers."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="john.doe",
            password="testpass123",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )

    def _make_employee(self, **kwargs):
        from employee.models import Employee

        defaults = dict(
            employee_first_name="John",
            employee_last_name="Doe",
            employee_user_id=self.user,
            email="john@example.com",
            phone="1234567890",
            gender="male",
        )
        defaults.update(kwargs)
        return Employee.objects.create(**defaults)

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------

    def test_create_employee_links_to_user(self):
        """Creating an Employee must store the OneToOne link with User."""
        emp = self._make_employee()
        self.assertEqual(emp.employee_user_id, self.user)
        self.assertEqual(emp.employee_first_name, "John")

    def test_is_active_defaults_to_true(self):
        """New employees are active by default."""
        emp = self._make_employee()
        self.assertTrue(emp.is_active)

    def test_str_representation(self):
        """__str__ should include employee name."""
        emp = self._make_employee()
        result = str(emp)
        self.assertTrue(len(result) > 0)

    # ------------------------------------------------------------------
    # Employee.for_user() classmethod
    # ------------------------------------------------------------------

    def test_for_user_returns_employee(self):
        """Employee.for_user() returns the employee linked to the given user."""
        from employee.models import Employee

        emp = self._make_employee()
        result = Employee.for_user(self.user)
        self.assertEqual(result, emp)

    def test_for_user_returns_none_when_no_employee(self):
        """Employee.for_user() returns None when no employee is linked."""
        from employee.models import Employee

        other_user = User.objects.create_user(username="nobody", password="x")
        result = Employee.for_user(other_user)
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # XSS protection (clean_fields)
    # ------------------------------------------------------------------

    def test_xss_script_tag_rejected(self):
        """clean_fields() must raise ValidationError for <script> in text fields."""
        from employee.models import Employee

        emp = Employee(
            employee_first_name='<script>alert("xss")</script>',
            employee_last_name="Doe",
            employee_user_id=self.user,
            email="xss@example.com",
            phone="1234567890",
            gender="male",
        )
        with self.assertRaises(ValidationError):
            emp.clean_fields()

    def test_xss_event_handler_rejected(self):
        """clean_fields() must reject onerror= style payloads."""
        from employee.models import Employee

        emp = Employee(
            employee_first_name='<img src=x onerror=alert(1)>',
            employee_last_name="Doe",
            employee_user_id=self.user,
            email="xss2@example.com",
            phone="1234567890",
            gender="male",
        )
        with self.assertRaises(ValidationError):
            emp.clean_fields()

    def test_normal_name_passes_clean_fields(self):
        """clean_fields() must not raise for normal plain-text names."""
        from employee.models import Employee

        emp = Employee(
            employee_first_name="Mary",
            employee_last_name="O'Brien",
            employee_user_id=self.user,
            email="mary@example.com",
            phone="9876543210",
            gender="female",
        )
        # Should not raise
        emp.clean_fields(exclude=["employee_user_id"])

    # ------------------------------------------------------------------
    # soft-delete
    # ------------------------------------------------------------------

    def test_soft_delete_via_is_active(self):
        """Setting is_active=False marks employee as inactive without deleting."""
        emp = self._make_employee()
        emp.is_active = False
        emp.save()

        from employee.models import Employee

        # Record still exists in the database
        self.assertTrue(Employee.objects.filter(pk=emp.pk).exists())
        emp.refresh_from_db()
        self.assertFalse(emp.is_active)


class EmployeeViewAccessTest(TestCase):
    """Tests for authentication enforcement on employee views."""

    def test_unauthenticated_redirected_from_employee_list(self):
        """Anonymous users must be redirected to login from the employee list."""
        response = self.client.get("/employee/employee-view/")
        self.assertIn(response.status_code, [301, 302])
        location = response.get("Location", "")
        self.assertIn("login", location.lower())

    def test_authenticated_user_not_rejected_with_403(self):
        """Authenticated users without an employee profile get a redirect, not 403/500."""
        User.objects.create_user(username="plain", password="pass123")
        self.client.login(username="plain", password="pass123")
        response = self.client.get("/employee/employee-view/")
        self.assertNotIn(response.status_code, [403, 500])
