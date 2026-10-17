"""Domain services for Calibration & Audit Sampling (MBE-04)."""

from __future__ import annotations

import hashlib
import json
import random
import secrets
from collections.abc import Mapping, Sequence
from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from rest_framework import status

from accounts.models import Role, RoleAssignment
from audit.services import append_audit_event
from calibration.models import (
    AssignmentStatus,
    AuditSample,
    AuditSampleFrame,
    AuditSampleStream,
    Benchmark,
    BenchmarkFrame,
    BenchmarkSource,
    BenchmarkStatus,
    CalibrationAssignment,
    TargetKind,
)
from config.exceptions import ApiError
from orchestration.models import Evaluation, VlmUnit
from review.models import FrameReview
from runs.models import ModelArtifact, QCRun, RunRanking, RunRankingEntry
from snapshots.models import Snapshot, SnapshotFrame

UserModel = get_user_model()


def canonical_hash(data: Mapping[str, Any]) -> str:
    """Canonical SHA-256 hash for idempotency checking."""
    raw = json.dumps(dict(data), sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sample_audit(
    *,
    run_id: int,
    stream: str,
    size: int,
    seed: int | None = None,
    created_by: User,
    idempotency_key: str | None = None,
    raw_payload: Mapping[str, Any] | None = None,
) -> AuditSample:
    """Tạo mẫu kiểm định (audit sample) theo stream random hoặc risk.

    - run chưa hoàn tất hoặc dữ liệu không đủ cỡ mẫu -> trả 422 INSUFFICIENT_SAMPLE.
    - seed được lưu lại; bỏ trống thì server sinh và lưu lại.
    - Cùng seed + run + stream + size cho cùng kết quả (idempotent).
    - Idempotency-Key được kiểm tra bảo vệ xung đột 409.
    """
    clean_key = (idempotency_key or "").strip()
    req_sha256 = canonical_hash(
        raw_payload or {"run_id": run_id, "stream": stream, "size": size, "seed": seed}
    )

    if clean_key:
        existing_key = AuditSample.objects.filter(idempotency_key=clean_key).first()
        if existing_key is not None:
            if existing_key.request_sha256 == req_sha256:
                return existing_key
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_KEY_REUSED",
                f"Idempotency-Key '{clean_key}' đã được sử dụng với payload khác.",
            )

    run = QCRun.objects.filter(pk=run_id).first()
    if run is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Run {run_id} không tồn tại.")

    if run.status != QCRun.Status.COMPLETED:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INSUFFICIENT_SAMPLE",
            f"Run {run_id} chưa hoàn tất (hiện tại: {run.status}).",
        )

    if size <= 0:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "Cỡ mẫu size phải lớn hơn 0.",
        )

    # Server generates seed if omitted
    if seed is None:
        seed = secrets.randbelow(2147483647) + 1

    # Check natural idempotency: cùng seed + run + stream + size
    existing = (
        AuditSample.objects.filter(run=run, stream=stream, seed=seed, size=size)
        .prefetch_related("sample_frames__snapshot_frame__snapshot_job")
        .first()
    )
    if existing is not None:
        return existing

    # Collect frames from run snapshot
    frames = list(
        SnapshotFrame.objects.filter(snapshot_job__snapshot=run.snapshot)
        .select_related("snapshot_job")
        .order_by("snapshot_job__cvat_task_id", "frame_index", "id")
    )
    total_frames = len(frames)
    if total_frames < size:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "INSUFFICIENT_SAMPLE",
            f"Dữ liệu không đủ cỡ mẫu yêu cầu (yêu cầu {size}, hiện có {total_frames}).",
        )

    # Sampling logic
    frame_reviews_map = {
        fr.snapshot_frame_id: fr.state
        for fr in FrameReview.objects.filter(run=run, snapshot_frame__in=frames)
    }

    ranking_ranks_map: dict[int, int] = {}
    if stream == AuditSampleStream.RISK:
        # Lấy từ ranking nếu có
        risk_ranking = RunRanking.objects.filter(run=run, source=RunRanking.Source.RISK).first()
        if risk_ranking is not None:
            entries = list(
                RunRankingEntry.objects.filter(ranking=risk_ranking).order_by("rank")[:size]
            )
            ranking_ranks_map = {e.snapshot_frame_id: e.rank for e in entries}

    if stream == AuditSampleStream.RISK and ranking_ranks_map:
        frame_by_id = {f.id: f for f in frames}
        sampled_frames = [frame_by_id[fid] for fid in ranking_ranks_map if fid in frame_by_id]
        # Nếu chưa đủ size do ranking ngắn, lấy thêm dùng seed
        if len(sampled_frames) < size:
            remaining = [f for f in frames if f.id not in ranking_ranks_map]
            rng = random.Random(seed)  # noqa: S311
            needed = size - len(sampled_frames)
            sampled_frames.extend(rng.sample(remaining, min(needed, len(remaining))))
    else:
        rng = random.Random(seed)  # noqa: S311
        sampled_frames = rng.sample(frames, size)

    with transaction.atomic():
        sample = AuditSample.objects.create(
            run=run,
            stream=stream,
            seed=seed,
            size=size,
            frame_count=len(sampled_frames),
            created_by=created_by,
            idempotency_key=clean_key,
            request_sha256=req_sha256,
        )

        sample_frames: list[AuditSampleFrame] = []
        for idx, frame in enumerate(sampled_frames, start=1):
            rank_val = ranking_ranks_map.get(
                frame.id, idx if stream == AuditSampleStream.RISK else None
            )
            review_state = frame_reviews_map.get(frame.id, FrameReview.State.UNREVIEWED)
            sample_frames.append(
                AuditSampleFrame(
                    audit_sample=sample,
                    snapshot_frame=frame,
                    rank=rank_val,
                    review_state=review_state,
                )
            )

        AuditSampleFrame.objects.bulk_create(sample_frames)

        append_audit_event(
            actor=created_by,
            action="audit_sample.create",
            object_type="audit_sample",
            object_id=str(sample.pk),
            before=None,
            after={
                "run_id": run_id,
                "stream": stream,
                "seed": seed,
                "size": size,
                "frame_count": sample.frame_count,
            },
            revision=str(sample.pk),
        )

    return sample


def create_benchmark(
    *,
    name: str,
    dataset_id: int,
    snapshot_id: int,
    frame_ids: Sequence[int],
    created_by: User,
    idempotency_key: str | None = None,
    raw_payload: Mapping[str, Any] | None = None,
) -> Benchmark:
    """Tạo benchmark từ frame của snapshot."""
    clean_key = (idempotency_key or "").strip()
    req_sha256 = canonical_hash(
        raw_payload
        or {
            "name": name,
            "dataset_id": dataset_id,
            "snapshot_id": snapshot_id,
            "frame_ids": list(frame_ids),
        }
    )

    if clean_key:
        existing_key = Benchmark.objects.filter(idempotency_key=clean_key).first()
        if existing_key is not None:
            if existing_key.request_sha256 == req_sha256:
                return existing_key
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_KEY_REUSED",
                f"Idempotency-Key '{clean_key}' đã được sử dụng với payload khác.",
            )

    snapshot = Snapshot.objects.filter(pk=snapshot_id).first()
    if snapshot is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Snapshot {snapshot_id} không tồn tại."
        )

    if snapshot.dataset_id != dataset_id:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            f"Snapshot {snapshot_id} thuộc dataset {snapshot.dataset_id}, "
            f"không khớp dataset {dataset_id}.",
        )

    unique_frame_ids = list(dict.fromkeys(frame_ids))
    if not unique_frame_ids:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "VALIDATION_ERROR",
            "Danh sách frame_ids không được rỗng.",
        )

    valid_frames = list(
        SnapshotFrame.objects.filter(snapshot_job__snapshot=snapshot, pk__in=unique_frame_ids)
    )
    if len(valid_frames) != len(unique_frame_ids):
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "Một số frame_ids không tồn tại trong snapshot được chọn.",
        )

    with transaction.atomic():
        benchmark = Benchmark.objects.create(
            name=name,
            dataset_id=dataset_id,
            snapshot=snapshot,
            source=BenchmarkSource.MANUAL,
            status=BenchmarkStatus.READY,
            frame_count=len(valid_frames),
            created_by=created_by,
            idempotency_key=clean_key,
            request_sha256=req_sha256,
        )

        benchmark_frames = [
            BenchmarkFrame(benchmark=benchmark, snapshot_frame=vf, frame_id=vf.pk)
            for vf in valid_frames
        ]
        BenchmarkFrame.objects.bulk_create(benchmark_frames)

        append_audit_event(
            actor=created_by,
            action="benchmark.create",
            object_type="benchmark",
            object_id=str(benchmark.pk),
            before=None,
            after={
                "name": name,
                "dataset_id": dataset_id,
                "snapshot_id": snapshot_id,
                "frame_count": benchmark.frame_count,
            },
            revision=str(benchmark.pk),
        )

    return benchmark


def import_cvat_benchmark(
    *,
    name: str,
    dataset_id: int,
    cvat_task_id: int,
    created_by: User,
    idempotency_key: str | None = None,
    raw_payload: Mapping[str, Any] | None = None,
) -> tuple[Benchmark, bool]:
    """Nhập benchmark từ task CVAT (chỉ đọc, idempotent theo (dataset_id, cvat_task_id)).

    Returns:
        (benchmark, is_newly_created)
    """
    clean_key = (idempotency_key or "").strip()
    req_sha256 = canonical_hash(
        raw_payload or {"name": name, "dataset_id": dataset_id, "cvat_task_id": cvat_task_id}
    )

    if clean_key:
        existing_key = Benchmark.objects.filter(idempotency_key=clean_key).first()
        if existing_key is not None:
            if existing_key.request_sha256 == req_sha256:
                return existing_key, False
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_KEY_REUSED",
                f"Idempotency-Key '{clean_key}' đã được sử dụng với payload khác.",
            )

    # Idempotent theo (dataset_id, cvat_task_id)
    existing_cvat = Benchmark.objects.filter(
        dataset_id=dataset_id, cvat_task_id=cvat_task_id
    ).first()
    if existing_cvat is not None:
        return existing_cvat, False

    with transaction.atomic():
        benchmark = Benchmark.objects.create(
            name=name,
            dataset_id=dataset_id,
            snapshot=None,
            source=BenchmarkSource.CVAT_IMPORT,
            cvat_task_id=cvat_task_id,
            status=BenchmarkStatus.PENDING,
            frame_count=0,
            created_by=created_by,
            idempotency_key=clean_key,
            request_sha256=req_sha256,
        )

        append_audit_event(
            actor=created_by,
            action="benchmark.import_cvat",
            object_type="benchmark",
            object_id=str(benchmark.pk),
            before=None,
            after={
                "name": name,
                "dataset_id": dataset_id,
                "cvat_task_id": cvat_task_id,
                "status": benchmark.status,
            },
            revision=str(benchmark.pk),
        )

    return benchmark, True


def create_calibration_assignment(
    *,
    target_kind: str,
    target_id: int,
    audit_sample_id: int,
    note: str = "",
    created_by: User,
    idempotency_key: str | None = None,
    raw_payload: Mapping[str, Any] | None = None,
) -> CalibrationAssignment:
    """Ghi nhận giao mẫu hiệu chỉnh cho reviewer hoặc model."""
    clean_key = (idempotency_key or "").strip()
    req_sha256 = canonical_hash(
        raw_payload
        or {
            "target_kind": target_kind,
            "target_id": target_id,
            "audit_sample_id": audit_sample_id,
            "note": note,
        }
    )

    if clean_key:
        existing_key = CalibrationAssignment.objects.filter(idempotency_key=clean_key).first()
        if existing_key is not None:
            if existing_key.request_sha256 == req_sha256:
                return existing_key
            raise ApiError(
                status.HTTP_409_CONFLICT,
                "IDEMPOTENCY_KEY_REUSED",
                f"Idempotency-Key '{clean_key}' đã được sử dụng với payload khác.",
            )

    audit_sample = AuditSample.objects.filter(pk=audit_sample_id).first()
    if audit_sample is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Audit sample {audit_sample_id} không tồn tại."
        )

    if target_kind == TargetKind.REVIEWER:
        user_exists = UserModel.objects.filter(pk=target_id).exists()
        if not user_exists:
            raise ApiError(
                status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Reviewer user {target_id} không tồn tại."
            )
    elif target_kind == TargetKind.MODEL:
        model_exists = ModelArtifact.objects.filter(pk=target_id).exists()
        if not model_exists:
            raise ApiError(
                status.HTTP_404_NOT_FOUND, "NOT_FOUND", f"Model {target_id} không tồn tại."
            )
    else:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            f"target_kind '{target_kind}' không hợp lệ.",
        )

    with transaction.atomic():
        assignment = CalibrationAssignment.objects.create(
            target_kind=target_kind,
            target_id=target_id,
            audit_sample=audit_sample,
            status=AssignmentStatus.ASSIGNED,
            note=note,
            created_by=created_by,
            idempotency_key=clean_key,
            request_sha256=req_sha256,
        )

        append_audit_event(
            actor=created_by,
            action="calibration.assignment_create",
            object_type="calibration_assignment",
            object_id=str(assignment.pk),
            before=None,
            after={
                "target_kind": target_kind,
                "target_id": target_id,
                "audit_sample_id": audit_sample_id,
                "status": assignment.status,
            },
            revision=str(assignment.pk),
        )

    return assignment


def get_performance_entries(
    *,
    dataset_id: int | None = None,
    run_id: int | None = None,
    allowed_dataset_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Tổng hợp hiệu năng từ các evaluation; chỉ evaluation đã completed.

    Số liệu thiếu mẫu giữ status not_checked, không bịa số.
    """
    # Evaluation completed: không có vlm_unit hoặc vlm_unit đã completed
    eval_qs = (
        Evaluation.objects.filter(
            Q(vlm_unit__isnull=True) | Q(vlm_unit__status=VlmUnit.Status.COMPLETED)
        )
        .select_related("run", "vlm_unit")
        .order_by("-created_at", "-id")
    )

    if run_id is not None:
        eval_qs = eval_qs.filter(run_id=run_id)
    if dataset_id is not None:
        eval_qs = eval_qs.filter(run__dataset_id=dataset_id)
    elif allowed_dataset_ids is not None:
        eval_qs = eval_qs.filter(run__dataset_id__in=allowed_dataset_ids)

    results: list[dict[str, Any]] = []
    for ev in eval_qs:
        metrics = {
            "accuracy": {
                "status": "not_checked",
                "value": None,
                "sample_size": 0,
                "denominator": 0,
                "method": "evaluation_summary",
                "confidence_interval": None,
            },
            "agreement_rate": {
                "status": "not_checked",
                "value": None,
                "sample_size": 0,
                "denominator": 0,
                "method": "evaluation_summary",
                "confidence_interval": None,
            },
        }

        results.append(
            {
                "evaluation_id": ev.pk,
                "run_id": ev.run_id,
                "snapshot_id": ev.run.snapshot_id if ev.run else 0,
                "score_version": ev.run.score_version if ev.run else "v1",
                "created_at": ev.created_at,
                "metrics": metrics,
            }
        )

    return results


def get_calibration_reviewers(
    *,
    dataset_id: int | None = None,
    allowed_dataset_ids: set[int] | None = None,
) -> list[dict[str, Any]]:
    """Danh sách reviewer và độ hiệu chỉnh (ghi nhận và liệt kê; null khi chưa đủ dữ liệu)."""
    # Reviewer users: có role REVIEWER/ANNOTATOR, đã review frame,
    # hoặc có calibration assignment.
    reviewer_role_qs = RoleAssignment.objects.filter(role__in=[Role.REVIEWER, Role.ANNOTATOR])
    if dataset_id is not None:
        reviewer_role_qs = reviewer_role_qs.filter(dataset_id=dataset_id)
    elif allowed_dataset_ids is not None:
        reviewer_role_qs = reviewer_role_qs.filter(dataset_id__in=allowed_dataset_ids)

    reviewer_user_ids = set(reviewer_role_qs.values_list("user_id", flat=True))

    frame_rev_qs = FrameReview.objects.filter(previous_reviewer__isnull=False)
    if dataset_id is not None:
        frame_rev_qs = frame_rev_qs.filter(run__dataset_id=dataset_id)
    elif allowed_dataset_ids is not None:
        frame_rev_qs = frame_rev_qs.filter(run__dataset_id__in=allowed_dataset_ids)
    reviewer_user_ids.update(frame_rev_qs.values_list("previous_reviewer_id", flat=True))

    assignment_targets = CalibrationAssignment.objects.filter(target_kind=TargetKind.REVIEWER)
    if dataset_id is not None:
        assignment_targets = assignment_targets.filter(audit_sample__run__dataset_id=dataset_id)
    elif allowed_dataset_ids is not None:
        assignment_targets = assignment_targets.filter(
            audit_sample__run__dataset_id__in=allowed_dataset_ids
        )
    reviewer_user_ids.update(assignment_targets.values_list("target_id", flat=True))

    users = list(UserModel.objects.filter(pk__in=reviewer_user_ids).order_by("username"))

    results: list[dict[str, Any]] = []
    for u in users:
        reviewed_count = FrameReview.objects.filter(
            previous_reviewer=u, state__in=[FrameReview.State.REVIEWED, FrameReview.State.COMPLETED]
        )
        if dataset_id is not None:
            reviewed_count = reviewed_count.filter(run__dataset_id=dataset_id)
        elif allowed_dataset_ids is not None:
            reviewed_count = reviewed_count.filter(run__dataset_id__in=allowed_dataset_ids)
        frames_done = reviewed_count.count()

        assignments_qs = CalibrationAssignment.objects.filter(
            target_kind=TargetKind.REVIEWER, target_id=u.pk
        )
        assignments_count = assignments_qs.count()
        last_assignment = assignments_qs.order_by("-created_at").first()

        display_name = u.get_full_name() or u.username
        results.append(
            {
                "user_id": u.pk,
                "display_name": display_name,
                "reviewed_frames": frames_done,
                "assignments": assignments_count,
                "agreement_rate": None,  # Không thuật toán chấm điểm; null khi chưa đủ dữ liệu
                "last_calibrated_at": last_assignment.created_at if last_assignment else None,
            }
        )

    return results


def get_calibration_models() -> list[dict[str, Any]]:
    """Danh sách model và độ hiệu chỉnh (ghi nhận và liệt kê; không thuật toán chấm điểm)."""
    models_qs = ModelArtifact.objects.all().order_by("name", "version")
    results: list[dict[str, Any]] = []

    for art in models_qs:
        name_lower = art.name.lower()
        if any(name in name_lower for name in ("vlm", "qwen", "gemini")):
            kind = "vlm"
        elif "detector" in name_lower or "rcnn" in name_lower or "yolo" in name_lower:
            kind = "detector"
        elif "embed" in name_lower:
            kind = "embedding"
        else:
            kind = "other"

        assignments_qs = CalibrationAssignment.objects.filter(
            target_kind=TargetKind.MODEL, target_id=art.pk
        )
        assignments_count = assignments_qs.count()
        last_assignment = assignments_qs.order_by("-created_at").first()

        results.append(
            {
                "model_id": art.pk,
                "name": art.name,
                "version": art.version,
                "kind": kind,
                "assignments": assignments_count,
                "agreement_rate": None,  # null khi chưa đủ dữ liệu
                "last_calibrated_at": last_assignment.created_at if last_assignment else None,
            }
        )

    return results
