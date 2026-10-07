"""Custom exception handler cho API LabelX theo hợp đồng Error schema."""

from __future__ import annotations

import uuid
from typing import Any

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler


class ApiError(APIException):
    """Lỗi mang sẵn mã `ErrorCode` của contract (docs/04-api/openapi.yaml)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(detail=message, code=code)
        self.status_code = status_code
        self.error_code = code


def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Exception handler dùng chung theo Error schema của LabelX."""
    response = exception_handler(exc, context)
    request = context.get("request")
    request_id = (
        getattr(request, "request_id", None)
        or getattr(getattr(request, "_request", None), "request_id", None)
        or str(uuid.uuid4())
    )

    if response is None:
        return None

    code = "VALIDATION_ERROR"
    message = "Dữ liệu không hợp lệ."
    details: dict[str, Any] = {}

    if isinstance(exc, ApiError):
        code = exc.error_code
        message = str(exc.detail)
    elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        code = "NOT_AUTHENTICATED"
        message = "Chưa đăng nhập. Vui lòng đăng nhập để tiếp tục."
        response.status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, PermissionDenied):
        code = "FORBIDDEN"
        message = (
            str(exc.detail)
            if hasattr(exc, "detail") and exc.detail
            else "Bạn không có quyền thực hiện thao tác này."
        )
        response.status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, (NotFound, Http404)):
        code = "NOT_FOUND"
        message = (
            str(exc.detail)
            if hasattr(exc, "detail") and exc.detail
            else "Tài nguyên không tồn tại."
        )
        response.status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ValidationError):
        code = "VALIDATION_ERROR"
        message = "Dữ liệu không hợp lệ."
        if isinstance(exc.detail, dict):
            details = {"fields": exc.detail}
        elif isinstance(exc.detail, list):
            details = {"errors": exc.detail}
        else:
            details = {"detail": exc.detail}
        response.status_code = status.HTTP_400_BAD_REQUEST
    elif isinstance(exc, MethodNotAllowed):
        code = "VALIDATION_ERROR"
        message = (
            str(exc.detail)
            if hasattr(exc, "detail") and exc.detail
            else "Phương thức không được hỗ trợ."
        )
        response.status_code = status.HTTP_405_METHOD_NOT_ALLOWED
    else:
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            code = "NOT_AUTHENTICATED"
            message = "Chưa đăng nhập. Vui lòng đăng nhập để tiếp tục."
            response.status_code = status.HTTP_403_FORBIDDEN
        elif response.status_code == status.HTTP_403_FORBIDDEN:
            code = "FORBIDDEN"
            message = "Bạn không có quyền thực hiện thao tác này."
        elif response.status_code == status.HTTP_404_NOT_FOUND:
            code = "NOT_FOUND"
            message = "Tài nguyên không tồn tại."
        elif response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            code = "VALIDATION_ERROR"
            message = "Phương thức không được hỗ trợ."
        elif response.status_code == status.HTTP_400_BAD_REQUEST:
            code = "VALIDATION_ERROR"
            message = "Dữ liệu không hợp lệ."
            if isinstance(response.data, dict):
                details = {"fields": response.data}
        else:
            code = "VALIDATION_ERROR"
            message = str(response.data)

    response.data = {
        "code": code,
        "message": message,
        "details": details,
        "request_id": request_id,
    }
    response["X-Request-ID"] = request_id
    return response
