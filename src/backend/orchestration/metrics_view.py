"""GET /internal/metrics/: Prometheus text cho queue/shard QC Run (CR-109, BLOCKER-026)."""

from __future__ import annotations

from typing import Any

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.request import Request
from rest_framework.views import APIView

from accounts.models import SYSTEM_WIDE_ROLES, RoleAssignment
from config.exceptions import ApiError
from orchestration.metrics import render_metrics

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class PrometheusRenderer(BaseRenderer):
    media_type = "text/plain"
    format = "txt"
    charset = "utf-8"

    def render(
        self, data: Any, accepted_media_type: Any = None, renderer_context: Any = None
    ) -> bytes:
        if isinstance(data, str):
            return data.encode("utf-8")
        # Lỗi (Error JSON của contract) vẫn trả JSON.
        if renderer_context and renderer_context.get("response") is not None:
            renderer_context["response"]["Content-Type"] = "application/json"
        return bytes(JSONRenderer().render(data, "application/json", renderer_context))


class IsSystemWideOps(BasePermission):
    """Chỉ qc_admin/super_admin có RoleAssignment toàn hệ thống (dataset_id = null).

    Metric gộp mọi dataset nên vai trò gán theo dataset không đủ quyền (fail closed).
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            raise ApiError(status.HTTP_403_FORBIDDEN, "NOT_AUTHENTICATED", "Chưa đăng nhập.")
        allowed = RoleAssignment.objects.filter(
            user_id=user.pk, role__in=[r.value for r in SYSTEM_WIDE_ROLES], dataset_id__isnull=True
        ).exists()
        if not allowed:
            raise ApiError(
                status.HTTP_403_FORBIDDEN,
                "FORBIDDEN",
                "Chỉ QC Admin hoặc Super Admin toàn hệ thống được đọc metric vận hành.",
            )
        return True


class MetricsView(APIView):
    permission_classes = [IsSystemWideOps]
    renderer_classes = [PrometheusRenderer]
    object_type = "metrics"

    @extend_schema(
        operation_id="internal_metrics",
        responses={(200, "text/plain"): str},
        tags=["ops"],
    )
    def get(self, request: Request) -> HttpResponse:
        response = HttpResponse(render_metrics(), content_type=CONTENT_TYPE)
        response["Cache-Control"] = "no-store"
        return response
