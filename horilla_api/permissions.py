"""
horilla_api/permissions.py

Custom permission classes for the Horilla API.
"""

from django.conf import settings
from rest_framework.permissions import BasePermission


class SwaggerPermission(BasePermission):
    """
    Controls access to the Swagger / ReDoc documentation endpoints.

    Rules:
      - DEBUG=True  (development) : any authenticated user may view the docs.
      - DEBUG=False (production)  : only authenticated staff / superusers.

    Unauthenticated requests are always denied.  drf-yasg will redirect the
    browser to the DRF login page so developers can sign in and then return.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if settings.DEBUG:
            # Development: any logged-in user can explore the API.
            return True

        # Production: restrict to staff / admin accounts only.
        return bool(request.user.is_staff or request.user.is_superuser)
