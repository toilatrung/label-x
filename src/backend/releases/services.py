from __future__ import annotations

import hashlib
import json
from typing import cast

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.request import Request

from accounts.permissions import append_action_audit, check_separation_of_duties
from config.exceptions import ApiError
from releases.models import Release
from reports.models import ReportExport


def build_manifest(release: Release) -> dict[str, object]:
    artifacts: list[dict[str, object]] = []
    snapshot_hash = release.snapshot.revision_sha256
    if snapshot_hash:
        snapshot_bytes = json.dumps(
            release.snapshot.normalized_json,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        artifacts.append(
            {"name": "snapshot", "sha256": snapshot_hash, "size_bytes": len(snapshot_bytes)}
        )
    if release.run.model_artifact_id is not None:
        artifact = release.run.model_artifact
        assert artifact is not None
        artifacts.append(
            {
                "name": f"model:{artifact.name}:{artifact.version}",
                "sha256": artifact.checksum,
                "size_bytes": 0,
            }
        )
    for export in ReportExport.objects.filter(
        run=release.run, status=ReportExport.Status.COMPLETED
    ).order_by("format", "pk"):
        if export.sha256 and export.size_bytes is not None:
            artifacts.append(
                {
                    "name": f"report.{export.format}",
                    "sha256": export.sha256,
                    "size_bytes": export.size_bytes,
                }
            )
    artifacts.sort(key=lambda item: str(item["name"]))
    body: dict[str, object] = {
        "release_id": release.pk,
        "generated_at": release.created_at,
        "snapshot_id": release.snapshot_id,
        "run_id": release.run_id,
        "config_version_id": release.config_version_id,
        "guideline_version": release.snapshot.guideline_version or None,
        "score_version": release.run.score_version or None,
        "gate": release.gate,
        "artifacts": artifacts,
    }
    digest_body = dict(body)
    digest_body["generated_at"] = release.created_at.isoformat()
    body["checksum"] = hashlib.sha256(
        json.dumps(digest_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return body


def approve_release(
    *, release_id: int, request: Request, idempotency_key: str, note: str
) -> Release:
    with transaction.atomic():
        release = (
            Release.objects.select_for_update()
            .select_related("created_by")
            .filter(pk=release_id)
            .first()
        )
        if release is None:
            raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Release không tồn tại.")
        if release.status == Release.Status.APPROVED:
            raise ApiError(
                status.HTTP_409_CONFLICT, "INVALID_TRANSITION", "Release đã được phê duyệt."
            )
        key_owner = Release.objects.filter(approval_idempotency_key=idempotency_key).exclude(
            pk=release.pk
        )
        if key_owner.exists():
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_KEY_REUSED",
                "Idempotency-Key đã được dùng cho release khác.",
            )
        check_separation_of_duties(
            request=request,
            requester_user_id=release.created_by_id,
            action="release.approve",
            object_type="release",
            object_id=release.pk,
        )
        if release.gate_status != Release.GateStatus.PASSED and release.approved_waiver_id is None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "BUSINESS_RULE_UNMET",
                "Quality gate chưa passed và release không có waiver đã duyệt.",
            )
        before = {
            "status": release.status,
            "approved_by": release.approved_by_id,
            "approved_at": None,
        }
        now = timezone.now()
        release.status = Release.Status.APPROVED
        release.approved_by = cast(User, request.user)
        release.approved_at = now
        release.approval_idempotency_key = idempotency_key
        release.approval_note = note
        release.save(
            update_fields=[
                "status",
                "approved_by",
                "approved_at",
                "approval_idempotency_key",
                "approval_note",
            ]
        )
        append_action_audit(
            request=request,
            action="release.approve",
            object_type="release",
            object_id=release.pk,
            before=before,
            after={
                "status": release.status,
                "approved_by": release.approved_by_id,
                "approved_at": now.isoformat(),
                "gate_status": release.gate_status,
                "waiver_id": release.approved_waiver_id,
            },
            reason=note,
            revision=idempotency_key,
        )
        return release
