"""Versioned QC configuration lifecycle with audit and idempotency."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils import timezone

from audit.services import append_audit_event
from runs.models import ConfigVersion
from runs.services import (
    ConfigVersionNotFoundError,
    IdempotencyKeyReusedError,
    InvalidTransitionError,
)


def create_config_version(
    *,
    name: str,
    engines: dict[str, Any],
    thresholds: dict[str, Any],
    models: dict[str, Any],
    created_by: User,
    idempotency_key: str,
) -> ConfigVersion:
    """Create a draft, replaying a matching idempotent request."""
    payload = {"name": name, "engines": engines, "thresholds": thresholds, "models": models}
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
            config = ConfigVersion.objects.create(
                name=name,
                engines=engines,
                thresholds=thresholds,
                models=models,
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
