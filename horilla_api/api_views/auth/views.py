import logging

from django.contrib.auth import authenticate
from drf_yasg import openapi
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from horilla_api.docs import document_api
from horilla_api.throttles import LoginDailyRateThrottle, LoginRateThrottle

from ...api_serializers.auth.serializers import (
    GetEmployeeSerializer,
    LoginRequestSerializer,
)

logger = logging.getLogger(__name__)


class LoginAPIView(APIView):
    # Both throttles must pass for a request to proceed.
    # LoginRateThrottle  : 5 attempts / minute / IP
    # LoginDailyRateThrottle : 20 attempts / day / IP
    throttle_classes = [LoginRateThrottle, LoginDailyRateThrottle]

    @document_api(
        operation_description="Authenticate user and return JWT access token with employee info",
        request_body=LoginRequestSerializer,
        responses={
            200: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "employee": openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        properties={
                            "id": openapi.Schema(type=openapi.TYPE_INTEGER),
                            "full_name": openapi.Schema(type=openapi.TYPE_STRING),
                            "employee_profile": openapi.Schema(
                                type=openapi.TYPE_STRING,
                                description="Profile image URL",
                            ),
                        },
                    ),
                    "access": openapi.Schema(
                        type=openapi.TYPE_STRING, description="JWT access token"
                    ),
                    "face_detection": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "face_detection_image": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Face detection image URL",
                        nullable=True,
                    ),
                    "geo_fencing": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    "company_id": openapi.Schema(
                        type=openapi.TYPE_INTEGER, nullable=True
                    ),
                },
            ),
            429: openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    "detail": openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description="Too many login attempts. Try again later.",
                    )
                },
            ),
        },
        tags=["auth"],
    )
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:
            return Response(
                {"error": "Please provide Username and Password"}, status=400
            )

        user = authenticate(username=username, password=password)

        if not user:
            logger.warning(
                "Failed login attempt: username=%r IP=%s",
                username,
                request.META.get("REMOTE_ADDR"),
            )
            return Response({"error": "Invalid credentials"}, status=401)

        refresh = RefreshToken.for_user(user)
        employee = user.employee_get
        face_detection = False
        face_detection_image = None
        geo_fencing = False
        company_id = None

        try:
            face_detection = employee.get_company().face_detection.start
        except AttributeError:
            pass
        try:
            geo_fencing = employee.get_company().geo_fencing.start
        except AttributeError:
            pass
        try:
            face_detection_image = employee.face_detection.image.url
        except AttributeError:
            pass
        try:
            company_id = employee.get_company().id
        except AttributeError:
            pass

        logger.info(
            "Successful login: username=%r IP=%s",
            username,
            request.META.get("REMOTE_ADDR"),
        )

        result = {
            "employee": GetEmployeeSerializer(employee).data,
            "access": str(refresh.access_token),
            "face_detection": face_detection,
            "face_detection_image": face_detection_image,
            "geo_fencing": geo_fencing,
            "company_id": company_id,
        }
        return Response(result, status=200)
