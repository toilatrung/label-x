"""API phiên đăng nhập LabelX `/api/auth/*` theo contract T-001 (E-02, T-011).

- Xác thực bằng session Django (cookie `sessionid`); request ghi phải có header `X-CSRFToken`
  khớp cookie `csrftoken`. CSRF được kiểm cả khi chưa đăng nhập (login, logout), vì
  `SessionAuthentication` của DRF chỉ kiểm cho người đã đăng nhập.
- Lỗi theo `Error` của contract: thiếu/sai CSRF 403 FORBIDDEN, sai thông tin đăng nhập
  400 INVALID_CREDENTIALS, chưa đăng nhập hoặc phiên hết hạn 403 NOT_AUTHENTICATED.
"""

from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.authentication import CSRFCheck
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from accounts.permissions import HasRoleAndDatasetScope
from accounts.serializers import (
    LoginRequestSerializer,
    SessionSerializer,
    WorkflowPermissionsSerializer,
    build_session,
)
from config.exceptions import ApiError
from config.serializers import ErrorSerializer

CSRF_FAILED_MESSAGE = "Yêu cầu thiếu hoặc sai mã bảo vệ. Vui lòng tải lại trang và thử lại."


def enforce_csrf(request: Request) -> None:
    """Kiểm CSRF như CsrfViewMiddleware, kể cả với người chưa đăng nhập."""

    def _no_response(_request: object) -> None:  # pragma: no cover - không bao giờ được gọi
        return None

    check = CSRFCheck(_no_response)  # type: ignore[arg-type]
    check.process_request(request._request)
    reason = check.process_view(request._request, None, (), {})  # type: ignore[arg-type]
    if reason:
        raise ApiError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", CSRF_FAILED_MESSAGE)


def _error(description: str) -> OpenApiResponse:
    return OpenApiResponse(response=ErrorSerializer, description=description)


class CsrfView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="auth_csrf",
        tags=["auth"],
        summary="Đặt cookie csrftoken",
        auth=[],
        responses={204: OpenApiResponse(description="Đã đặt cookie csrftoken")},
    )
    def get(self, request: Request) -> Response:
        get_token(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="auth_login",
        tags=["auth"],
        summary="Đăng nhập, tạo session",
        auth=[],
        request=LoginRequestSerializer,
        responses={
            200: SessionSerializer,
            400: _error("Dữ liệu không hợp lệ (VALIDATION_ERROR, INVALID_CREDENTIALS)"),
            403: _error("Thiếu hoặc sai CSRF (FORBIDDEN)"),
        },
    )
    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request._request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            # Sai mật khẩu, không có tài khoản hoặc tài khoản bị khoá: cùng một thông báo.
            raise ApiError(
                status.HTTP_400_BAD_REQUEST,
                "INVALID_CREDENTIALS",
                "Tên đăng nhập hoặc mật khẩu không chính xác.",
            )
        login(request._request, user)
        return Response(build_session(user), headers={"Cache-Control": "no-store"})


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="auth_logout",
        tags=["auth"],
        summary="Đăng xuất, huỷ session",
        request=None,
        responses={
            204: OpenApiResponse(
                description="Đã đăng xuất (gọi lại khi đã đăng xuất cũng trả 204)"
            ),
            403: _error("Thiếu hoặc sai CSRF (FORBIDDEN)"),
        },
    )
    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="auth_session",
        tags=["auth"],
        summary="Người dùng, vai trò theo scope, identity mapping",
        responses={
            200: SessionSerializer,
            403: _error("Chưa đăng nhập hoặc phiên hết hạn (NOT_AUTHENTICATED)"),
        },
    )
    def get(self, request: Request) -> Response:
        return Response(build_session(request.user), headers={"Cache-Control": "no-store"})


ROLE_MATRIX = [
    {
        "function": "Datasets",
        "roles": {
            "annotator": "view_assigned",
            "reviewer": "view_assigned",
            "qa_lead": "view_assigned",
            "qc_admin": "view_all",
            "super_admin": "view_all",
            "product_owner": "view_assigned",
            "data_model_owner": "view_assigned",
        },
    },
    {
        "function": "Quality Analysis",
        "roles": {
            "annotator": "none",
            "reviewer": "none",
            "qa_lead": "run_view",
            "qc_admin": "configure",
            "super_admin": "run_configure",
            "product_owner": "view_kpi",
            "data_model_owner": "none",
        },
    },
    {
        "function": "Review Queues & Workspace",
        "roles": {
            "annotator": "none",
            "reviewer": "review",
            "qa_lead": "review_monitor",
            "qc_admin": "view",
            "super_admin": "review_monitor",
            "product_owner": "none",
            "data_model_owner": "none",
        },
    },
    {
        "function": "Rework",
        "roles": {
            "annotator": "execute",
            "reviewer": "request_verify",
            "qa_lead": "request_monitor",
            "qc_admin": "none",
            "super_admin": "execute_verify",
            "product_owner": "none",
            "data_model_owner": "none",
        },
    },
    {
        "function": "Adjudication",
        "roles": {
            "annotator": "none",
            "reviewer": "none",
            "qa_lead": "yes",
            "qc_admin": "none",
            "super_admin": "override_with_reason",
            "product_owner": "none",
            "data_model_owner": "none",
        },
    },
    {
        "function": "Calibration & Audit",
        "roles": {
            "annotator": "participate",
            "reviewer": "participate",
            "qa_lead": "manage",
            "qc_admin": "configure",
            "super_admin": "manage_configure",
            "product_owner": "none",
            "data_model_owner": "none",
        },
    },
    {
        "function": "Phê duyệt phát hành",
        "roles": {
            "annotator": "none",
            "reviewer": "none",
            "qa_lead": "authorized",
            "qc_admin": "none",
            "super_admin": "override_with_reason",
            "product_owner": "none",
            "data_model_owner": "none",
        },
    },
    {
        "function": "Configuration",
        "roles": {
            "annotator": "none",
            "reviewer": "none",
            "qa_lead": "limited",
            "qc_admin": "yes",
            "super_admin": "full_including_permissions",
            "product_owner": "none",
            "data_model_owner": "lock_detector_artifact",
        },
    },
]

WORKFLOW_RULES = [
    {
        "rule": "anti_self_review",
        "name": "Reviewer không review annotation của chính mình",
        "description": "Backend từ chối khi trùng người (kể cả Super Admin ghi đè)",
        "enforced": True,
    },
    {
        "rule": "super_admin_override_reason",
        "name": "Ghi đè của Super Admin phải có lý do",
        "description": (
            "Áp dụng cho quyết định, phân xử, waiver, phê duyệt phát hành, duyệt guideline"
        ),
        "enforced": True,
    },
    {
        "rule": "audit_logging",
        "name": "Mọi thao tác ghi nhật ký kiểm toán",
        "description": "Gắn nhãn Super Admin khi dùng quyền ghi đè; ghi sự kiện từ chối",
        "enforced": True,
    },
    {
        "rule": "separation_of_duties",
        "name": "Người duyệt khác người yêu cầu",
        "description": "Nguyên tắc bốn mắt, từ chối khi trùng người yêu cầu và phê duyệt",
        "enforced": True,
    },
]


class WorkflowPermissionsView(APIView):
    permission_classes = [IsAuthenticated, HasRoleAndDatasetScope]
    allowed_roles = (Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN)
    action_name = "auth_workflow_permissions"
    requires_dataset = False
    scope_type = "system"

    @extend_schema(
        operation_id="auth_workflow_permissions",
        tags=["auth"],
        summary="Ma trận phân quyền và quy tắc quy trình cho màn WorkflowPermissions",
        responses={
            200: WorkflowPermissionsSerializer,
            403: _error("Chưa đăng nhập hoặc không đủ quyền (FORBIDDEN, NOT_AUTHENTICATED)"),
        },
    )
    def get(self, request: Request) -> Response:
        session = build_session(request.user)
        return Response(
            {
                "matrix": ROLE_MATRIX,
                "rules": WORKFLOW_RULES,
                "user_roles": session["roles"],
            },
            headers={"Cache-Control": "no-store"},
        )
