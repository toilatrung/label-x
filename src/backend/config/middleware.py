"""Middleware cho cấu hình LabelX."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse


class RequestIDMiddleware:
    """Gắn X-Request-ID cho mọi request/response để phục vụ trace và log.

    Đồng thời chuẩn hóa các lỗi 404 ngoài DRF trên /api/ về Error JSON contract.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = request_id  # type: ignore[attr-defined]
        response = self.get_response(request)
        response["X-Request-ID"] = request_id

        # Chuẩn hóa lỗi 404 không qua DRF view (ví dụ route đã bị gỡ) về JSON contract
        if (
            response.status_code == 404
            and request.path.startswith("/api/")
            and not response.headers.get("Content-Type", "").startswith("application/json")
        ):
            return JsonResponse(
                {
                    "code": "NOT_FOUND",
                    "message": "Tài nguyên không tồn tại.",
                    "details": {},
                    "request_id": request_id,
                },
                status=404,
                headers={"X-Request-ID": request_id},
            )

        return response
