"""T-010: API error codes and trace IDs consumed by the shared frontend messages."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from corsheaders.middleware import CorsMiddleware
from django.http import Http404, HttpResponse
from django.test import RequestFactory, override_settings
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    PermissionDenied,
    ValidationError,
)

from config.exceptions import custom_exception_handler
from config.middleware import RequestIDMiddleware

BACKEND = Path(__file__).resolve().parents[1]
CONTRACT = BACKEND.parents[1] / "docs/04-api/openapi.yaml"


def test_backend_literal_error_codes_are_declared_in_contract() -> None:
    """Catch a new view/handler code even when the ErrorSerializer enum is unchanged."""
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    declared = set(contract["components"]["schemas"]["ErrorCode"]["enum"])
    sources = [
        BACKEND / "config/exceptions.py",
        BACKEND / "config/middleware.py",
        *sorted(BACKEND.glob("*/views.py")),
    ]
    emitted: list[tuple[str, str]] = []

    def collect(value: ast.expr, source: Path) -> None:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            emitted.append((value.value, f"{source.relative_to(BACKEND)}:{value.lineno}"))

    for source in sources:
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "code" for target in node.targets
            ):
                collect(node.value, source)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value == "code":
                        collect(value, source)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "ApiError":
                    code = next((kw.value for kw in node.keywords if kw.arg == "code"), None)
                    if code is None and len(node.args) > 1:
                        code = node.args[1]
                    if code is not None:
                        collect(code, source)

    assert emitted, "No backend error codes were found; check the audited source paths."
    unknown = [(code, location) for code, location in emitted if code not in declared]
    assert not unknown, f"Backend emits codes absent from ErrorCode: {unknown}"


@pytest.mark.parametrize(
    ("exc", "status", "code"),
    [
        (ValidationError({"name": ["Required"]}), 400, "VALIDATION_ERROR"),
        (NotAuthenticated(), 403, "NOT_AUTHENTICATED"),
        (AuthenticationFailed(), 403, "NOT_AUTHENTICATED"),
        (PermissionDenied(), 403, "FORBIDDEN"),
        (NotFound(), 404, "NOT_FOUND"),
        (Http404(), 404, "NOT_FOUND"),
        (MethodNotAllowed("POST"), 405, "VALIDATION_ERROR"),
    ],
)
def test_exception_handler_returns_contract_code_and_matching_trace(
    exc: Exception, status: int, code: str
) -> None:
    response = custom_exception_handler(exc, {"request": SimpleNamespace(request_id="trace-t010")})

    assert response is not None
    assert response.status_code == status
    assert response.data["code"] == code
    assert response.data["message"]
    assert isinstance(response.data["details"], dict)
    assert response.data["request_id"] == response["X-Request-ID"] == "trace-t010"


@pytest.mark.parametrize("status", [500, 502, 503])
def test_non_json_server_error_retains_trace_header(status: int) -> None:
    """Frontend can still display a request ID when Django/proxy sends an HTML error."""
    request = RequestFactory().get("/api/auth/session/", HTTP_X_REQUEST_ID="trace-server-error")
    middleware = RequestIDMiddleware(lambda _request: HttpResponse("Server error", status=status))

    response = middleware(request)

    assert response.status_code == status
    assert response["X-Request-ID"] == "trace-server-error"


@pytest.mark.parametrize("status", [500, 502, 503])
@override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:3000"])
def test_allowed_origin_can_read_trace_header_on_server_error(status: int) -> None:
    request = RequestFactory().get(
        "/api/auth/session/",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_X_REQUEST_ID="trace-cross-origin",
    )
    middleware = RequestIDMiddleware(
        CorsMiddleware(lambda _request: HttpResponse("Server error", status=status))
    )

    response = middleware(request)

    assert response.status_code == status
    assert response["Access-Control-Allow-Origin"] == "http://localhost:3000"
    exposed = {
        header.strip().lower() for header in response["Access-Control-Expose-Headers"].split(",")
    }
    assert "x-request-id" in exposed
    assert response["X-Request-ID"] == "trace-cross-origin"
