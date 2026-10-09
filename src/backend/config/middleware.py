"""Middleware for the LabelX backend."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.contrib.auth.models import User
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse

from audit.services import append_audit_event
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


class AuditRejectionMiddleware:
    """Flushes any pending rejection audit event outside of the view's atomic block.

    When ATOMIC_REQUESTS is active, Django wraps the view inside transaction.atomic.
    If an error occurs or the view transaction rolls back, anything written inside that
    transaction is lost. This middleware runs outside the view transaction and commits
    the pending rejection audit in an independent transaction.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request._has_audit_middleware = True  # type: ignore[attr-defined]
        try:
            response = self.get_response(request)
        except Exception:
            self._flush_pending(request, status_code=500)
            raise
        self._flush_pending(request, status_code=response.status_code)
        return response

    @staticmethod
    def _flush_pending(request: HttpRequest, status_code: int) -> None:
        pending = getattr(request, "_pending_rejection_audit", None)
        if pending and status_code in (400, 403, 404, 422, 500):
            actor = pending.get("actor")
            if actor and isinstance(actor, User) and actor.is_authenticated:
                with transaction.atomic():
                    append_audit_event(
                        actor=actor,
                        action=str(pending["action"]),
                        object_type=str(pending["object_type"]),
                        object_id=str(pending["object_id"]),
                        before=pending.get("before"),
                        after=pending.get("after"),
                        revision=str(pending.get("revision") or getattr(request, "request_id", "")),
                        reason=str(pending.get("reason", "")),
                    )
            setattr(request, "_pending_rejection_audit", None)  # noqa: B010
