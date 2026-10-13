"""Read-only per-round timeline of a rework (submission -> re-check -> verification)."""

from __future__ import annotations

from review.models import ReworkRequest, ReworkVerification


def _verification_payload(verification: ReworkVerification) -> dict[str, object]:
    return {
        "id": verification.pk,
        "outcome": verification.outcome,
        "verifier_user_id": verification.verifier_id,
        "reason": verification.reason,
        "verified_at": verification.created_at.isoformat(),
    }


def _result_status(verification: ReworkVerification | None) -> str:
    """Rework status right after this round: fail reopens into fix_pending."""

    if verification is None:
        return ReworkRequest.Status.RECHECK_PENDING.value
    if verification.outcome == ReworkVerification.Outcome.PASS:
        return ReworkRequest.Status.RESOLVED.value
    return ReworkRequest.Status.FIX_PENDING.value


def rework_timeline(rework: ReworkRequest) -> list[dict[str, object]]:
    """Rounds in submission order; uses prefetched rechecks/verifications, never writes."""

    verifications = sorted(rework.verifications.all(), key=lambda row: row.pk)
    by_run: dict[int, ReworkVerification] = {}
    for row in verifications:
        by_run.setdefault(row.recheck_run_id, row)
    rounds: list[dict[str, object]] = []
    seen_runs: set[int] = set()
    for recheck in sorted(rework.rechecks.all(), key=lambda row: (row.round, row.pk)):
        verification = by_run.get(recheck.run_id)
        seen_runs.add(recheck.run_id)
        rounds.append(
            {
                "round": recheck.round,
                "revision": recheck.revision,
                "snapshot_id": recheck.snapshot_id,
                "recheck_run_id": recheck.run_id,
                "recheck_run_status": recheck.run.status,
                "submitted_at": recheck.created_at.isoformat(),
                "verification": _verification_payload(verification) if verification else None,
                "result_status": _result_status(verification),
            }
        )
    # Rows created before per-round rechecks existed carry only the verification.
    for orphan in verifications:
        if orphan.recheck_run_id in seen_runs:
            continue
        seen_runs.add(orphan.recheck_run_id)
        rounds.append(
            {
                "round": len(rounds) + 1,
                "revision": orphan.revision,
                "snapshot_id": orphan.recheck_run.snapshot_id,
                "recheck_run_id": orphan.recheck_run_id,
                "recheck_run_status": orphan.recheck_run.status,
                "submitted_at": None,
                "verification": _verification_payload(orphan),
                "result_status": _result_status(orphan),
            }
        )
    return rounds
