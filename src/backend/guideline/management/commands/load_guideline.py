"""Management command nạp tệp guideline YAML vào DB (T-003, T-017).

Idempotency: nếu checksum của tệp trùng với version đã có, command bỏ qua.
Nếu version_tag đã tồn tại nhưng checksum khác, command từ chối
để tránh ghi đè phiên bản đang dùng.

Dùng:
    python manage.py load_guideline fixtures/bdd100k_guideline_v1.yaml --actor qc-admin
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from guideline.models import GuidelineLoadRecord, GuidelineRule, GuidelineVersion, RuleMapping

BDD100K_CLASSES = {
    "car",
    "truck",
    "bus",
    "pedestrian",
    "rider",
    "bicycle",
    "motorcycle",
    "traffic light",
    "traffic sign",
    "train",
}
VALID_ERROR_GROUPS = {"", "E1", "E2", "E3", "structural"}


class GuidelineMappingValidationError(CommandError):
    """Lỗi kiểm tra mapping guideline không hợp lệ, giữ danh sách lỗi theo dòng/mục."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("Invalid guideline mappings: " + "; ".join(errors))


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CommandError(f"{context} must be a mapping.")
    return cast(dict[str, Any], value)


def _required_text(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CommandError(f"{context}.{key} must be a non-empty string.")
    return value.strip()


def _optional_text(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CommandError(f"{context}.{key} must be a string if provided.")
    return value.strip()


def _parse_guideline(raw: bytes) -> tuple[str, str, list[dict[str, str]], list[dict[str, Any]]]:
    """Parse YAML và trả về (version_tag, name, rules, mappings).

    Quy tắc kiểm tra (T-003, T-017):
    - version_tag, name không rỗng
    - rules: mỗi rule có id, section, content không rỗng; id không trùng
    - mappings: selector (error_group, class_name, paired_class) có ít nhất 1 giá trị
    - rule_ids tham chiếu tới rule_id đã định nghĩa trong rules
    - class_name, paired_class thuộc taxonomy 10 lớp BDD100K
    - error_group thuộc IssueFamily enum
    - Không trùng bộ selector + rule_id
    """
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except yaml.YAMLError as exc:
        raise CommandError(f"File is not valid UTF-8 YAML: YAML parse error: {exc}") from exc

    if not isinstance(data, dict):
        raise CommandError("YAML root must be a mapping.")

    # Tương thích cả định dạng có wrapper `guideline:` và định dạng phẳng
    if "guideline" in data and isinstance(data["guideline"], dict):
        data = data["guideline"]

    version_tag = _required_text(data, "version", "guideline")
    name = _required_text(data, "name", "guideline")

    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise CommandError("guideline.rules must be a non-empty list.")

    rules: list[dict[str, str]] = []
    known_rule_ids: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        context = f"rules[{index}]"
        rule = _mapping(raw_rule, context)
        rule_id = _required_text(rule, "id", context)
        section = _required_text(rule, "section", context)
        content = _required_text(rule, "content", context)

        if rule_id in known_rule_ids:
            raise CommandError(f"Duplicate rule ID '{rule_id}' at {context}.")
        known_rule_ids.add(rule_id)
        rules.append({"id": rule_id, "section": section, "content": content})

    raw_mappings = data.get("mappings", [])
    if not isinstance(raw_mappings, list):
        raise CommandError("guideline.mappings must be a list.")

    mappings: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_mappings: set[tuple[str, str, str, str]] = set()
    for index, raw_mapping in enumerate(raw_mappings):
        context = f"mappings[{index}]"
        mapping = _mapping(raw_mapping, context)
        error_group = _optional_text(mapping, "error_group", context)
        class_name = _optional_text(mapping, "class_name", context)
        paired_class = _optional_text(mapping, "paired_class", context)
        if not any((error_group, class_name, paired_class)):
            errors.append(f"{context} must contain at least one mapping selector.")
        if error_group not in VALID_ERROR_GROUPS:
            errors.append(f"{context}.error_group '{error_group}' is not a valid IssueFamily.")
        if class_name and class_name not in BDD100K_CLASSES:
            errors.append(f"{context}.class_name '{class_name}' is outside BDD100K taxonomy.")
        if paired_class and paired_class not in BDD100K_CLASSES:
            errors.append(f"{context}.paired_class '{paired_class}' is outside BDD100K taxonomy.")

        raw_rule_ids = mapping.get("rule_ids")
        if not isinstance(raw_rule_ids, list) or not raw_rule_ids:
            errors.append(f"{context}.rule_ids must be a non-empty list.")
            continue

        rule_ids: list[str] = []
        for raw_rule_id in raw_rule_ids:
            if not isinstance(raw_rule_id, str) or not raw_rule_id.strip():
                errors.append(f"{context}.rule_ids must contain only non-empty strings.")
                continue
            rule_id = raw_rule_id.strip()
            if rule_id not in known_rule_ids:
                errors.append(f"{context} references unknown rule_id '{rule_id}'.")
                continue
            mapping_key = (error_group, class_name, paired_class, rule_id)
            if mapping_key in seen_mappings:
                errors.append(f"Duplicate mapping to rule_id '{rule_id}' at {context}.")
                continue
            seen_mappings.add(mapping_key)
            rule_ids.append(rule_id)

        mappings.append(
            {
                "error_group": error_group,
                "class_name": class_name,
                "paired_class": paired_class,
                "rule_ids": rule_ids,
            }
        )

    if errors:
        raise GuidelineMappingValidationError(errors)
    return version_tag, name, rules, mappings


class Command(BaseCommand):
    help = "Nạp guideline từ tệp YAML (idempotent theo SHA-256)"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("file", type=str, help="Đường dẫn tệp YAML guideline")
        parser.add_argument("--actor", required=True, help="Username người thực hiện lần nạp")

    def handle(self, *args: Any, **options: Any) -> None:
        file_path = Path(options["file"])
        if not file_path.is_file():
            raise CommandError(f"File not found: {file_path}")

        raw = file_path.read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        row_count = len(raw.splitlines())
        actor_username = str(options["actor"]).strip()
        actor = get_user_model().objects.filter(username=actor_username).first()

        def record(result: str, errors: list[str]) -> None:
            GuidelineLoadRecord.objects.create(
                actor_username=actor_username,
                actor=actor,
                file_checksum=checksum,
                row_count=row_count,
                result=result,
                errors=errors,
            )

        if actor is None:
            record(
                GuidelineLoadRecord.Result.REJECTED,
                [f"Actor '{actor_username}' does not exist."],
            )
            raise CommandError(f"Actor '{actor_username}' does not exist.")

        if not actor.is_active:
            record(
                GuidelineLoadRecord.Result.REJECTED,
                [f"Actor '{actor_username}' is not active."],
            )
            raise CommandError(f"Actor '{actor_username}' is not active.")

        # Chỉ QC_ADMIN hoặc SUPER_ADMIN được cấu hình/nạp guideline (FR-GDL-02, FR-SEC-05)
        has_perm = (
            actor.is_superuser
            or actor.role_assignments.filter(role__in=["qc_admin", "super_admin"]).exists()
        )
        if not has_perm:
            record(
                GuidelineLoadRecord.Result.REJECTED,
                [f"Actor '{actor_username}' lacks permission to load guidelines."],
            )
            raise CommandError(f"Actor '{actor_username}' lacks permission to load guidelines.")

        # Idempotency: cùng checksum → bỏ qua
        if GuidelineVersion.objects.filter(file_checksum=checksum).exists():
            record(GuidelineLoadRecord.Result.SKIPPED, [])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Guideline already loaded (checksum {checksum[:12]}...). Skipping."
                )
            )
            return

        try:
            version_tag, name, rules_data, mappings_data = _parse_guideline(raw)
        except GuidelineMappingValidationError as exc:
            record(GuidelineLoadRecord.Result.REJECTED, exc.errors)
            raise CommandError(str(exc)) from exc
        except CommandError as exc:
            record(GuidelineLoadRecord.Result.REJECTED, [str(exc)])
            raise

        # Chặn ghi đè version_tag đã tồn tại với nội dung khác
        if GuidelineVersion.objects.filter(version_tag=version_tag).exists():
            record(
                GuidelineLoadRecord.Result.REJECTED,
                [f"Version '{version_tag}' already exists with different content."],
            )
            raise CommandError(
                f"Version '{version_tag}' already exists with different content. "
                "Use a new version_tag or verify the file."
            )

        try:
            with transaction.atomic():
                gv = GuidelineVersion.objects.create(
                    version_tag=version_tag,
                    name=name,
                    file_checksum=checksum,
                )

                rule_map: dict[str, GuidelineRule] = {}
                for r in rules_data:
                    rule_obj = GuidelineRule.objects.create(
                        version=gv,
                        rule_id=r["id"],
                        section=r["section"],
                        content=r["content"],
                    )
                    rule_map[r["id"]] = rule_obj

                for m in mappings_data:
                    for rid in m["rule_ids"]:
                        RuleMapping.objects.create(
                            version=gv,
                            error_group=m["error_group"],
                            class_name=m["class_name"],
                            paired_class=m["paired_class"],
                            rule=rule_map[rid],
                        )
        except Exception as exc:
            record(
                GuidelineLoadRecord.Result.REJECTED,
                [f"Database error during load: {exc}"],
            )
            raise CommandError(f"Database error during load: {exc}") from exc

        record(GuidelineLoadRecord.Result.ACCEPTED, [])

        rule_count = len(rules_data)
        mapping_count = len(mappings_data)
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded guideline '{name}' ({version_tag}): "
                f"{rule_count} rules, {mapping_count} mapping groups."
            )
        )
