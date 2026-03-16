from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view

from horilla_api.permissions import SwaggerPermission
from horilla_api.schema import OrderedTagSchemaGenerator

# Create schema view for Swagger and ReDoc.
# public=False tells drf-yasg to honour the permission_classes check;
# unauthenticated browsers are redirected to the DRF login page.
schema_view = get_schema_view(
    openapi.Info(
        title="Horilla API",
        default_version="v1",
        description=(
            "API documentation for Horilla HRMS.\n\n"
            "Click **Authorize** and enter your JWT token as: `Bearer <token>`\n\n"
            "Obtain a token via `POST /api/auth/`"
        ),
        terms_of_service="https://www.horilla.com/terms/",
        contact=openapi.Contact(email="contact@horilla.com"),
        license=openapi.License(name="BSD License"),
    ),
    public=False,
    permission_classes=(SwaggerPermission,),
    generator_class=OrderedTagSchemaGenerator,
)

urlpatterns = [
    # API Documentation URLs
    path(
        "swagger<format>/", schema_view.without_ui(cache_timeout=0), name="schema-json"
    ),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="schema-redoc"),
    path("docs/", schema_view.with_ui("swagger", cache_timeout=0), name="schema-docs"),
    # API Endpoints (static configuration)
    path("auth/", include("horilla_api.api_urls.auth.urls")),
    path("asset/", include("horilla_api.api_urls.asset.urls")),
    path("base/", include("horilla_api.api_urls.base.urls")),
    path("employee/", include("horilla_api.api_urls.employee.urls")),
    path("notifications/", include("horilla_api.api_urls.notifications.urls")),
    path("payroll/", include("horilla_api.api_urls.payroll.urls")),
    path("attendance/", include("horilla_api.api_urls.attendance.urls")),
    path("leave/", include("horilla_api.api_urls.leave.urls")),
    path("helpdesk/", include("horilla_api.api_urls.helpdesk.urls")),
]
