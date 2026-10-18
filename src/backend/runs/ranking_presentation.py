"""Read-time evidence groups; never modify the frozen score_v0 ordering.

These are review groups, not calibrated risk levels or confirmed error counts.
"""

from django.db.models import Q

from runs.models import QCRun

PRIORITIES = ("suspected", "unassessed", "no_suspicions")
SCORING_ENGINES = frozenset({"schema", "geometry", "duplicate", "detector"})
HAS_SUSPICIONS = Q(issue_counts__E1__gt=0) | Q(issue_counts__E2__gt=0) | Q(issue_counts__E3__gt=0)


def run_evidence_incomplete(run: QCRun) -> bool:
    """Disabled detector still leaves E1/E2 unassessed; optional VLM is separate."""
    results = list(run.engine_results.all())
    by_engine = {result.engine: result for result in results}
    expected = SCORING_ENGINES | {result.engine for result in results if result.required}
    return any(
        engine not in by_engine or by_engine[engine].status != "checked" for engine in expected
    )


def review_priority(issue_counts: dict[str, int], missing_evidence: bool) -> str:
    if any(issue_counts.get(family, 0) > 0 for family in ("E1", "E2", "E3")):
        return "suspected"
    return "unassessed" if missing_evidence else "no_suspicions"
