"""Read-only normalization of detector no-match context across the four engines."""

from typing import Any

from orchestration.models import CandidateRecord


def unmatched_targets(run_id: int) -> set[tuple[int, int, str]]:
    targets = set()
    for candidate in CandidateRecord.objects.filter(
        run_id=run_id, engine="detector", evidence__trigger_reason="detector_no_match"
    ):
        for obj in (candidate.anchor or {}).get("objects", []):
            if isinstance(obj, dict) and isinstance(obj.get("id"), str):
                targets.add((candidate.cvat_task_id, candidate.frame_number, obj["id"]))
    return targets


def routing_evidence(
    candidate: CandidateRecord, targets: set[tuple[int, int, str]]
) -> dict[str, Any]:
    evidence = candidate.evidence if isinstance(candidate.evidence, dict) else {}
    for obj in (candidate.anchor or {}).get("objects", []):
        if (
            isinstance(obj, dict)
            and (candidate.cvat_task_id, candidate.frame_number, obj.get("id")) in targets
        ):
            return {**evidence, "trigger_reason": "detector_no_match"}
    return evidence
