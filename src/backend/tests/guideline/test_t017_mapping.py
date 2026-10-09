"""Tests kiểm chứng độc lập cho Task T-017 (Issue #43, Epic E-03, CR-107).

Bao gồm:
1. Nạp tệp YAML hợp lệ (kể cả mapping có paired_class) và kiểm tra RuleMapping tạo đúng.
2. SHA-256 idempotency: nạp lại cùng tệp tạo record skipped, không trùng mapping.
3. Bắt buộc --actor: thiếu hoặc actor không tồn tại bị từ chối; tạo record rejected.
4. Kiểm tra actor.is_active: actor bị khóa bị từ chối; tạo record rejected.
5. Kiểm tra quyền actor: actor không có role QC_ADMIN hoặc SUPER_ADMIN bị từ chối.
6. Validation taxonomy 10 lớp BDD100K: class_name / paired_class ngoài taxonomy bị từ chối.
7. Validation IssueFamily: error_group ngoài IssueFamily bị từ chối.
8. Validation rule_id: rule_id không tồn tại bị từ chối.
9. Duplicate mapping: dòng mapping trùng bị từ chối.
10. All-or-nothing: file có dòng hợp lệ và dòng lỗi phải rollback toàn bộ transaction.
11. Lỗi theo từng dòng: GuidelineLoadRecord.errors lưu danh sách lỗi có cấu trúc.
12. Tính bất biến GuidelineLoadRecord: chặn save(), instance delete, queryset delete/update.
13. API GET /api/guidelines/mappings/ và RBAC matrix.
14. API mapping chỉ đọc: POST, PUT, PATCH, DELETE trả 405 Method Not Allowed.
15. Lọc API theo family, class_name, paired_class, version.
16. Cursor pagination cho danh sách mapping khi có trên 50 bản ghi.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from rest_framework.test import APIClient

from accounts.models import RoleAssignment
from guideline.models import GuidelineLoadRecord, GuidelineRule, GuidelineVersion, RuleMapping

User = get_user_model()

VALID_T017_GUIDELINE: dict[str, Any] = {
    "version": "t017-v1",
    "name": "BDD100K Guideline T-017",
    "rules": [
        {"id": "RULE-01", "section": "§1.1", "content": "Quy tắc 1 xe con"},
        {"id": "RULE-02", "section": "§1.2", "content": "Quy tắc 2 xe tải"},
        {"id": "RULE-03", "section": "§2.1", "content": "Quy tắc 3 người đi bộ"},
    ],
    "mappings": [
        {
            "error_group": "E2",
            "class_name": "car",
            "paired_class": "truck",
            "rule_ids": ["RULE-01", "RULE-02"],
        },
        {
            "error_group": "E1",
            "class_name": "pedestrian",
            "rule_ids": ["RULE-03"],
        },
        {
            "error_group": "structural",
            "class_name": "car",
            "rule_ids": ["RULE-01"],
        },
    ],
}


@pytest.fixture()
def qc_admin_user(db: Any) -> Any:
    user = User.objects.create_user(username=f"qc_admin_{uuid.uuid4().hex[:6]}", password="pwd")
    RoleAssignment.objects.create(user=user, role="qc_admin", dataset_id=None)
    return user


@pytest.fixture()
def super_admin_user(db: Any) -> Any:
    user = User.objects.create_user(username=f"super_admin_{uuid.uuid4().hex[:6]}", password="pwd")
    RoleAssignment.objects.create(user=user, role="super_admin", dataset_id=None)
    return user


@pytest.fixture()
def annotator_user(db: Any) -> Any:
    user = User.objects.create_user(username=f"annotator_{uuid.uuid4().hex[:6]}", password="pwd")
    RoleAssignment.objects.create(user=user, role="annotator", dataset_id=1)
    return user


@pytest.fixture()
def valid_yaml_file(tmp_path: Path) -> Path:
    p = tmp_path / "valid_t017.yaml"
    p.write_text(yaml.dump(VALID_T017_GUIDELINE, allow_unicode=True), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Tests cho loader & actor
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_load_guideline_requires_actor_argument(valid_yaml_file: Path) -> None:
    """Lệnh nạp thiếu --actor phải raise CommandError."""
    with pytest.raises(CommandError, match="--actor"):
        call_command("load_guideline", str(valid_yaml_file))


@pytest.mark.django_db
def test_load_guideline_rejects_nonexistent_actor(valid_yaml_file: Path) -> None:
    """Actor không tồn tại bị từ chối và ghi bản ghi load rejected."""
    checksum = hashlib.sha256(valid_yaml_file.read_bytes()).hexdigest()
    with pytest.raises(CommandError, match="does not exist"):
        call_command("load_guideline", str(valid_yaml_file), actor="ghost_user")

    record = GuidelineLoadRecord.objects.filter(actor_username="ghost_user").first()
    assert record is not None
    assert record.result == GuidelineLoadRecord.Result.REJECTED
    assert record.file_checksum == checksum
    assert any("does not exist" in e for e in record.errors)
    assert GuidelineVersion.objects.count() == 0


@pytest.mark.django_db
def test_load_guideline_rejects_inactive_actor(valid_yaml_file: Path, qc_admin_user: Any) -> None:
    """Actor bị khóa (is_active=False) bị từ chối và ghi record rejected."""
    qc_admin_user.is_active = False
    qc_admin_user.save()

    with pytest.raises(CommandError, match="not active"):
        call_command("load_guideline", str(valid_yaml_file), actor=qc_admin_user.username)

    record = GuidelineLoadRecord.objects.filter(actor_username=qc_admin_user.username).first()
    assert record is not None
    assert record.result == GuidelineLoadRecord.Result.REJECTED
    assert any("not active" in e for e in record.errors)
    assert GuidelineVersion.objects.count() == 0


@pytest.mark.django_db
def test_load_guideline_rejects_unauthorized_role_actor(
    valid_yaml_file: Path, annotator_user: Any
) -> None:
    """Actor không có vai trò QC_ADMIN hoặc SUPER_ADMIN bị từ chối."""
    with pytest.raises(CommandError, match="lacks permission"):
        call_command("load_guideline", str(valid_yaml_file), actor=annotator_user.username)

    record = GuidelineLoadRecord.objects.filter(actor_username=annotator_user.username).first()
    assert record is not None
    assert record.result == GuidelineLoadRecord.Result.REJECTED
    assert any("lacks permission" in e for e in record.errors)
    assert GuidelineVersion.objects.count() == 0


@pytest.mark.django_db
def test_load_guideline_valid_with_paired_class_and_record(
    valid_yaml_file: Path, qc_admin_user: Any
) -> None:
    """Tệp hợp lệ có paired_class nạp thành công, tạo GuidelineLoadRecord(accepted)."""
    out = io.StringIO()
    call_command("load_guideline", str(valid_yaml_file), actor=qc_admin_user.username, stdout=out)

    assert GuidelineVersion.objects.filter(version_tag="t017-v1").count() == 1
    assert GuidelineRule.objects.filter(version__version_tag="t017-v1").count() == 3
    # 2 mappings car+truck (RULE-01, 02) + 1 pedestrian (RULE-03) + 1 structural = 4
    assert RuleMapping.objects.filter(version__version_tag="t017-v1").count() == 4

    # Kiểm tra mapping có paired_class="truck"
    paired = RuleMapping.objects.filter(
        version__version_tag="t017-v1", error_group="E2", class_name="car", paired_class="truck"
    )
    assert paired.count() == 2

    # Kiểm tra load record accepted
    record = GuidelineLoadRecord.objects.filter(
        actor_username=qc_admin_user.username, result=GuidelineLoadRecord.Result.ACCEPTED
    ).first()
    assert record is not None
    assert record.actor == qc_admin_user
    assert record.row_count > 0
    assert record.file_checksum == hashlib.sha256(valid_yaml_file.read_bytes()).hexdigest()
    assert record.errors == []


@pytest.mark.django_db
def test_load_guideline_sha256_idempotency_creates_skipped_record(
    valid_yaml_file: Path, qc_admin_user: Any
) -> None:
    """Nạp lại cùng tệp tạo GuidelineLoadRecord(skipped) và không nhân đôi mapping."""
    call_command("load_guideline", str(valid_yaml_file), actor=qc_admin_user.username)
    mappings_count_1 = RuleMapping.objects.count()

    out = io.StringIO()
    call_command("load_guideline", str(valid_yaml_file), actor=qc_admin_user.username, stdout=out)
    assert "Skipping" in out.getvalue()
    assert RuleMapping.objects.count() == mappings_count_1

    record_skipped = GuidelineLoadRecord.objects.filter(
        actor_username=qc_admin_user.username, result=GuidelineLoadRecord.Result.SKIPPED
    ).first()
    assert record_skipped is not None
    assert record_skipped.errors == []


# ---------------------------------------------------------------------------
# 2. Tests cho validation & all-or-nothing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_load_guideline_rejects_unknown_rule_id(tmp_path: Path, qc_admin_user: Any) -> None:
    """Rule ID không tồn tại bị từ chối cả tệp."""
    bad_data = dict(VALID_T017_GUIDELINE)
    bad_data["version"] = "bad-rule-v1"
    bad_data["mappings"] = [
        {"error_group": "E1", "class_name": "car", "rule_ids": ["NONEXISTENT-99"]}
    ]
    p = tmp_path / "bad_rule.yaml"
    p.write_text(yaml.dump(bad_data), encoding="utf-8")

    with pytest.raises(CommandError, match="unknown rule_id"):
        call_command("load_guideline", str(p), actor=qc_admin_user.username)

    assert GuidelineVersion.objects.filter(version_tag="bad-rule-v1").count() == 0
    record = GuidelineLoadRecord.objects.filter(
        file_checksum=hashlib.sha256(p.read_bytes()).hexdigest()
    ).first()
    assert record is not None
    assert record.result == GuidelineLoadRecord.Result.REJECTED
    assert any("NONEXISTENT-99" in e for e in record.errors)


@pytest.mark.django_db
def test_load_guideline_rejects_class_name_outside_taxonomy(
    tmp_path: Path, qc_admin_user: Any
) -> None:
    """class_name ngoài 10 lớp BDD100K bị từ chối."""
    bad_data = dict(VALID_T017_GUIDELINE)
    bad_data["version"] = "bad-class-v1"
    bad_data["mappings"] = [
        {"error_group": "E1", "class_name": "airplane", "rule_ids": ["RULE-01"]}
    ]
    p = tmp_path / "bad_class.yaml"
    p.write_text(yaml.dump(bad_data), encoding="utf-8")

    with pytest.raises(CommandError, match="outside BDD100K taxonomy"):
        call_command("load_guideline", str(p), actor=qc_admin_user.username)

    assert GuidelineVersion.objects.filter(version_tag="bad-class-v1").count() == 0


@pytest.mark.django_db
def test_load_guideline_rejects_paired_class_outside_taxonomy(
    tmp_path: Path, qc_admin_user: Any
) -> None:
    """paired_class ngoài 10 lớp BDD100K bị từ chối."""
    bad_data = dict(VALID_T017_GUIDELINE)
    bad_data["version"] = "bad-paired-v1"
    bad_data["mappings"] = [
        {
            "error_group": "E2",
            "class_name": "car",
            "paired_class": "submarine",
            "rule_ids": ["RULE-01"],
        }
    ]
    p = tmp_path / "bad_paired.yaml"
    p.write_text(yaml.dump(bad_data), encoding="utf-8")

    with pytest.raises(CommandError, match="outside BDD100K taxonomy"):
        call_command("load_guideline", str(p), actor=qc_admin_user.username)

    assert GuidelineVersion.objects.filter(version_tag="bad-paired-v1").count() == 0


@pytest.mark.django_db
def test_load_guideline_rejects_family_outside_issue_family(
    tmp_path: Path, qc_admin_user: Any
) -> None:
    """Family ngoài enum IssueFamily (E1, E2, E3, structural) bị từ chối."""
    bad_data = dict(VALID_T017_GUIDELINE)
    bad_data["version"] = "bad-family-v1"
    bad_data["mappings"] = [
        {"error_group": "E99_UNKNOWN", "class_name": "car", "rule_ids": ["RULE-01"]}
    ]
    p = tmp_path / "bad_family.yaml"
    p.write_text(yaml.dump(bad_data), encoding="utf-8")

    with pytest.raises(CommandError, match="not a valid IssueFamily"):
        call_command("load_guideline", str(p), actor=qc_admin_user.username)

    assert GuidelineVersion.objects.filter(version_tag="bad-family-v1").count() == 0


@pytest.mark.django_db
def test_load_guideline_rejects_duplicate_mapping_tuple(tmp_path: Path, qc_admin_user: Any) -> None:
    """Dòng mapping trùng bộ selector + rule_id bị từ chối."""
    bad_data = dict(VALID_T017_GUIDELINE)
    bad_data["version"] = "bad-dup-v1"
    bad_data["mappings"] = [
        {"error_group": "E1", "class_name": "car", "rule_ids": ["RULE-01"]},
        {"error_group": "E1", "class_name": "car", "rule_ids": ["RULE-01"]},
    ]
    p = tmp_path / "bad_dup.yaml"
    p.write_text(yaml.dump(bad_data), encoding="utf-8")

    with pytest.raises(CommandError, match="Duplicate mapping"):
        call_command("load_guideline", str(p), actor=qc_admin_user.username)

    assert GuidelineVersion.objects.filter(version_tag="bad-dup-v1").count() == 0


@pytest.mark.django_db
def test_load_guideline_all_or_nothing_rollback(tmp_path: Path, qc_admin_user: Any) -> None:
    """Tệp có 2 dòng hợp lệ và 1 dòng lỗi ở cuối: không ghi một phần nào vào DB."""
    mixed_data = dict(VALID_T017_GUIDELINE)
    mixed_data["version"] = "mixed-v1"
    mixed_data["mappings"] = [
        {"error_group": "E1", "class_name": "car", "rule_ids": ["RULE-01"]},
        {"error_group": "E2", "class_name": "truck", "rule_ids": ["RULE-02"]},
        {"error_group": "E1", "class_name": "spaceship", "rule_ids": ["RULE-01"]},  # lỗi taxonomy
    ]
    p = tmp_path / "mixed.yaml"
    p.write_text(yaml.dump(mixed_data), encoding="utf-8")

    with pytest.raises(CommandError, match="outside BDD100K taxonomy"):
        call_command("load_guideline", str(p), actor=qc_admin_user.username)

    assert GuidelineVersion.objects.filter(version_tag="mixed-v1").count() == 0
    assert RuleMapping.objects.filter(version__version_tag="mixed-v1").count() == 0
    record = GuidelineLoadRecord.objects.filter(
        file_checksum=hashlib.sha256(p.read_bytes()).hexdigest()
    ).first()
    assert record is not None
    assert record.result == GuidelineLoadRecord.Result.REJECTED


@pytest.mark.django_db
def test_load_guideline_errors_structured_list(tmp_path: Path, qc_admin_user: Any) -> None:
    """Tệp có nhiều lỗi phải lưu từng lỗi riêng biệt trong mảng GuidelineLoadRecord.errors."""
    multi_err_data = dict(VALID_T017_GUIDELINE)
    multi_err_data["version"] = "multi-err-v1"
    multi_err_data["mappings"] = [
        {"error_group": "INVALID_FAM", "class_name": "car", "rule_ids": ["RULE-01"]},
        {"error_group": "E1", "class_name": "alien", "rule_ids": ["RULE-01"]},
        {"error_group": "E2", "class_name": "car", "rule_ids": ["NONEXISTENT-99"]},
    ]
    p = tmp_path / "multi_err.yaml"
    p.write_text(yaml.dump(multi_err_data), encoding="utf-8")

    with pytest.raises(CommandError):
        call_command("load_guideline", str(p), actor=qc_admin_user.username)

    record = GuidelineLoadRecord.objects.filter(
        file_checksum=hashlib.sha256(p.read_bytes()).hexdigest()
    ).first()
    assert record is not None
    assert isinstance(record.errors, list)
    assert len(record.errors) >= 3
    assert any("INVALID_FAM" in e for e in record.errors)
    assert any("alien" in e for e in record.errors)
    assert any("NONEXISTENT-99" in e for e in record.errors)


# ---------------------------------------------------------------------------
# 3. Tests cho tính bất biến của GuidelineLoadRecord
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guideline_load_record_immutability(valid_yaml_file: Path, qc_admin_user: Any) -> None:
    """GuidelineLoadRecord cấm mọi thao tác sửa, xóa cá thể và bulk delete/update."""
    call_command("load_guideline", str(valid_yaml_file), actor=qc_admin_user.username)
    record = GuidelineLoadRecord.objects.first()
    assert record is not None

    # 1. Chặn update qua save()
    with pytest.raises(ValueError, match="append-only"):
        record.actor_username = "hacked"
        record.save()

    # 2. Chặn delete() trên instance
    with pytest.raises(ValueError, match="append-only"):
        record.delete()

    # 3. Chặn bulk delete qua QuerySet
    with pytest.raises(ValueError, match="append-only"):
        GuidelineLoadRecord.objects.all().delete()

    # 4. Chặn bulk update qua QuerySet
    with pytest.raises(ValueError, match="append-only"):
        GuidelineLoadRecord.objects.all().update(actor_username="hacked")

    # Bản ghi vẫn nguyên vẹn
    assert GuidelineLoadRecord.objects.count() == 1


# ---------------------------------------------------------------------------
# 4. Tests cho API GET /api/guidelines/mappings/ và RBAC
# ---------------------------------------------------------------------------


@pytest.fixture()
def client_for_role(db: Any):
    def _create(role: str | None = None, is_superuser: bool = False) -> APIClient:
        client = APIClient()
        if role is None and not is_superuser:
            return client
        user = User.objects.create_user(
            username=f"user_{role or 'su'}_{uuid.uuid4().hex[:6]}",
            password="pwd",
            is_superuser=is_superuser,
        )
        if role:
            RoleAssignment.objects.create(
                user=user,
                role=role,
                dataset_id=None if role in ("super_admin", "qc_admin") else 1,
            )
        client.force_authenticate(user=user)
        return client

    return _create


@pytest.mark.django_db
def test_guideline_mappings_api_rbac(
    valid_yaml_file: Path, qc_admin_user: Any, client_for_role: Any
) -> None:
    """Quyền truy cập GET /api/guidelines/mappings/ tuân thủ rbac-matrix."""
    call_command("load_guideline", str(valid_yaml_file), actor=qc_admin_user.username)

    # 1. Unauthenticated -> 403
    anon = client_for_role(role=None)
    assert anon.get("/api/guidelines/mappings/").status_code == 403

    # 2. Annotator -> 403
    annotator = client_for_role(role="annotator")
    assert annotator.get("/api/guidelines/mappings/").status_code == 403

    # 3. Reviewer -> 200
    reviewer = client_for_role(role="reviewer")
    resp_rev = reviewer.get("/api/guidelines/mappings/")
    assert resp_rev.status_code == 200
    assert len(resp_rev.json()["results"]) == 4

    # 4. QA Lead -> 200
    qa_lead = client_for_role(role="qa_lead")
    assert qa_lead.get("/api/guidelines/mappings/").status_code == 200

    # 5. QC Admin -> 200
    qc_admin = client_for_role(role="qc_admin")
    assert qc_admin.get("/api/guidelines/mappings/").status_code == 200

    # 6. Super Admin -> 200
    super_admin = client_for_role(role="super_admin")
    assert super_admin.get("/api/guidelines/mappings/").status_code == 200


@pytest.mark.django_db
def test_guideline_mappings_api_write_methods_405(
    valid_yaml_file: Path, qc_admin_user: Any, client_for_role: Any
) -> None:
    """Mapping API chỉ hỗ trợ GET; POST, PUT, PATCH, DELETE trả 405 Method Not Allowed."""
    call_command("load_guideline", str(valid_yaml_file), actor=qc_admin_user.username)
    client = client_for_role(role="qc_admin")

    assert client.post("/api/guidelines/mappings/", data={}).status_code == 405
    assert client.put("/api/guidelines/mappings/", data={}).status_code == 405
    assert client.patch("/api/guidelines/mappings/", data={}).status_code == 405
    assert client.delete("/api/guidelines/mappings/").status_code == 405


@pytest.mark.django_db
def test_guideline_mappings_api_filters(
    valid_yaml_file: Path, qc_admin_user: Any, client_for_role: Any
) -> None:
    """Lọc mapping theo family (ánh xạ error_group), class_name, paired_class, version."""
    call_command("load_guideline", str(valid_yaml_file), actor=qc_admin_user.username)
    client = client_for_role(role="reviewer")

    # Lọc theo family
    resp_fam = client.get("/api/guidelines/mappings/?family=E2")
    assert resp_fam.status_code == 200
    assert len(resp_fam.json()["results"]) == 2
    for item in resp_fam.json()["results"]:
        assert item["error_group"] == "E2"

    # Lọc theo paired_class
    resp_pair = client.get("/api/guidelines/mappings/?paired_class=truck")
    assert resp_pair.status_code == 200
    assert len(resp_pair.json()["results"]) == 2
    for item in resp_pair.json()["results"]:
        assert item["paired_class"] == "truck"

    # Lọc theo family không hợp lệ -> 400
    resp_invalid_fam = client.get("/api/guidelines/mappings/?family=UNKNOWN")
    assert resp_invalid_fam.status_code == 400


@pytest.mark.django_db
def test_guideline_mappings_cursor_pagination(
    tmp_path: Path, qc_admin_user: Any, client_for_role: Any
) -> None:
    """Cursor pagination 51 mapping: trang 1 có 50 items, next != None; trang 2 có 1 item."""
    rules = [{"id": f"R-{i:03d}", "section": "§1", "content": f"Content {i}"} for i in range(1, 52)]
    mappings = [
        {"error_group": "E1", "class_name": "car", "rule_ids": [f"R-{i:03d}"]} for i in range(1, 52)
    ]
    data = {"version": "page-51", "name": "Pagination 51", "rules": rules, "mappings": mappings}
    p = tmp_path / "page51.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")

    call_command("load_guideline", str(p), actor=qc_admin_user.username)
    client = client_for_role(role="reviewer")

    resp_p1 = client.get("/api/guidelines/mappings/")
    assert resp_p1.status_code == 200
    body_p1 = resp_p1.json()
    assert len(body_p1["results"]) == 50
    assert body_p1["next"] is not None
    assert body_p1["previous"] is None

    # Gọi trang 2 theo cursor
    resp_p2 = client.get(body_p1["next"])
    assert resp_p2.status_code == 200
    body_p2 = resp_p2.json()
    assert len(body_p2["results"]) == 1
    assert body_p2["previous"] is not None
