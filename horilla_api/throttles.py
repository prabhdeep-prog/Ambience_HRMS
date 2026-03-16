"""
horilla_api/throttles.py

Custom throttle classes for the Horilla API login endpoint.

Two throttles work together on LoginAPIView:
  - LoginRateThrottle     — 5 attempts per minute per IP  (burst protection)
  - LoginDailyRateThrottle — 20 attempts per day per IP   (sustained protection)

Both key on the client IP address (not on a user account, because the user
is not yet authenticated at the login endpoint).

Cache backend:
  Django's default cache is used.  For a single-process dev server the
  in-memory cache is fine.  For multi-process / multi-instance production
  deployments configure a shared cache (Redis) in settings.CACHES so that
  counters are shared across all processes:

      CACHES = {
          "default": {
              "BACKEND": "django_redis.cache.RedisCache",
              "LOCATION": env("REDIS_URL"),
          }
      }
"""

import logging

from rest_framework.throttling import SimpleRateThrottle

logger = logging.getLogger(__name__)


class LoginRateThrottle(SimpleRateThrottle):
    """
    Allows 5 login attempts per minute per IP address.

    Keyed on: client IP
    Scope   : "login"  →  DEFAULT_THROTTLE_RATES["login"] = "5/minute"
    """

    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }

    def throttle_failure(self):
        logger.warning(
            "Login throttled (per-minute limit): IP=%s wait=%.0fs",
            self.get_ident(self.request),
            self.wait(),
        )
        return False


class LoginDailyRateThrottle(SimpleRateThrottle):
    """
    Caps login attempts at 20 per day per IP address.

    Keyed on: client IP
    Scope   : "login_day"  →  DEFAULT_THROTTLE_RATES["login_day"] = "20/day"
    """

    scope = "login_day"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }

    def throttle_failure(self):
        logger.warning(
            "Login throttled (daily limit): IP=%s wait=%.0fs",
            self.get_ident(self.request),
            self.wait(),
        )
        return False
