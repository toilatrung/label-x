"""Shared, audited YAML import for CLI and API."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, cast

import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.db import transaction

from guideline.models import GuidelineLoadRecord, GuidelineRule, GuidelineVersion, RuleMapping
from guideline.taxonomy import parse_taxonomy

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


def _parse_guideline(
    raw: bytes,
    *,
    manual_taxonomy: dict[str, Any] | None = None,
    require_taxonomy: bool = False,
    validate_classes: bool = True,
) -> tuple[str, str, list[dict[str, str]], list[dict[str, Any]]]:
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
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
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

    taxonomy = parse_taxonomy(raw, known_rule_ids, manual_taxonomy)
    if require_taxonomy and not taxonomy:
        raise CommandError("Guideline không có taxonomy. Nhập taxonomy trước khi import.")
    validate_classes = validate_classes or bool(taxonomy)
    taxonomy_name = "guideline" if taxonomy else "BDD100K"
    valid_classes = {label["name"] for label in taxonomy["labels"]} if taxonomy else BDD100K_CLASSES

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
        if validate_classes and class_name and class_name not in valid_classes:
            errors.append(
                f"{context}.class_name '{class_name}' is outside {taxonomy_name} taxonomy."
            )
        if validate_classes and paired_class and paired_class not in valid_classes:
            errors.append(
                f"{context}.paired_class '{paired_class}' is outside {taxonomy_name} taxonomy."
            )

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


def load_guideline(
    raw: bytes,
    actor_username: str,
    on_loaded: Callable[[GuidelineVersion, bool], None] | None = None,
    *,
    manual_taxonomy: dict[str, Any] | None = None,
    require_taxonomy: bool = False,
) -> tuple[GuidelineVersion, bool]:
    checksum = hashlib.sha256(raw).hexdigest()
    if manual_taxonomy is not None:
        # Include both sources so changed manual policy cannot replay a file-only checksum.
        effective = json.dumps(
            {"file_sha256": checksum, "taxonomy": manual_taxonomy},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        checksum = hashlib.sha256(effective.encode("utf-8")).hexdigest()
    row_count = len(raw.splitlines())
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
        or getattr(  # noqa: B009
            actor, "role_assignments"
        )
        .filter(role__in=["qc_admin", "super_admin"])
        .exists()
    )
    if not has_perm:
        record(
            GuidelineLoadRecord.Result.REJECTED,
            [f"Actor '{actor_username}' lacks permission to load guidelines."],
        )
        raise CommandError(f"Actor '{actor_username}' lacks permission to load guidelines.")

    # Idempotency: cùng checksum → bỏ qua
    if GuidelineVersion.objects.filter(file_checksum=checksum).exists():
        version = GuidelineVersion.objects.get(file_checksum=checksum)
        if require_taxonomy and not version.taxonomy:
            message = "Guideline đã import chưa có taxonomy. Nhập taxonomy để tạo phiên bản đầy đủ."
            record(GuidelineLoadRecord.Result.REJECTED, [message])
            raise CommandError(message)
        with transaction.atomic():
            record(GuidelineLoadRecord.Result.SKIPPED, [])
            if on_loaded:
                on_loaded(version, True)
        return version, True

    try:
        version_tag, name, rules_data, mappings_data = _parse_guideline(
            raw, manual_taxonomy=manual_taxonomy, require_taxonomy=require_taxonomy
        )
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
                taxonomy=parse_taxonomy(raw, {r["id"] for r in rules_data}, manual_taxonomy),
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
            record(GuidelineLoadRecord.Result.ACCEPTED, [])
            if on_loaded:
                on_loaded(gv, False)
    except Exception as exc:
        record(
            GuidelineLoadRecord.Result.REJECTED,
            [f"Database error during load: {exc}"],
        )
        raise CommandError(f"Database error during load: {exc}") from exc

    return gv, False


def preview_guideline(raw: bytes) -> dict[str, Any]:
    version, name, rules, _ = _parse_guideline(raw, validate_classes=False)
    taxonomy = parse_taxonomy(raw, {rule["id"] for rule in rules})
    return {
        "version": version,
        "name": name,
        "rules": [{"rule_id": rule["id"], "section": rule["section"]} for rule in rules],
        "taxonomy": taxonomy or None,
    }
