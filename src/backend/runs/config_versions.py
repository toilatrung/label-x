"""Versioned QC configuration lifecycle with audit and idempotency."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.services import append_audit_event
from runs.config_guard import validate_config_safety
from runs.models import ConfigVersion
from runs.routing_config import validate_routing_thresholds
from runs.services import (
    BusinessRuleUnmetError,
    ConfigVersionNotFoundError,
    IdempotencyKeyReusedError,
    InvalidTransitionError,
)
from vlm.config import validate_vlm_config


def create_config_version(
    *,
    name: str,
    engines: dict[str, Any],
    thresholds: dict[str, Any],
    models: dict[str, Any],
    created_by: User,
    idempotency_key: str,
    rules: list[dict[str, Any]] | None = None,
    release_thresholds: dict[str, Any] | None = None,
    sampling_policy: dict[str, Any] | None = None,
) -> ConfigVersion:
    """Create a draft, replaying a matching idempotent request."""
    effective_thresholds = dict(thresholds)
    if release_thresholds and "release_thresholds" not in effective_thresholds:
        effective_thresholds["release_thresholds"] = release_thresholds
    if sampling_policy and "sampling_policy" not in effective_thresholds:
        effective_thresholds["sampling_policy"] = sampling_policy

    payload: dict[str, Any] = {
        "name": name,
        "engines": engines,
        "thresholds": effective_thresholds,
        "models": models,
    }
    if rules:
        payload["rules"] = rules
    if release_thresholds:
        payload["release_thresholds"] = release_thresholds
    if sampling_policy:
        payload["sampling_policy"] = sampling_policy

    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = ConfigVersion.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        if existing.request_sha256 != digest or existing.created_by_id != created_by.pk:
            raise IdempotencyKeyReusedError("Idempotency-Key đã được dùng với yêu cầu khác.")
        return existing
    try:
        with transaction.atomic():
            # Resolve the shared connection once; published configurations keep this version.
            if engines.get("vlm", {}).get("enabled"):
                from vlm.connection import current_connection

                shared = current_connection()
                if shared is not None:
                    if "vlm" not in models:
                        models = {
                            **models,
                            "vlm": {
                                **shared.config,
                                "connection_id": shared.pk,
                            },
                        }
                    routing = effective_thresholds.get("classification_routing", {})
                    if isinstance(routing, dict) and "score_threshold" not in routing:
                        effective_thresholds = {
                            **effective_thresholds,
                            "classification_routing": {
                                **routing,
                                "score_threshold": shared.confidence_threshold,
                            },
                        }
                    payload = {**payload, "models": models, "thresholds": effective_thresholds}
            config = ConfigVersion.objects.create(
                name=name,
                engines=engines,
                thresholds=effective_thresholds,
                models=models,
                payload=payload,
                created_by=created_by,
                idempotency_key=idempotency_key,
                request_sha256=digest,
            )
            append_audit_event(
                actor=created_by,
                action="config_version.create",
                object_type="config_version",
                object_id=config.pk,
                before=None,
                after={"name": name, "status": config.status},
                revision=str(config.pk),
            )
            return config
    except IntegrityError as exc:
        existing = ConfigVersion.objects.filter(idempotency_key=idempotency_key).first()
        if (
            existing
            and existing.request_sha256 == digest
            and existing.created_by_id == created_by.pk
        ):
            return existing
        raise IdempotencyKeyReusedError("Idempotency-Key đã được dùng với yêu cầu khác.") from exc


def publish_config_version(*, config_id: int, actor: User) -> ConfigVersion:
    """Publish exactly once and audit the transition atomically."""
    with transaction.atomic():
        config = ConfigVersion.objects.select_for_update().filter(pk=config_id).first()
        if config is None:
            raise ConfigVersionNotFoundError(f"Config version {config_id} không tồn tại.")
        if config.status != ConfigVersion.Status.DRAFT:
            raise InvalidTransitionError("Chỉ config version nháp mới được publish.")
        _assert_publishable_ai_config(config)
        config.status = ConfigVersion.Status.PUBLISHED
        config.published_by = actor
        config.published_at = timezone.now()
        config.save(update_fields=["status", "published_by", "published_at"])
        append_audit_event(
            actor=actor,
            action="config_version.publish",
            object_type="config_version",
            object_id=config.pk,
            before={"status": ConfigVersion.Status.DRAFT},
            after={"status": ConfigVersion.Status.PUBLISHED},
            revision=str(config.pk),
        )
        return config


def _assert_publishable_ai_config(config: ConfigVersion) -> None:
    """Chặn publish khi models.vlm hoặc thresholds.classification_routing sai schema (M04A-01)."""
    errors = validate_routing_thresholds(config.thresholds or {})
    models_cfg = config.models or {}
    errors += validate_config_safety(config.engines or {}, config.thresholds or {}, models_cfg)
    if "vlm" in models_cfg:
        errors += validate_vlm_config(models_cfg["vlm"])
    elif (config.engines or {}).get("vlm", {}).get("enabled"):
        errors.append("Thiết lập kết nối VLM tại Configuration / Models và Guidelines trước.")
    if errors:
        raise BusinessRuleUnmetError(" ".join(errors))
