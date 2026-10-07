"""Tests cho API phiên đăng nhập `/api/auth/*` (T-011, E-02).

Đối chiếu contract docs/04-api/openapi.yaml: schema drf-spectacular khớp contract, mọi mã lỗi
thuộc ErrorCode; các trường hợp từ chối (thiếu/sai CSRF, sai mật khẩu, phiên hết hạn,
chưa đăng nhập) và người không có vai trò/identity mapping.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session as DjangoSession
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIClient

from accounts.models import CvatIdentity, RoleAssignment

CONTRACT = yaml.safe_load(
    (Path(__file__).resolve().parents[4] / "docs/04-api/openapi.yaml").read_text(encoding="utf-8")
)
ERROR_CODES = set(CONTRACT["components"]["schemas"]["ErrorCode"]["enum"])
PASSWORD = "Mat-khau-dai-123"

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def reviewer() -> User:
    user = User.objects.create_user(
        "reviewer1", password=PASSWORD, first_name="Rà", last_name="Soát"
    )
    RoleAssignment.objects.create(user=user, role="reviewer", dataset_id=7)
    CvatIdentity.objects.create(user=user, cvat_user_id=42, cvat_username="rv1")
    return user


def csrf(client: APIClient) -> str:
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 204
    return str(client.cookies["csrftoken"].value)


def login(
    client: APIClient, username: str, password: str = PASSWORD, token: str | None = None
) -> Any:
    headers = {"HTTP_X_CSRFTOKEN": token} if token is not None else {}
    return client.post(
        "/api/auth/login/", {"username": username, "password": password}, format="json", **headers
    )


def assert_error(response: Response, status: int, code: str) -> None:
    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert body["code"] in ERROR_CODES
    assert body["message"]
    assert body["request_id"] == response["X-Request-ID"]


# ---------------------------------------------------------------------------- thành công


def test_csrf_sets_cookie(client: APIClient) -> None:
    assert csrf(client)


def test_login_returns_session_and_session_endpoint_matches(
    client: APIClient, reviewer: User
) -> None:
    response = login(client, "reviewer1", token=csrf(client))
    assert response.status_code == 200
    expected = {
        "user": {"id": reviewer.pk, "username": "reviewer1", "display_name": "Rà Soát"},
        "roles": [{"role": "reviewer", "dataset_id": 7}],
        "identity_mapping": {"status": "mapped", "cvat_user_id": 42},
    }
    assert response.json() == expected
    assert client.cookies["sessionid"]["httponly"]
    session = client.get("/api/auth/session/")
    assert session.status_code == 200
    assert session.json() == expected


def test_user_without_role_or_mapping_has_no_grant(client: APIClient) -> None:
    User.objects.create_user("norole", password=PASSWORD)
    response = login(client, "norole", token=csrf(client))
    assert response.status_code == 200
    body = response.json()
    assert body["roles"] == []
    assert body["identity_mapping"] == {"status": "missing", "cvat_user_id": None}
    assert body["user"]["display_name"] == "norole"


def test_logout_ends_session_and_is_idempotent(client: APIClient, reviewer: User) -> None:
    token = csrf(client)
    assert login(client, "reviewer1", token=token).status_code == 200
    token = str(client.cookies["csrftoken"].value)  # login xoay csrftoken
    assert client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code == 204
    assert_error(client.get("/api/auth/session/"), 403, "NOT_AUTHENTICATED")
    assert client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=token).status_code == 204


# ---------------------------------------------------------------------------- từ chối


def test_login_without_csrf_is_forbidden(client: APIClient, reviewer: User) -> None:
    assert_error(login(client, "reviewer1"), 403, "FORBIDDEN")


def test_login_with_wrong_csrf_is_forbidden(client: APIClient, reviewer: User) -> None:
    csrf(client)
    assert_error(login(client, "reviewer1", token="x" * 32), 403, "FORBIDDEN")


def test_login_with_untrusted_origin_is_forbidden(
    client: APIClient, reviewer: User, settings: Any
) -> None:
    settings.CSRF_TRUSTED_ORIGINS = ["http://localhost:3000"]
    token = csrf(client)
    response = client.post(
        "/api/auth/login/",
        {"username": "reviewer1", "password": PASSWORD},
        format="json",
        HTTP_X_CSRFTOKEN=token,
        HTTP_ORIGIN="http://evil.example",
    )
    assert_error(response, 403, "FORBIDDEN")


def test_login_wrong_password(client: APIClient, reviewer: User) -> None:
    response = login(client, "reviewer1", password="sai", token=csrf(client))
    assert_error(response, 400, "INVALID_CREDENTIALS")
    assert "sessionid" not in client.cookies


def test_login_unknown_user_and_inactive_user_same_error(client: APIClient, reviewer: User) -> None:
    token = csrf(client)
    unknown = login(client, "khong-co", token=token)
    reviewer.is_active = False
    reviewer.save()
    inactive = login(client, "reviewer1", token=token)
    for response in (unknown, inactive):
        assert_error(response, 400, "INVALID_CREDENTIALS")
    assert unknown.json()["message"] == inactive.json()["message"]


def test_login_missing_fields(client: APIClient) -> None:
    token = csrf(client)
    response = client.post(
        "/api/auth/login/", {"username": ""}, format="json", HTTP_X_CSRFTOKEN=token
    )
    assert_error(response, 400, "VALIDATION_ERROR")
    assert set(response.json()["details"]["fields"]) == {"username", "password"}


def test_session_without_login(client: APIClient) -> None:
    assert_error(client.get("/api/auth/session/"), 403, "NOT_AUTHENTICATED")


def test_expired_session_is_not_authenticated(client: APIClient, reviewer: User) -> None:
    assert login(client, "reviewer1", token=csrf(client)).status_code == 200
    key = client.cookies["sessionid"].value
    DjangoSession.objects.filter(session_key=key).update(
        expire_date=timezone.now() - timedelta(seconds=1)
    )
    assert_error(client.get("/api/auth/session/"), 403, "NOT_AUTHENTICATED")


def test_logout_without_csrf_when_logged_in_is_forbidden(client: APIClient, reviewer: User) -> None:
    assert login(client, "reviewer1", token=csrf(client)).status_code == 200
    assert_error(client.post("/api/auth/logout/"), 403, "FORBIDDEN")
    assert client.get("/api/auth/session/").status_code == 200


def test_session_cookie_settings(settings: Any) -> None:
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.CSRF_COOKIE_HTTPONLY is False
    assert settings.SESSION_COOKIE_AGE == 8 * 60 * 60


# ---------------------------------------------------------------------------- contract


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = components[schema["$ref"].rsplit("/", 1)[-1]]
    return schema


def _shape(schema: dict[str, Any], components: dict[str, Any]) -> Any:
    """Rút gọn schema thành cấu trúc (kiểu, trường bắt buộc, enum, nullable) để so hai nguồn."""
    schema = _resolve(schema, components)
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return _shape(
            {**schema["allOf"][0], **{k: v for k, v in schema.items() if k != "allOf"}}, components
        )
    if schema.get("type") == "array":
        return ["array", _shape(schema["items"], components)]
    if schema.get("type") == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {
            "required": sorted(schema.get("required", [])),
            "properties": {
                k: _shape(v, components) for k, v in sorted(props.items()) if not v.get("writeOnly")
            },
        }
    return {
        "type": schema.get("type"),
        "enum": sorted(schema["enum"]) if "enum" in schema else None,
        "nullable": bool(schema.get("nullable")),
    }


AUTH_OPERATIONS = {
    ("/api/auth/csrf/", "get"): "auth_csrf",
    ("/api/auth/login/", "post"): "auth_login",
    ("/api/auth/logout/", "post"): "auth_logout",
    ("/api/auth/session/", "get"): "auth_session",
}


@pytest.mark.parametrize(("path", "method"), list(AUTH_OPERATIONS))
def test_auth_schema_matches_contract(path: str, method: str) -> None:
    from drf_spectacular.generators import SchemaGenerator

    generated = SchemaGenerator().get_schema(request=None, public=True)
    ours, theirs = generated["paths"][path][method], CONTRACT["paths"][path][method]
    assert ours["operationId"] == theirs["operationId"] == AUTH_OPERATIONS[(path, method)]
    assert set(ours["responses"]) == set(theirs["responses"])
    gen_c, con_c = generated["components"]["schemas"], CONTRACT["components"]["schemas"]
    for code, response in theirs["responses"].items():
        response = _resolve(response, CONTRACT["components"]["responses"])
        if "content" not in response:
            assert "content" not in ours["responses"][code]
            continue
        expected = response["content"]["application/json"]["schema"]
        actual = ours["responses"][code]["content"]["application/json"]["schema"]
        assert _shape(actual, gen_c) == _shape(expected, con_c), (path, code)
    if "requestBody" in theirs:
        expected = theirs["requestBody"]["content"]["application/json"]["schema"]
        actual = ours["requestBody"]["content"]["application/json"]["schema"]
        assert _shape(actual, gen_c) == _shape(expected, con_c)


def test_error_codes_match_contract() -> None:
    from config.serializers import ERROR_CODES

    assert ERROR_CODES == CONTRACT["components"]["schemas"]["ErrorCode"]["enum"]
