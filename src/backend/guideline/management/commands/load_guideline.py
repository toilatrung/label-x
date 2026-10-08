"""Nạp guideline từ tệp YAML vào database.

Idempotent: tệp có cùng nội dung (SHA-256) sẽ bị bỏ qua.
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


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CommandError(f"{context} must be a YAML object.")
    return cast(dict[str, Any], value)


def _required_text(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CommandError(f"{context}.{key} must be a non-empty string.")
    return value.strip()


def _optional_text(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key, "")
    if not isinstance(value, str):
        raise CommandError(f"{context}.{key} must be a string.")
    return value.strip()


def _parse_guideline(raw: bytes) -> tuple[str, str, list[dict[str, str]], list[dict[str, Any]]]:
    """Parse và kiểm tra schema tối thiểu của tệp guideline pilot."""

    try:
        loaded = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise CommandError(f"Guideline file must be valid UTF-8 YAML: {exc}") from exc

    data = _mapping(loaded, "Tệp guideline")
    version_tag = _required_text(data, "version", "Tệp guideline")
    name = _required_text(data, "name", "Tệp guideline")

    raw_rules = data.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise CommandError("guideline.rules must be a non-empty list.")

    rules: list[dict[str, str]] = []
    known_rule_ids: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        context = f"rules[{index}]"
        rule = _mapping(raw_rule, context)
        rule_id = _required_text(rule, "id", context)
        if rule_id in known_rule_ids:
            raise CommandError(f"Duplicate rule ID '{rule_id}' in guideline file.")
        known_rule_ids.add(rule_id)
        rules.append(
            {
                "id": rule_id,
                "section": _required_text(rule, "section", context),
                "content": _required_text(rule, "content", context),
            }
        )

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
            raise CommandError(f"{context}.rule_ids must be a non-empty list.")

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
        raise CommandError("Invalid guideline mappings: " + " ".join(errors))
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

        with transaction.atomic():
            version = GuidelineVersion.objects.create(
                version_tag=version_tag,
                name=name,
                file_checksum=checksum,
            )

            # Tạo dict rule_id → GuidelineRule để mapping tham chiếu
            rule_map: dict[str, GuidelineRule] = {}
            for rule_data in rules_data:
                rule = GuidelineRule.objects.create(
                    version=version,
                    rule_id=rule_data["id"],
                    section=rule_data["section"],
                    content=rule_data["content"].strip(),
                )
                rule_map[rule.rule_id] = rule

            # Tạo mappings
            for mapping_data in mappings_data:
                error_group = cast(str, mapping_data["error_group"])
                class_name = cast(str, mapping_data["class_name"])
                paired_class = cast(str, mapping_data["paired_class"])
                rule_ids = cast(list[str], mapping_data["rule_ids"])

                for rid in rule_ids:
                    RuleMapping.objects.create(
                        version=version,
                        error_group=error_group,
                        class_name=class_name,
                        paired_class=paired_class,
                        rule=rule_map[rid],
                    )

            record(GuidelineLoadRecord.Result.ACCEPTED, [])

        rule_count = len(rules_data)
        mapping_count = len(mappings_data)
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded guideline '{name}' ({version_tag}): "
                f"{rule_count} rules, {mapping_count} mapping groups."
            )
        )
