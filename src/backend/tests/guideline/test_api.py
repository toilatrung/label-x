"""Tests cho module GDL — Guideline API và management command.

Acceptance Criteria (task-board.html T-003):
  AC-1: Nạp tệp hai lần không tạo bản ghi trùng (idempotency)
  AC-2a: API trả rule theo rule_id (200 + đúng payload)
  AC-2b: API trả rule theo mapping (nhóm lỗi/lớp)
  AC-2c: rule_id không tồn tại → 404 với {code, message, request_id}
  AC-3: Unauthenticated → 403; Authenticated → 200
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.contrib.auth.models import User
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
def auth_client(db: Any) -> APIClient:
    """APIClient đã đăng nhập với user bình thường."""
    user = User.objects.create_user(username="tester", password="pass")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture()
def anon_client() -> APIClient:
    """APIClient chưa đăng nhập."""
    return APIClient()


# ---------------------------------------------------------------------------
# AC-1: Idempotency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_load_guideline_idempotent(guideline_file: Path) -> None:
    """Nạp cùng tệp hai lần: chỉ tạo một GuidelineVersion, không trùng rule."""
    out = io.StringIO()
    call_command("load_guideline", str(guideline_file), stdout=out)
    call_command("load_guideline", str(guideline_file), stdout=out)

    assert GuidelineVersion.objects.filter(version_tag="test-v1").count() == 1
    assert GuidelineRule.objects.filter(version__version_tag="test-v1").count() == 3


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
    assert GuidelineRule.objects.filter(version__version_tag="test-v1").count() == 3
    # 2 nhóm mapping × số rule_ids (2+2=4 mapping records)
    assert RuleMapping.objects.filter(version__version_tag="test-v1").count() == 4


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


# ---------------------------------------------------------------------------
# AC-2a: GET rule theo rule_id → 200
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rule_detail_success(auth_client: APIClient, loaded_version: GuidelineVersion) -> None:
    """GET /api/guidelines/rules/VEH-01/ → 200 với đúng payload."""
    response = auth_client.get("/api/guidelines/rules/VEH-01/")
    assert response.status_code == 200
    data = response.json()
    assert data["rule_id"] == "VEH-01"
    assert data["section"] == "§2.1"
    assert "guideline_version" in data
    assert data["guideline_version"] == "test-v1"


@pytest.mark.django_db
def test_rule_detail_with_version_param(
    auth_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """GET với ?version=test-v1 phải trả cùng kết quả."""
    response = auth_client.get("/api/guidelines/rules/VEH-01/?version=test-v1")
    assert response.status_code == 200
    assert response.json()["rule_id"] == "VEH-01"


# ---------------------------------------------------------------------------
# AC-2b: GET rule theo mapping
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rule_list_by_error_group_and_class(
    auth_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """GET /api/guidelines/rules/?error_group=E2&class_name=car → rules từ mapping."""
    response = auth_client.get("/api/guidelines/rules/?error_group=E2&class_name=car")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    rule_ids = {r["rule_id"] for r in data["results"]}
    assert rule_ids == {"VEH-01", "VEH-02"}


@pytest.mark.django_db
def test_rule_list_no_filter_returns_all(
    auth_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """GET /api/guidelines/rules/ không filter → tất cả rule của latest version."""
    response = auth_client.get("/api/guidelines/rules/")
    assert response.status_code == 200
    assert response.json()["count"] == 3


# ---------------------------------------------------------------------------
# AC-2c: rule_id không tồn tại → 404 với hợp đồng lỗi
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rule_not_found(auth_client: APIClient, loaded_version: GuidelineVersion) -> None:
    """GET /api/guidelines/rules/NOTEXIST/ → 404 với {code, message, request_id}."""
    response = auth_client.get("/api/guidelines/rules/NOTEXIST/")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "not_found"
    assert "message" in data
    assert "request_id" in data


@pytest.mark.django_db
def test_rule_bad_version(auth_client: APIClient, loaded_version: GuidelineVersion) -> None:
    """?version=nonexistent → 404 với hợp đồng lỗi."""
    response = auth_client.get("/api/guidelines/rules/VEH-01/?version=nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "not_found"


# ---------------------------------------------------------------------------
# AC-3: Authentication / permission
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unauthenticated_cannot_read(
    anon_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """Unauthenticated GET → 403 (IsAuthenticated default)."""
    endpoints = [
        "/api/guidelines/",
        "/api/guidelines/rules/",
        "/api/guidelines/rules/VEH-01/",
    ]
    for url in endpoints:
        response = anon_client.get(url)
        assert response.status_code == 403, f"Expected 403 for {url}, got {response.status_code}"
        assert set(response.json()) == {"code", "message", "request_id"}
        assert response.json()["code"] == "forbidden"


@pytest.mark.django_db
def test_authenticated_can_read_versions(
    auth_client: APIClient, loaded_version: GuidelineVersion
) -> None:
    """Authenticated GET /api/guidelines/ → 200."""
    response = auth_client.get("/api/guidelines/")
    assert response.status_code == 200
    assert response.json()["count"] >= 1
