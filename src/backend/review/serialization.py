"""Read-only representations of T-035 issue and decision records."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.files.storage import storages

from cvat_adapter.client import build_job_url
from engines.interface import (
    UNFINISHED_OUTCOMES,
    EngineInternalState,
    EngineUnitOutcome,
    LedgerCounts,
    NotCheckedReason,
)
from engines.interface import display_status as engine_display_status
from orchestration.models import CandidateRecord, LedgerUnit
from review.models import FrameReview, Issue, ReviewDecision
from runs.models import EngineResult, RunRankingEntry


def review_evidence(raw: Any) -> list[dict[str, Any]]:
    """Adapt detector xyxy evidence to the review API without mutating engine output."""
    rows = raw if isinstance(raw, list) else [raw]
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item = dict(row)
        bbox = item.get("prediction_bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            item["prediction_bbox"] = dict(zip(("x1", "y1", "x2", "y2"), bbox, strict=True))
        result.append(item)
    return result


def decision_record(decision: ReviewDecision) -> dict[str, object]:
    return {
        "id": decision.pk,
        "issue_id": decision.issue_id,
        "actor_user_id": decision.actor_id,
        "actor_role": decision.actor_role,
        "decision": decision.action,
        "revision": decision.revision,
        "reason": decision.reason,
        "rule_ids": decision.rule_ids,
        "reference_version": decision.reference_version,
        "reference_match_status": decision.reference_match_status,
        "reference_error_ids": decision.reference_error_ids,
        "recorded_at": decision.recorded_at.isoformat(),
    }


def decision_response(decision: ReviewDecision) -> dict[str, object]:
    return {
        "id": decision.pk,
        "issue_id": decision.issue_id,
        "action": decision.action,
        "actor_user_id": decision.actor_id,
        "revision": decision.revision,
        "family": decision.issue.family,
        "severity": decision.issue.severity,
        "reason": decision.reason,
        "rule_id": decision.rule_ids[0] if decision.rule_ids else None,
        "created_at": decision.recorded_at.isoformat(),
        "audit_event_id": decision.audit_event_id,
    }


def issue_response(issue: Issue) -> dict[str, object]:
    candidate = issue.candidate if issue.candidate_id else None
    candidate_evidence: Any = candidate.evidence if candidate is not None else None
    if isinstance(candidate_evidence, list):
        evidence = candidate_evidence
    elif isinstance(candidate_evidence, dict):
        evidence = [candidate_evidence]
    else:
        evidence = issue.reviewer_evidence
    return {
        "id": issue.pk,
        "family": issue.family,
        "origin": issue.origin,
        "state": issue.state,
        "anchor": issue.anchor,
        "n_i": issue.n_i,
        "q_i": issue.q_i,
        "severity": issue.severity,
        "rule_ids": issue.rule_ids,
        "evidence": review_evidence(evidence),
        "links": issue.links,
        "review_decisions": [
            decision_record(decision)
            for decision in issue.review_decisions.order_by("recorded_at", "pk")
        ],
    }


def frame_summary(frame: FrameReview) -> dict[str, object]:
    source = frame.snapshot_frame
    job = source.snapshot_job
    ranking = (
        RunRankingEntry.objects.filter(ranking__run_id=frame.run_id, snapshot_frame=source)
        .order_by("ranking__source", "rank")
        .first()
    )
    return {
        "id": frame.pk,
        "run_id": frame.run_id,
        "frame_key": {"cvat_task_id": job.cvat_task_id, "frame_number": source.frame_index},
        "cvat_job_id": job.cvat_job_id,
        "rank": ranking.rank if ranking else None,
        "review_state": frame.state,
        "missing_evidence": bool(ranking.missing_evidence) if ranking else False,
        "image_url": storages["snapshots"].url(source.media_storage_key),
        "width": source.width,
        "height": source.height,
        "cvat_deep_link": build_job_url(
            settings.CVAT_BASE_URL,
            job.cvat_task_id,
            job.cvat_job_id,
            frame_index=source.frame_index,
        ),
    }


def frame_engines(frame: FrameReview) -> list[dict[str, object]]:
    source = frame.snapshot_frame
    job = source.snapshot_job
    units = LedgerUnit.objects.filter(
        run_id=frame.run_id, cvat_task_id=job.cvat_task_id, frame_number=source.frame_index
    ).order_by("engine", "pk")
    by_engine: dict[str, list[LedgerUnit]] = {}
    for unit in units:
        by_engine.setdefault(unit.engine, []).append(unit)
    results = {row.engine: row for row in EngineResult.objects.filter(run_id=frame.run_id)}
    output: list[dict[str, object]] = []
    for name in sorted(set(by_engine) | set(results)):
        rows = by_engine.get(name, [])
        reasons: dict[NotCheckedReason, int] = {}
        for row in rows:
            if row.outcome == EngineUnitOutcome.NOT_CHECKED and row.not_checked_reason:
                try:
                    reason = NotCheckedReason(row.not_checked_reason)
                except ValueError:
                    continue
                reasons[reason] = reasons.get(reason, 0) + 1
        ledger = LedgerCounts(
            completed=sum(row.outcome == EngineUnitOutcome.COMPLETED for row in rows),
            failed=sum(row.outcome == EngineUnitOutcome.FAILED for row in rows),
            pending=sum(row.outcome in UNFINISHED_OUTCOMES for row in rows),
            not_checked_reasons=reasons,
        )
        result = results.get(name)
        try:
            state = EngineInternalState(result.status) if result else EngineInternalState.RUNNING
        except ValueError:
            state = EngineInternalState.RUNNING
        output.append(
            {
                "engine": name,
                "status": str(engine_display_status(state, ledger)),
                "reason": result.reason if result else None,
                "failed_units": ledger.failed,
            }
        )
    return output


def frame_annotations(frame: FrameReview) -> list[dict[str, object]]:
    """Every annotation of the locked snapshot frame, with or without an engine candidate."""
    annotations: list[dict[str, object]] = []
    context = frame.run.snapshot.provenance.get("guideline_context", {})
    labels = context.get("annotation_labels") or context.get("taxonomy", {}).get("labels", [])
    by_id = {label["label_id"]: label for label in labels}
    for shape in frame.snapshot_frame.shapes:
        points = shape.get("points") or []
        source = shape.get("source") or {}
        annotations.append(
            {
                "id": f"{source.get('kind')}:{source.get('id')}",
                "source": source,
                "label_id": shape.get("label_id"),
                "label": by_id.get(shape.get("label_id"), {}).get("name"),
                "color": by_id.get(shape.get("label_id"), {}).get("color"),
                "bbox": (
                    {"x1": points[0], "y1": points[1], "x2": points[2], "y2": points[3]}
                    if len(points) == 4
                    else None
                ),
                "rotation": shape.get("rotation", 0),
                "occluded": shape.get("occluded", False),
                "outside": shape.get("outside", False),
                "z_order": shape.get("z_order", 0),
                "attributes": shape.get("attributes", []),
            }
        )
    return annotations


def frame_predictions(frame: FrameReview) -> list[dict[str, object]]:
    """Immutable engine output of this run for the frame; never altered by review."""
    source = frame.snapshot_frame
    job = source.snapshot_job
    candidates = CandidateRecord.objects.filter(
        run_id=frame.run_id, cvat_task_id=job.cvat_task_id, frame_number=source.frame_index
    ).order_by("pk")
    return [
        {
            "candidate_id": candidate.pk,
            "engine": candidate.engine,
            "engine_version": candidate.engine_version,
            "family": candidate.family,
            "anchor": candidate.anchor,
            "evidence": candidate.evidence,
        }
        for candidate in candidates
    ]
