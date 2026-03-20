"""
horilla/test_settings.py

Lightweight settings for running the test suite.

Usage:
    python manage.py test --settings=horilla.test_settings employee attendance leave recruitment

Key differences from production settings:
  - SQLite in-memory database  — fast, isolated, no external dependency
  - DEBUG = True               — better tracebacks in tests
  - Dummy email backend        — no real emails sent
  - Celery runs eagerly        — tasks execute inline, no broker needed
  - Signals from horilla_automations disabled — prevents mail-template lookup errors
  - Password hashing uses MD5  — dramatically speeds up User creation in tests
"""

from horilla.settings import *  # noqa: F401, F403

# ── Database ──────────────────────────────────────────────────────────────────
# Use a fast in-memory SQLite database so tests never touch the dev/prod DB
# and there are no leftover connections to prevent teardown.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ── Speed-ups ─────────────────────────────────────────────────────────────────
# MD5 is insecure for production but perfectly fine for test data.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ── Celery — run tasks synchronously inline ───────────────────────────────────
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ── Cache — use a simple in-process cache (no Redis needed) ──────────────────
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# ── Media files — write to a temp directory ───────────────────────────────────
import tempfile  # noqa: E402

MEDIA_ROOT = tempfile.mkdtemp()

# ── Disable automation signals to prevent HorillaMailTemplate lookup errors ───
# The automation app's post_save signals fire on every model save and try to
# look up mail templates that don't exist in the empty test database.
# We disconnect them in tests by overriding INSTALLED_APPS to exclude the app,
# or by marking signal handlers as inactive via a test flag.
HORILLA_TESTING = True  # read by signals to short-circuit in test mode

# ── Exclude facedetection to prevent auditlog reverse-relation errors ─────────
# django-auditlog fires a post_save signal on every Employee creation and tries
# to access the facedetection reverse relation before that app's migration runs
# in the in-memory SQLite database.  Excluding the app prevents its table from
# being expected while keeping all other functionality available for tests.
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != "facedetection"]  # noqa: F405

# ── Skip migrations for heavy 3rd-party apps that are not under test ──────────
# Setting a migration module to None tells Django to skip all migrations for
# that app and create the tables directly from model definitions instead.
# This avoids APScheduler wiring up live jobs during app startup.
MIGRATION_MODULES = {
    "django_apscheduler": None,
}

# ── Static files ──────────────────────────────────────────────────────────────
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY = "test-secret-key-not-for-production"  # noqa: S105
DEBUG = True
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = ["http://localhost:8000"]
