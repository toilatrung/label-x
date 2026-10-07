"""Tests cho module GDL — Guideline API và management command.

Kiểm tra:
- Nạp tệp hai lần không tạo bản ghi trùng (idempotency).
- Xác định đúng phiên bản mới nhất theo số học kể cả khi nạp lại version cũ.
- Tra rule theo rule_id (200).
- Tra rule theo context mapping (family, class_name, paired_class).
- Wildcard mapping (error_group rỗng, paired_class rỗng, class_name rỗng).
- Query parameter rỗng được bỏ qua.
- Phân trang Cursor ({next, previous, results}).
- Validate enum family (E1, E2, E3, structural), sai trả 400 VALIDATION_ERROR.
- Error contract: 400, 404, 405 có code, message, details, request_id.
- X-Request-ID header khớp request_id trong body.
- Quyền theo vai trò: chưa đăng nhập -> 403 NOT_AUTHENTICATED; sai vai trò -> 403 FORBIDDEN;
  4 vai trò được phép (reviewer, qa_lead, qc_admin, super_admin) và superuser -> 200.
- Endpoint /api/guidelines/ đã bị loại bỏ (404 NOT_FOUND).
"""

from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.contrib.auth.models import Group, User
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from guideline.models import GuidelineRule, GuidelineVersion, RuleMapping

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

SAMPLE_GUIDELINE: dict[str, Any] = {
    "version": "test-v1",
    "name": "Test Guideline",
    "rules": [
        {"id": "VEH-01", "section": "§2.1", "content": "Xe ô tô con."},
        {"id": "VEH-02", "section": "§2.2", "content": "Xe tải."},
        {"id": "GEO-01", "section": "§7.1", "content": "Quy tắc hình học."},
        {"id": "STR-01", "section": "§9.1", "content": "Cảnh báo cấu trúc."},
    ],
    "mappings": [
        {
            "error_group": "E2",
            "class_name": "car",
            "paired_class": "truck",
            "rule_ids": ["VEH-01", "VEH-02"],
        },
        {
            "error_group": "E1",
            "class_name": "car",
            "rule_ids": ["VEH-01", "GEO-01"],
        },
        # Wildcard 1: error_group rỗng -> khớp mọi family khi class_name="car"
        {
            "error_group": "",
            "class_name": "car",
            "rule_ids": ["GEO-01"],
        },
        # Wildcard 2: paired_class rỗng -> khớp mọi paired_class khi
        # error_group="E2", class_name="truck"
        {
            "error_group": "E2",
            "class_name": "truck",
            "paired_class": "",
            "rule_ids": ["VEH-02"],
        },
        # Wildcard 3: class_name rỗng -> khớp mọi class_name khi family="structural"
        {
            "error_group": "structural",
            "class_name": "",
            "rule_ids": ["STR-01"],
        },
    ],
}


@pytest.fixture()
def guideline_file(tmp_path: Path) -> Path:
    """Tạo tệp YAML tạm để test load_guideline command."""
    content = yaml.dump(SAMPLE_GUIDELINE, allow_unicode=True)
    p = tmp_path / "test_guideline.yaml"
    p.write_text(content, encoding="utf-8")
    return p


@pytest.fixture()
def loaded_version(guideline_file: Path) -> GuidelineVersion:
    """Nạp guideline mẫu vào DB và trả về GuidelineVersion."""
    out = io.StringIO()
    call_command("load_guideline", str(guideline_file), stdout=out)
    return GuidelineVersion.objects.get(version_tag="test-v1")


@pytest.fixture()
def client_factory(db: Any):
    """Factory tạo client theo vai trò."""

    def _create(role: str | None = None, is_superuser: bool = False) -> APIClient:
        client = APIClient()
        if role is None and not is_superuser:
            return client
        user = User.objects.create_user(
            username=f"user_{role or 'su'}_{uuid.uuid4().hex[:6]}",
            password="pass",
            is_superuser=is_superuser,
        )
        if role:
            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)
        client.force_authenticate(user=user)
        return client

    return _create


@pytest.fixture()
def reviewer_client(client_factory: Any) -> APIClient:
    return client_factory(role="reviewer")


@pytest.fixture()
def anon_client() -> APIClient:
    return APIClient()


# ---------------------------------------------------------------------------
# Management Command & Model Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_load_guideline_idempotent(guideline_file: Path) -> None:
    """Nạp cùng tệp hai lần: chỉ tạo một GuidelineVersion, không trùng rule."""
    out = io.StringIO()
    call_command("load_guideline", str(guideline_file), stdout=out)
    call_command("load_guideline", str(guideline_file), stdout=out)

    assert GuidelineVersion.objects.filter(version_tag="test-v1").count() == 1
    assert GuidelineRule.objects.filter(version__version_tag="test-v1").count() == 4


@pytest.mark.django_db
def test_load_guideline_output_on_skip(guideline_file: Path) -> None:
    """Lần nạp thứ hai: stdout phải có thông báo bỏ qua."""
    out = io.StringIO()
    call_command("load_guideline", str(guideline_file), stdout=out)
    out.truncate(0)
    out.seek(0)
    call_command("load_guideline", str(guideline_file), stdout=out)
    assert "Skipping" in out.getvalue()


@pytest.mark.django_db
def test_load_guideline_checksum_stored(guideline_file: Path) -> None:
    """Checksum SHA-256 phải được lưu đúng."""
    call_command("load_guideline", str(guideline_file))
    expected = hashlib.sha256(guideline_file.read_bytes()).hexdigest()
    version = GuidelineVersion.objects.get(version_tag="test-v1")
    assert version.file_checksum == expected


@pytest.mark.django_db
def test_load_guideline_creates_rules_and_mappings(guideline_file: Path) -> None:
    """Sau khi nạp: phải có đủ rules và mappings."""
    call_command("load_guideline", str(guideline_file))
    assert GuidelineRule.objects.filter(version__version_tag="test-v1").count() == 4
    assert RuleMapping.objects.filter(version__version_tag="test-v1").count() == 7


@pytest.mark.django_db
def test_load_guideline_rejects_invalid_yaml(tmp_path: Path) -> None:
    """YAML lỗi phải trả CommandError rõ ràng và không ghi dữ liệu."""
    invalid_file = tmp_path / "invalid.yaml"
    invalid_file.write_text("rules: [", encoding="utf-8")

    with pytest.raises(CommandError, match="valid UTF-8 YAML"):
        call_command("load_guideline", str(invalid_file))

    assert GuidelineVersion.objects.count() == 0


@pytest.mark.django_db
def test_load_guideline_rejects_duplicate_rule_ids(tmp_path: Path) -> None:
    """Rule ID trùng trong cùng tệp phải bị từ chối trước transaction."""
    duplicate = dict(SAMPLE_GUIDELINE)
    duplicate["rules"] = [SAMPLE_GUIDELINE["rules"][0], SAMPLE_GUIDELINE["rules"][0]]
    duplicate["mappings"] = []
    duplicate_file = tmp_path / "duplicate.yaml"
    duplicate_file.write_text(yaml.dump(duplicate, allow_unicode=True), encoding="utf-8")

    with pytest.raises(CommandError, match="Duplicate rule ID"):
        call_command("load_guideline", str(duplicate_file))

    assert GuidelineVersion.objects.count() == 0


@pytest.mark.django_db
def test_latest_version_not_broken_when_old_version_reloaded(
    tmp_path: Path, reviewer_client: APIClient
) -> None:
    """Nạp v1 rồi v2, sau đó cập nhật loaded_at của v1: default version vẫn là v2."""
    v1_data = {
        "version": "v1",
        "name": "Guideline v1",
        "rules": [{"id": "RULE-01", "section": "§1", "content": "Rule v1"}],
        "mappings": [{"error_group": "E1", "rule_ids": ["RULE-01"]}],
    }
    v2_data = {
        "version": "v2",
        "name": "Guideline v2",
        "rules": [{"id": "RULE-01", "section": "§1", "content": "Rule v2"}],
        "mappings": [{"error_group": "E1", "rule_ids": ["RULE-01"]}],
    }
    f1 = tmp_path / "v1.yaml"
    f2 = tmp_path / "v2.yaml"
    f1.write_text(yaml.dump(v1_data, allow_unicode=True), encoding="utf-8")
    f2.write_text(yaml.dump(v2_data, allow_unicode=True), encoding="utf-8")

    call_command("load_guideline", str(f1))
    call_command("load_guideline", str(f2))

    # Cập nhật v1 loaded_at sau v2
    v1 = GuidelineVersion.objects.get(version_tag="v1")
    v2 = GuidelineVersion.objects.get(version_tag="v2")
    v1.loaded_at = v2.loaded_at
    v1.save()

    response = reviewer_client.get("/api/guidelines/rules/")
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["guideline_version"] == "v2"


# ---------------------------------------------------------------------------
# API Detail Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rule_detail_success(reviewer_client: APIClient, loaded_version: GuidelineVersion) -> None:
    """GET /api/guidelines/rules/VEH-01/ → 200 với đúng payload."""
    response = reviewer_client.get("/api/guidelines/rules/VEH-01/")
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "VEH-01"
    assert data["section"] == "§2.1"
    assert data["guideline_version"] == "test-v1"


@pytest.mark.django_db
def test_rule_detail_with_version_param(
    reviewer_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """GET với ?version=test-v1 trả đúng kết quả."""
    response = reviewer_client.get("/api/guidelines/rules/VEH-01/?version=test-v1")
    assert response.status_code == 200
    assert response.json()["rule_id"] == "VEH-01"


# ---------------------------------------------------------------------------
# API Cursor Pagination & Filtering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cursor_pagination_envelope(
    reviewer_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """Envelope phản hồi cursor có đủ {next, previous, results}."""
    response = reviewer_client.get("/api/guidelines/rules/")
    assert response.status_code == 200
    data = response.json()
    assert "next" in data
    assert "previous" in data
    assert "results" in data
    assert len(data["results"]) == 4


@pytest.mark.django_db
def test_family_query_and_enum_validation(
    reviewer_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """Query ?family=E2 lọc đúng; enum sai trả 400 VALIDATION_ERROR."""
    # Hợp lệ
    response = reviewer_client.get("/api/guidelines/rules/?family=E2&class_name=car")
    assert response.status_code == 200
    data = response.json()
    rule_ids = {r["rule_id"] for r in data["results"]}
    # VEH-01, VEH-02 (từ E2 mapping) và GEO-01 (từ wildcard mapping error_group="")
    assert "VEH-01" in rule_ids
    assert "VEH-02" in rule_ids
    assert "GEO-01" in rule_ids

    # Sai enum -> 400
    bad_response = reviewer_client.get("/api/guidelines/rules/?family=INVALID")
    assert bad_response.status_code == 400
    err = bad_response.json()
    assert err["code"] == "VALIDATION_ERROR"
    assert "family" in err["details"]["fields"]


@pytest.mark.django_db
def test_empty_query_params_ignored(
    reviewer_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """Query parameter rỗng (?family=&class_name=&paired_class=&version=) được bỏ qua."""
    response = reviewer_client.get(
        "/api/guidelines/rules/?family=&class_name=&paired_class=&version="
    )
    assert response.status_code == 200
    assert len(response.json()["results"]) == 4


@pytest.mark.django_db
def test_wildcard_mapping_three_cases(
    reviewer_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """Kiểm tra ba trường hợp wildcard mapping:

    1. error_group rỗng: khớp mọi family khi class_name="car"
    2. paired_class rỗng: khớp mọi paired_class khi family="E2", class_name="truck"
    3. class_name rỗng: khớp mọi class_name khi family="structural"
    """
    # TH1: error_group rỗng -> tìm family=E1, class_name=car vẫn chứa GEO-01 (có error_group="")
    r1 = reviewer_client.get("/api/guidelines/rules/?family=E1&class_name=car")
    assert r1.status_code == 200
    r1_ids = {r["rule_id"] for r in r1.json()["results"]}
    assert "GEO-01" in r1_ids
    assert "VEH-01" in r1_ids

    # TH2: paired_class rỗng -> tìm family=E2, class_name=truck, paired_class=bus vẫn chứa VEH-02
    r2 = reviewer_client.get("/api/guidelines/rules/?family=E2&class_name=truck&paired_class=bus")
    assert r2.status_code == 200
    r2_ids = {r["rule_id"] for r in r2.json()["results"]}
    assert "VEH-02" in r2_ids

    # TH3: class_name rỗng -> tìm family=structural, class_name=car vẫn chứa STR-01
    r3 = reviewer_client.get("/api/guidelines/rules/?family=structural&class_name=car")
    assert r3.status_code == 200
    r3_ids = {r["rule_id"] for r in r3.json()["results"]}
    assert "STR-01" in r3_ids


# ---------------------------------------------------------------------------
# Error Contract & Request-ID Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_error_contracts_400_404_405(
    reviewer_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """Các mã 400, 404, 405 tuân thủ chuẩn {code, message, details, request_id}."""
    # 400
    r_400 = reviewer_client.get("/api/guidelines/rules/?family=bad")
    assert r_400.status_code == 400
    d_400 = r_400.json()
    assert d_400["code"] == "VALIDATION_ERROR"
    assert isinstance(d_400["details"], dict)
    assert "request_id" in d_400

    # 404
    r_404 = reviewer_client.get("/api/guidelines/rules/NONEXISTENT/")
    assert r_404.status_code == 404
    d_404 = r_404.json()
    assert d_404["code"] == "NOT_FOUND"
    assert isinstance(d_404["details"], dict)
    assert "request_id" in d_404

    # 405 (Method Not Allowed)
    r_405 = reviewer_client.post("/api/guidelines/rules/", {})
    assert r_405.status_code == 405
    d_405 = r_405.json()
    assert d_405["code"] == "VALIDATION_ERROR"
    assert isinstance(d_405["details"], dict)
    assert "request_id" in d_405


@pytest.mark.django_db
def test_request_id_in_body_matches_response_header(
    reviewer_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """request_id trong body trùng khớp header X-Request-ID (kể cả khi client truyền vào)."""
    # Trường hợp tự sinh
    resp = reviewer_client.get("/api/guidelines/rules/NOTEXIST/")
    assert resp.status_code == 404
    body_id = resp.json()["request_id"]
    header_id = resp.headers["X-Request-ID"]
    assert body_id == header_id

    # Trường hợp client gửi X-Request-ID
    custom_id = "trace-custom-uuid-9999"
    resp_custom = reviewer_client.get(
        "/api/guidelines/rules/NOTEXIST/", HTTP_X_REQUEST_ID=custom_id
    )
    assert resp_custom.headers["X-Request-ID"] == custom_id
    assert resp_custom.json()["request_id"] == custom_id


# ---------------------------------------------------------------------------
# RBAC Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_returns_not_authenticated(
    anon_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """Chưa đăng nhập trả 403 với code NOT_AUTHENTICATED."""
    endpoints = [
        "/api/guidelines/rules/",
        "/api/guidelines/rules/VEH-01/",
    ]
    for url in endpoints:
        resp = anon_client.get(url)
        assert resp.status_code == 403
        data = resp.json()
        assert data["code"] == "NOT_AUTHENTICATED"
        assert "message" in data
        assert "request_id" in data
        assert isinstance(data["details"], dict)


@pytest.mark.django_db
def test_unauthorized_role_returns_forbidden(
    client_factory: Any, loaded_version: GuidelineVersion
) -> None:
    """User không có role hoặc có role annotator bị từ chối 403 FORBIDDEN."""
    # User thường không có nhóm
    normal_client = client_factory(role=None)
    user_no_group = User.objects.create_user(username="normal_user", password="p")
    normal_client.force_authenticate(user=user_no_group)
    r1 = normal_client.get("/api/guidelines/rules/")
    assert r1.status_code == 403
    assert r1.json()["code"] == "FORBIDDEN"

    # Annotator
    annotator_client = client_factory(role="annotator")
    r2 = annotator_client.get("/api/guidelines/rules/")
    assert r2.status_code == 403
    assert r2.json()["code"] == "FORBIDDEN"


@pytest.mark.django_db
def test_four_allowed_roles_and_superuser_return_200(
    client_factory: Any, loaded_version: GuidelineVersion
) -> None:
    """reviewer, qa_lead, qc_admin, super_admin và superuser đều được phép truy cập (200)."""
    allowed_roles = ["reviewer", "qa_lead", "qc_admin", "super_admin"]
    for role in allowed_roles:
        client = client_factory(role=role)
        resp = client.get("/api/guidelines/rules/")
        assert resp.status_code == 200, f"Role {role} phải được phép"

    # Superuser
    su_client = client_factory(is_superuser=True)
    resp_su = su_client.get("/api/guidelines/rules/")
    assert resp_su.status_code == 200


# ---------------------------------------------------------------------------
# Version Endpoint Removed
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_version_endpoint_removed(
    reviewer_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """GET /api/guidelines/ không còn trong route -> 404 NOT_FOUND."""
    resp = reviewer_client.get("/api/guidelines/")
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_cursor_pagination_fifty_one_rules(reviewer_client: APIClient, tmp_path: Path) -> None:
    """Tạo 51 rule: trang đầu có 50 rule, next != None, previous == None;
    gọi URL trong next -> trang 2 có 1 rule, previous != None; không có count."""
    rules = [{"id": f"RULE-{i:03d}", "section": "§1", "content": f"Rule {i}"} for i in range(1, 52)]
    data = {
        "version": "page-v1",
        "name": "Pagination Test",
        "rules": rules,
        "mappings": [{"error_group": "E1", "rule_ids": ["RULE-001"]}],
    }
    file_path = tmp_path / "page_test.yaml"
    file_path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    call_command("load_guideline", str(file_path))

    # Trang 1
    resp1 = reviewer_client.get("/api/guidelines/rules/?version=page-v1")
    assert resp1.status_code == 200
    d1 = resp1.json()
    assert "count" not in d1
    assert len(d1["results"]) == 50
    assert d1["previous"] is None
    assert d1["next"] is not None

    # Gọi URL trong next
    resp2 = reviewer_client.get(d1["next"])
    assert resp2.status_code == 200
    d2 = resp2.json()
    assert "count" not in d2
    assert len(d2["results"]) == 1
    assert d2["previous"] is not None
