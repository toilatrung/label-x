"""Middleware for the LabelX backend."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

from config.logging import log_context

request_logger = logging.getLogger("labelx.request")


class RequestIDMiddleware:
    """Attach X-Request-ID, normalize API 404 responses, and log each request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = request_id  # type: ignore[attr-defined]
        started_at = time.perf_counter()

        with log_context(request_id=request_id, run_id=None, snapshot_id=None):
            try:
                response = self.get_response(request)

                if (
                    response.status_code == 404
                    and request.path.startswith("/api/")
                    and not response.headers.get("Content-Type", "").startswith("application/json")
                ):
                    response = JsonResponse(
                        {
                            "code": "NOT_FOUND",
                            "message": "Tài nguyên không tồn tại.",
                            "details": {},
                            "request_id": request_id,
                        },
                        status=404,
                    )

                response["X-Request-ID"] = request_id
                status_code = response.status_code
                level = (
                    logging.ERROR
                    if status_code >= 500
                    else logging.WARNING
                    if status_code >= 400
                    else logging.INFO
                )
                request_logger.log(
                    level,
                    "request.completed",
                    extra={
                        "event": "request.completed",
                        "http_method": request.method,
                        "http_path": request.path,
                        "http_status_code": status_code,
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    },
                )
                return response
            except Exception:
                request_logger.exception(
                    "request.failed",
                    extra={
                        "event": "request.failed",
                        "http_method": request.method,
                        "http_path": request.path,
                        "http_status_code": 500,
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 3),
                    },
                )
                raise
