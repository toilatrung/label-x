"""DEMO-ONLY read model for M-DEMO01 run frames.

This module intentionally does not persist ranking rows.  It projects the immutable
snapshot and candidate records through ``score_v0`` every time the demo endpoint is read.
"""

from __future__ import annotations

import base64
import binascii
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from django.conf import settings

from cvat_adapter.client import build_job_url
from orchestration.models import CandidateRecord
from ranking.score_v0 import SCORE_V0, FrameInput, RankedFrame, rank_frames
from runs.models import EngineResult, QCRun
from snapshots.models import SnapshotFrame

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
_SCOREABLE_FAMILIES = frozenset({"E1", "E2", "E3"})


def build_demo_frame_page(
    run: QCRun, *, cursor: str | None = None, page_size: int = DEFAULT_PAGE_SIZE
) -> dict[str, Any]:
    """Build one deterministic page matching ``demo-review-contract.html``."""

    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    offset = _decode_cursor(cursor)

    frames = list(
        SnapshotFrame.objects.filter(snapshot_job__snapshot_id=run.snapshot_id)
        .select_related("snapshot_job")
        .order_by("snapshot_job__cvat_task_id", "frame_index", "id")
    )
    candidates = list(CandidateRecord.objects.filter(run_id=run.pk).order_by("id"))
    candidates_by_key: dict[str, list[CandidateRecord]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_key[_frame_key(candidate.cvat_task_id, candidate.frame_number)].append(
            candidate
        )

    ranked, _ranking_hash = rank_frames(
        [_frame_input(frame) for frame in frames],
        [_score_candidate(candidate) for candidate in candidates if _is_scoreable(candidate)],
        seed=run.seed,
    )
    frames_by_key = {_snapshot_frame_key(frame): frame for frame in frames}
    ordered_rows = [
        _frame_row(
            run,
            frames_by_key[item.frame_key],
            item,
            candidates_by_key[item.frame_key],
        )
        for item in ranked
    ]

    page = ordered_rows[offset : offset + page_size]
    next_offset = offset + len(page)
    next_cursor = _encode_cursor(next_offset) if next_offset < len(ordered_rows) else None
    return {
        "run_id": run.pk,
        "snapshot_id": run.snapshot_id,
        "score_version": SCORE_V0,
        "next": next_cursor,
        "items": page,
        "engines": [_engine_row(result) for result in run.engine_results.order_by("engine")],
    }


def parse_page_size(raw: str | None) -> int:
    if raw is None or raw == "":
        return DEFAULT_PAGE_SIZE
    try:
        page_size = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("page_size must be an integer") from exc
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    return page_size


def _frame_input(frame: SnapshotFrame) -> FrameInput:
    return FrameInput(
        cvat_task_id=frame.snapshot_job.cvat_task_id,
        frame_number=frame.frame_index,
        annotation_count=frame.rectangle_count,
    )


def _is_scoreable(candidate: CandidateRecord) -> bool:
    # Structural candidates remain visible but score_v0 deliberately only counts E1/E2/E3.
    return candidate.family in _SCOREABLE_FAMILIES


def _score_candidate(candidate: CandidateRecord) -> dict[str, object]:
    return {
        "family": candidate.family,
        "frame": {
            "cvat_task_id": candidate.cvat_task_id,
            "frame_number": candidate.frame_number,
        },
        "anchor": candidate.anchor,
        "evidence": candidate.evidence,
    }


def _frame_row(
    run: QCRun,
    frame: SnapshotFrame,
    ranked: RankedFrame,
    candidates: Sequence[CandidateRecord],
) -> dict[str, Any]:
    job = frame.snapshot_job
    return {
        "frame_id": frame.pk,
        "rank": ranked.rank,
        "score": float(ranked.score),
        "file_name": frame.file_name,
        "width": frame.width,
        "height": frame.height,
        "image_url": f"/api/runs/{run.pk}/frames/{frame.pk}/image/",
        "cvat": {
            "task_id": job.cvat_task_id,
            "job_id": job.cvat_job_id,
            "frame": frame.frame_index,
            "deep_link": build_job_url(
                settings.CVAT_BASE_URL,
                job.cvat_task_id,
                job.cvat_job_id,
                frame_index=frame.frame_index,
            ),
        },
        "shapes": [_shape_row(shape) for shape in frame.shapes if isinstance(shape, Mapping)],
        "candidates": [_candidate_row(candidate) for candidate in candidates],
    }


def _shape_row(shape: Mapping[str, object]) -> dict[str, object]:
    source = shape.get("source")
    source_id = source.get("id") if isinstance(source, Mapping) else None
    label = shape.get("label") or shape.get("label_name")
    if label is None:
        label_id = shape.get("label_id")
        label = f"label:{label_id}" if label_id is not None else "unknown"
    points = shape.get("points")
    bbox = list(points[:4]) if isinstance(points, list) and len(points) >= 4 else []
    return {
        "id": str(source_id if source_id is not None else "unknown"),
        "label": str(label),
        "bbox": bbox,
    }


def _candidate_row(candidate: CandidateRecord) -> dict[str, object]:
    anchor = candidate.anchor if isinstance(candidate.anchor, Mapping) else {}
    evidence = candidate.evidence if isinstance(candidate.evidence, Mapping) else {}
    raw_objects = anchor.get("objects", [])
    objects = raw_objects if isinstance(raw_objects, list) else []
    shape_ids = [str(item["id"]) for item in objects if isinstance(item, Mapping) and "id" in item]
    rule_id = anchor.get("rule_id") or evidence.get("rule_id") or "DEMO-ONLY"
    severity = evidence.get("severity")
    if not isinstance(severity, str):
        severity = "high" if candidate.family in _SCOREABLE_FAMILIES else "medium"
    return {
        "id": str(candidate.pk),
        "engine": candidate.engine,
        "rule_id": str(rule_id),
        "family": candidate.family,
        "severity": severity,
        "shape_ids": shape_ids,
        "message": _candidate_message(candidate, evidence),
        "evidence": dict(evidence),
    }


def _candidate_message(candidate: CandidateRecord, evidence: Mapping[str, object]) -> str:
    message = evidence.get("message")
    if isinstance(message, str) and message.strip():
        return message
    expected, actual = evidence.get("expected"), evidence.get("actual")
    if expected is not None or actual is not None:
        return f"expected={expected!s}; actual={actual!s}"
    if "iou" in evidence:
        return f"IoU {evidence['iou']} ({candidate.family})"
    return f"{candidate.engine}: {candidate.family}"


def _engine_row(result: EngineResult) -> dict[str, str]:
    if result.status in {"completed", "checked"}:
        display_status = "checked"
    elif result.status == "failed":
        display_status = "failed"
    else:
        display_status = "not_checked"
    return {"engine": result.engine, "status": display_status}


def _snapshot_frame_key(frame: SnapshotFrame) -> str:
    return _frame_key(frame.snapshot_job.cvat_task_id, frame.frame_index)


def _frame_key(cvat_task_id: int, frame_number: int) -> str:
    return f"{cvat_task_id}:{frame_number}"


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(cursor + padding).decode()
        offset = int(decoded)
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise ValueError("cursor is invalid") from exc
    if offset < 0:
        raise ValueError("cursor is invalid")
    return offset
