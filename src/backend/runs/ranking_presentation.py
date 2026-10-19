"""Read-time evidence groups; never modify the frozen score_v0 ordering.

These are review groups, not calibrated risk levels or confirmed error counts.
"""

from django.db.models import CharField, F, Func, Q, Value
from django.db.models.fields.json import KeyTransform
from django.db.models.lookups import Exact

from runs.models import QCRun

PRIORITIES = ("suspected", "unassessed", "no_suspicions")
SCORING_ENGINES = frozenset({"schema", "geometry", "duplicate", "detector"})


def _has_json_type(family: str | None, kind: str) -> Q:
    value = F("issue_counts") if family is None else KeyTransform(family, "issue_counts")
    return Q(Exact(Func(value, function="jsonb_typeof", output_field=CharField()), Value(kind)))


def _positive_count(family: str) -> Q:
    # PostgreSQL jsonb orders unlike types: objects/bools can compare above 0.
    # Check the JSON type before interpreting a legacy value as a count.
    return _has_json_type(family, "number") & Q(**{f"issue_counts__{family}__gt": 0})


def _valid_count(family: str) -> Q:
    return ~Q(issue_counts__has_key=family) | (
        _has_json_type(family, "number") & ~Q(**{f"issue_counts__{family}__lt": 0})
    )


HAS_SUSPICIONS = _positive_count("E1") | _positive_count("E2") | _positive_count("E3")
VALID_COUNTS = (
    _has_json_type(None, "object") & _valid_count("E1") & _valid_count("E2") & _valid_count("E3")
)


def counts_are_valid(issue_counts: object) -> bool:
    return isinstance(issue_counts, dict) and all(
        isinstance(count, (int, float)) and not isinstance(count, bool) and count >= 0
        for family in ("E1", "E2", "E3")
        if family in issue_counts
        for count in [issue_counts[family]]
    )


def run_evidence_incomplete(run: QCRun) -> bool:
    """Disabled detector still leaves E1/E2 unassessed; optional VLM is separate."""
    results = list(run.engine_results.all())
    by_engine = {result.engine: result for result in results}
    expected = SCORING_ENGINES | {result.engine for result in results if result.required}
    return any(
        engine not in by_engine or by_engine[engine].status != "checked" for engine in expected
    )


def review_priority(issue_counts: object, missing_evidence: bool) -> str:
    if isinstance(issue_counts, dict) and any(
        isinstance(count, (int, float)) and not isinstance(count, bool) and count > 0
        for family in ("E1", "E2", "E3")
        for count in [issue_counts.get(family)]
    ):
        return "suspected"
    return (
        "unassessed" if missing_evidence or not counts_are_valid(issue_counts) else "no_suspicions"
    )
