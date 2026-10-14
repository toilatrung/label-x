"""Validate guideline policy and bind its names to a read-only CVAT label schema."""

from __future__ import annotations

from typing import Any, cast

import yaml
from django.core.management.base import CommandError

from guideline.models import DatasetGuideline, GuidelineVersion
from snapshots.normalization import sha256_json


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CommandError(f"{field} must be a non-empty string")
    return value.strip()


def parse_taxonomy(
    raw: bytes, rule_ids: set[str], manual_taxonomy: dict[str, Any] | None = None
) -> dict[str, Any]:
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as exc:
        raise CommandError("Invalid UTF-8 YAML") from exc
    if not isinstance(data, dict):
        raise CommandError("YAML root must be a mapping")
    data = data.get("guideline", data)
    if not isinstance(data, dict):
        raise CommandError("guideline must be a mapping")
    has_embedded = data.get("taxonomy") not in (None, {})
    if has_embedded and manual_taxonomy is not None:
        raise CommandError("Guideline đã có taxonomy; không được thay bằng taxonomy nhập tay.")
    if not has_embedded and manual_taxonomy is None:
        return {}  # Legacy CLI imports remain available for lookup.
    taxonomy = data["taxonomy"] if has_embedded else manual_taxonomy
    if not isinstance(taxonomy, dict):
        raise CommandError("taxonomy must be an object")
    version = _text(taxonomy.get("version"), "taxonomy.version")
    labels = taxonomy.get("labels")
    if not isinstance(labels, list) or not labels:
        raise CommandError("taxonomy.labels must be a non-empty list")
    parsed: list[dict[str, Any]] = []
    names = set()
    for label in labels:
        if not isinstance(label, dict):
            raise CommandError("taxonomy label must be an object")
        name = _text(label.get("name"), "label.name")
        if name in names:
            raise CommandError(f"Duplicate taxonomy label: {name}")
        names.add(name)
        attrs = label.get("required_attributes", [])
        if not isinstance(attrs, list):
            raise CommandError("required_attributes must be a list")
        requirements: list[dict[str, Any]] = []
        attr_names, used_rules = set(), set()
        for attr in attrs:
            if not isinstance(attr, dict):
                raise CommandError("Required attribute must be an object")
            attr_name = _text(attr.get("name"), "attribute.name")
            rule_id = _text(attr.get("rule_id"), "attribute.rule_id")
            if rule_id not in rule_ids:
                raise CommandError(f"Unknown attribute rule_id: {rule_id}")
            if attr_name in attr_names or rule_id in used_rules:
                raise CommandError(f"Duplicate attribute name or rule_id for {name}")
            attr_names.add(attr_name)
            used_rules.add(rule_id)
            values = attr.get("allowed_values", [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                raise CommandError("allowed_values must be a list of non-empty strings")
            if len(values) != len(set(values)):
                raise CommandError("Duplicate allowed_values")
            requirements.append(
                {"name": attr_name, "rule_id": rule_id, "allowed_values": sorted(values)}
            )
        parsed.append(
            {"name": name, "required_attributes": sorted(requirements, key=lambda a: a["name"])}
        )
    return {"version": version, "labels": sorted(parsed, key=lambda label: label["name"])}


class GuidelineBindingError(ValueError):
    """Dataset policy is missing or cannot be mapped without guessing."""


def _id(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GuidelineBindingError(f"CVAT {field} must be a positive integer")
    return cast(int, value)


def bind_taxonomy(
    dataset_id: int, labels: list[dict[str, Any]], *, guideline_version: str | None = None
) -> dict[str, Any]:
    if guideline_version is None:
        binding = (
            DatasetGuideline.objects.select_related("guideline")
            .filter(dataset_id=dataset_id)
            .first()
        )
        if binding is None:
            raise GuidelineBindingError(
                "Dataset chưa được gắn Guideline. Cấu hình Guideline trước khi tạo Snapshot."
            )
        guideline = binding.guideline
    else:
        selected = GuidelineVersion.objects.filter(version_tag=guideline_version).first()
        if selected is None:
            raise GuidelineBindingError("Guideline đã chọn không tồn tại.")
        guideline = selected
    if not guideline.taxonomy:
        raise GuidelineBindingError(
            "Guideline chưa có taxonomy. Import phiên bản mới có taxonomy trước khi tạo Snapshot."
        )
    by_name = {}
    label_ids = set()
    for label in labels:
        name = label.get("name")
        label_id = _id(label.get("id"), "label.id")
        if not isinstance(name, str) or not name or name in by_name or label_id in label_ids:
            raise GuidelineBindingError(
                "CVAT có tên hoặc ID lớp thiếu/trùng; không thể ánh xạ taxonomy."
            )
        by_name[name] = label
        label_ids.add(label_id)
    mapped = []
    for label in guideline.taxonomy["labels"]:
        source = by_name.get(label["name"])
        if source is None:
            raise GuidelineBindingError(f"CVAT thiếu lớp trong Guideline: {label['name']}")
        source_attrs = source.get("attributes", [])
        if not isinstance(source_attrs, list):
            raise GuidelineBindingError("CVAT attributes must be a list")
        attrs = {}
        attr_ids = set()
        for attr in source_attrs:
            if not isinstance(attr, dict):
                raise GuidelineBindingError("CVAT attribute must be an object")
            attr_id = _id(attr.get("id"), "attribute.id")
            name = attr.get("name")
            if not isinstance(name, str) or not name or name in attrs or attr_id in attr_ids:
                raise GuidelineBindingError("CVAT có tên hoặc ID thuộc tính thiếu/trùng.")
            attrs[name] = attr
            attr_ids.add(attr_id)
        requirements: list[dict[str, Any]] = []
        for requirement in label["required_attributes"]:
            attr = attrs.get(requirement["name"])
            if attr is None:
                raise GuidelineBindingError(
                    f"CVAT thiếu thuộc tính {label['name']}.{requirement['name']}"
                )
            values = attr.get("values", [])
            if attr.get("input_type") in ("select", "radio", "checkbox"):
                if not isinstance(values, list) or not set(requirement["allowed_values"]).issubset(
                    values
                ):
                    raise GuidelineBindingError(
                        f"Giá trị CVAT không tương thích: {label['name']}.{requirement['name']}"
                    )
            requirements.append({**requirement, "spec_id": attr["id"]})
        mapped.append(
            {"label_id": source["id"], "name": label["name"], "required_attributes": requirements}
        )
    source_hash = sha256_json(sorted(labels, key=lambda label: str(label["id"])))
    context = {
        "guideline_version": guideline.version_tag,
        "guideline_checksum": guideline.file_checksum,
        "taxonomy_definition": guideline.taxonomy,
        "cvat_labels_sha256": source_hash,
        "labels": mapped,
    }
    version = f"guideline-taxonomy:{sha256_json(context)}"
    return {**context, "taxonomy": {"version": version, "labels": mapped}}
