"""
Horilla Settings Forms - Base Classes & Mixins
Provides enterprise-grade form handling with automatic styling and validation
"""

from django import forms
from django.forms import ModelForm, Form
from django.forms.widgets import (
    TextInput, EmailInput, URLInput, NumberInput,
    Select, Textarea, CheckboxInput, RadioSelect,
    DateInput, DateTimeInput, TimeInput, FileInput
)


class SettingsFormMixin:
    """
    Mixin for forms used in settings pages.
    Automatically adds CSS classes and attributes to form fields.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_settings_styling()

    def _apply_settings_styling(self):
        """Apply consistent styling and accessibility attributes to all fields."""
        for field_name, field in self.fields.items():
            self._style_field(field, field_name)

    def _style_field(self, field, field_name):
        """Apply styling to individual field."""
        widget = field.widget

        # Add CSS classes to widget
        self._add_widget_class(widget, 'oh-form-field__input')

        # Set aria attributes for accessibility
        if not widget.attrs.get('aria-label'):
            widget.attrs['aria-label'] = field.label or field_name.replace('_', ' ').title()

        # Add aria-describedby if help_text exists
        if field.help_text:
            widget.attrs['aria-describedby'] = f'{field_name}_help'

        # Add data attributes
        widget.attrs['data-field-name'] = field_name
        if field.required:
            widget.attrs['required'] = 'required'
            widget.attrs['aria-required'] = 'true'

        # Set placeholder for text inputs
        if isinstance(widget, (TextInput, EmailInput, URLInput, NumberInput)):
            if not widget.attrs.get('placeholder'):
                widget.attrs['placeholder'] = self._get_placeholder(field, field_name)

        # Handle required field indicator
        if field.required and not field.widget.is_hidden:
            field.label = f"{field.label} <span class='oh-form-field__label-required'>*</span>"

    def _add_widget_class(self, widget, class_name):
        """Add a class to widget's existing classes."""
        existing_class = widget.attrs.get('class', '')
        widget.attrs['class'] = f"{existing_class} {class_name}".strip()

    @staticmethod
    def _get_placeholder(field, field_name):
        """Generate a sensible placeholder text."""
        if hasattr(field, 'initial') and field.initial:
            return f"e.g., {field.initial}"

        # Generate from field name
        placeholder_text = field_name.replace('_', ' ').title()

        # Add helpful hints based on field type
        if isinstance(field.widget, EmailInput):
            placeholder_text = "example@company.com"
        elif isinstance(field.widget, URLInput):
            placeholder_text = "https://example.com"
        elif isinstance(field.widget, NumberInput):
            placeholder_text = "Enter a number"

        return placeholder_text


class BaseSettingsForm(SettingsFormMixin, Form):
    """
    Base form class for all settings forms.
    Inherits from SettingsFormMixin and Django Form.

    Usage:
        class CompanySettingsForm(BaseSettingsForm):
            company_name = forms.CharField(
                label="Company Name",
                help_text="Your organization's official name"
            )
            email = forms.EmailField(
                label="Contact Email",
                help_text="Primary contact email for notifications"
            )
    """
    pass


class BaseSettingsModelForm(SettingsFormMixin, ModelForm):
    """
    Base model form class for settings forms tied to Django models.

    Usage:
        class CompanyForm(BaseSettingsModelForm):
            class Meta:
                model = Company
                fields = ['name', 'email', 'phone']
    """
    pass


# ============================================================
# Example: General Settings Forms
# ============================================================

class CompanySettingsForm(BaseSettingsForm):
    """General company-wide settings form."""

    company_name = forms.CharField(
        label="Company Name",
        max_length=255,
        help_text="The official name of your organization",
        required=True,
    )

    company_email = forms.EmailField(
        label="Company Email",
        help_text="Primary email address for system notifications",
        required=True,
    )

    company_phone = forms.CharField(
        label="Phone Number",
        max_length=20,
        required=False,
        help_text="Contact phone number (optional)",
    )

    company_website = forms.URLField(
        label="Website",
        required=False,
        help_text="Your company website URL (optional)",
    )

    currency = forms.ChoiceField(
        label="Default Currency",
        choices=[
            ('USD', 'US Dollar (USD)'),
            ('EUR', 'Euro (EUR)'),
            ('GBP', 'British Pound (GBP)'),
            ('INR', 'Indian Rupee (INR)'),
            ('JPY', 'Japanese Yen (JPY)'),
        ],
        help_text="Default currency for payroll and financial reports",
        required=True,
    )

    timezone = forms.ChoiceField(
        label="Timezone",
        choices=[
            ('UTC', 'UTC'),
            ('America/New_York', 'Eastern Time (ET)'),
            ('America/Chicago', 'Central Time (CT)'),
            ('America/Denver', 'Mountain Time (MT)'),
            ('America/Los_Angeles', 'Pacific Time (PT)'),
            ('Europe/London', 'London (GMT)'),
            ('Europe/Paris', 'Central European Time (CET)'),
            ('Asia/Kolkata', 'Indian Standard Time (IST)'),
            ('Asia/Tokyo', 'Japan Standard Time (JST)'),
        ],
        help_text="Server timezone for scheduling and reports",
        required=True,
    )

    language = forms.ChoiceField(
        label="Default Language",
        choices=[
            ('en', 'English'),
            ('es', 'Español'),
            ('fr', 'Français'),
            ('de', 'Deutsch'),
            ('hi', 'हिन्दी'),
            ('ja', '日本語'),
        ],
        help_text="Default language for the application interface",
        required=True,
    )

    max_employees = forms.IntegerField(
        label="Maximum Employees",
        min_value=1,
        help_text="Maximum number of employees your license allows",
        required=True,
    )

    enable_audit_trail = forms.BooleanField(
        label="Enable Audit Trail",
        required=False,
        help_text="Track all changes to sensitive data for compliance",
    )

    enable_two_factor_auth = forms.BooleanField(
        label="Require Two-Factor Authentication",
        required=False,
        help_text="Enforce 2FA for all admin accounts",
    )


class LocalizationSettingsForm(BaseSettingsForm):
    """Localization and regional settings."""

    date_format = forms.ChoiceField(
        label="Date Format",
        choices=[
            ('DD/MM/YYYY', 'DD/MM/YYYY'),
            ('MM/DD/YYYY', 'MM/DD/YYYY'),
            ('YYYY-MM-DD', 'YYYY-MM-DD'),
        ],
        help_text="How dates are displayed throughout the system",
        required=True,
    )

    time_format = forms.ChoiceField(
        label="Time Format",
        choices=[
            ('12', '12-hour (AM/PM)'),
            ('24', '24-hour'),
        ],
        help_text="Time display format preference",
        required=True,
    )

    first_day_of_week = forms.ChoiceField(
        label="First Day of Week",
        choices=[
            ('SUN', 'Sunday'),
            ('MON', 'Monday'),
            ('SAT', 'Saturday'),
        ],
        help_text="Starting day for calendar views",
        required=True,
    )

    number_format = forms.ChoiceField(
        label="Number Format",
        choices=[
            ('en_US', '1,000.00 (US)'),
            ('en_GB', '1,000.00 (UK)'),
            ('de_DE', '1.000,00 (EU)'),
            ('fr_FR', '1 000,00 (France)'),
        ],
        help_text="How numbers and decimals are displayed",
        required=True,
    )


class NotificationSettingsForm(BaseSettingsForm):
    """Email and notification preferences."""

    enable_email_notifications = forms.BooleanField(
        label="Enable Email Notifications",
        required=False,
        help_text="Send email alerts for important events",
    )

    notification_email = forms.EmailField(
        label="Notification Email",
        help_text="Default email for system notifications",
        required=False,
    )

    enable_daily_digest = forms.BooleanField(
        label="Enable Daily Digest",
        required=False,
        help_text="Send a daily summary of activities",
    )

    digest_time = forms.TimeField(
        label="Digest Time",
        help_text="What time to send the daily digest",
        required=False,
        widget=forms.TimeInput(attrs={'type': 'time'}),
    )

    enable_slack_notifications = forms.BooleanField(
        label="Enable Slack Notifications",
        required=False,
        help_text="Send alerts to Slack channels",
    )

    slack_webhook = forms.URLField(
        label="Slack Webhook URL",
        required=False,
        help_text="Your Slack incoming webhook URL",
    )


class SecuritySettingsForm(BaseSettingsForm):
    """Security and access control settings."""

    password_min_length = forms.IntegerField(
        label="Minimum Password Length",
        min_value=6,
        max_value=255,
        initial=8,
        help_text="Minimum number of characters required in passwords",
        required=True,
    )

    password_require_uppercase = forms.BooleanField(
        label="Require Uppercase Letters",
        required=False,
        help_text="Passwords must contain at least one uppercase letter",
    )

    password_require_numbers = forms.BooleanField(
        label="Require Numbers",
        required=False,
        help_text="Passwords must contain at least one number",
    )

    password_require_special = forms.BooleanField(
        label="Require Special Characters",
        required=False,
        help_text="Passwords must contain special characters (!@#$%^&*)",
    )

    password_expiry_days = forms.IntegerField(
        label="Password Expiry (Days)",
        min_value=0,
        help_text="Force password reset after this many days (0 = no expiry)",
        required=True,
    )

    session_timeout_minutes = forms.IntegerField(
        label="Session Timeout (Minutes)",
        min_value=5,
        help_text="Auto-logout inactive users after this duration",
        required=True,
    )

    allow_login_from_multiple_ips = forms.BooleanField(
        label="Allow Multiple IP Logins",
        required=False,
        help_text="Permit the same user to be logged in from different IPs",
    )

    ip_whitelist = forms.CharField(
        label="IP Whitelist",
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        help_text="Comma-separated list of allowed IP addresses (leave empty for all)",
    )


class TemplateContextMixin:
    """Mixin for rendering forms with proper context in templates."""

    def get_form_context(self):
        """Return context dict for template rendering."""
        return {
            'form': self,
            'form_title': getattr(self, '_title', self.__class__.__name__),
            'form_description': getattr(self, '_description', ''),
            'form_sections': self._get_form_sections(),
        }

    def _get_form_sections(self):
        """
        Group form fields into sections.
        Override this method in subclasses to customize grouping.
        """
        sections = []
        current_section = {
            'title': 'Basic Information',
            'description': '',
            'fields': list(self.fields.keys()),
        }
        sections.append(current_section)
        return sections


# ============================================================
# Utility Functions for Template Rendering
# ============================================================

def render_form_field(form, field_name, css_class='oh-form-field', show_help=True):
    """
    Render a single form field with proper structure.

    Usage in template:
        {{ field|add_form_styling:"oh-form-field" }}
    """
    field = form[field_name]
    classes = field.field.widget.attrs.get('class', '')
    field.field.widget.attrs['class'] = f"{classes} {css_class}__input".strip()

    return {
        'field': field,
        'help_text': field.help_text if show_help else '',
        'errors': field.errors,
        'has_errors': bool(field.errors),
    }


def get_form_field_attributes(form, field_name):
    """
    Get all attributes needed to render a field properly.

    Returns:
        dict: Contains field, label, help_text, errors, required, etc.
    """
    field = form[field_name]
    return {
        'field': field,
        'field_name': field_name,
        'label': field.label,
        'help_text': field.help_text,
        'errors': field.errors,
        'has_errors': bool(field.errors),
        'required': field.field.required,
        'widget_type': field.field.widget.__class__.__name__,
    }
