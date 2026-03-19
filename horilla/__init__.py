"""
init.py
"""

from horilla import (
    horilla_apps,
    horilla_context_processors,
    horilla_middlewares,
    horilla_settings,
    rest_conf,
)

# Expose the Celery app so that `celery -A horilla` picks it up and Django's
# @shared_task decorator resolves to the correct app at import time.
# Guarded so Django still boots when celery is not installed.
try:
    from horilla.celery import app as celery_app  # noqa: F401

    __all__ = ("celery_app",)
except ImportError:
    pass
