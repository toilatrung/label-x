"""DEC-019 P07: operational_source.blocked_reasons lists EVERY reason that applies.

Stable (sorted, unique) and read-only; the source decision (evaluation order) is unchanged.
Synthetic fixtures only.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from orchestration.models import LedgerUnit
from review.finalization_service import (
    final_source_blockers,
    final_source_status,
    operational_run,
    select_operational_source,
)
from review.lineage import run_lineage_fields
from review.models import Issue
from runs.models import QCRun
from tests.review.test_final_concurrency import _break_ledger
from tests.review.test_final_source_guard import (  # noqa: F401
    _candidate,
    _complete_final,
    final_world,
)
from tests.runs.test_run_detail_coverage import _client

pytest_plugins = ["tests.review.test_queue_lease", "tests.review.test_final_source_guard"]


def _reasons(origin: QCRun) -> list[str]:
    return run_lineage_fields(origin)["operational_source"]["blocked_reasons"]  # type: ignore[index,return-value]


@pytest.mark.django_db
def test_ledger_gap_and_new_candidate_together_list_both(final_world):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    _candidate(final, "both-new")
    _break_ledger(final, "failed_unit")

    assert _reasons(origin) == ["coverage_incomplete", "new_candidate_unreviewed"]
    assert final_source_blockers(origin, final) == [
        "new_candidate_unreviewed",
        "coverage_incomplete",
    ]
    # evaluation order unchanged: the first blocker is still the single reason
    assert final_source_status(origin, final) == (False, "new_candidate_unreviewed")
    assert operational_run(origin).pk == origin.pk


@pytest.mark.django_db
def test_all_three_completed_reasons_sorted_and_unique(final_world):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    _candidate(final, "triple-new")
    _break_ledger(final, "pending_ledger")
    Issue.objects.create(
        frame_review=final_world["issue"].frame_review.__class__.objects.create(
            run=final, snapshot_frame=final_world["issue"].frame_review.snapshot_frame
        ),
        family=Issue.Family.E2,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.PENDING_REVIEW,
        anchor={"kind": "manual_region", "objects": []},
    )

    expected = ["coverage_incomplete", "new_candidate_unreviewed", "open_issue_in_final_run"]
    assert _reasons(origin) == expected
    assert _reasons(origin) == expected  # stable across calls
    attempts = run_lineage_fields(origin)["operational_source"]["final_attempts"]  # type: ignore[index]
    assert attempts == [
        {"run_id": final.pk, "status": "completed", "reason": "open_issue_in_final_run"}
    ]  # shape and first blocker unchanged


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("gap", "expected"),
    [("failed_unit", ["coverage_incomplete"]), ("not_checked", ["coverage_incomplete"])],
)
def test_single_reasons_are_unchanged(final_world, gap, expected):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    _break_ledger(final, gap)
    assert _reasons(origin) == expected


@pytest.mark.django_db
def test_single_new_candidate_reason_is_unchanged(final_world):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    _candidate(final, "only-new")
    assert _reasons(origin) == ["new_candidate_unreviewed"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "terminal",
    [QCRun.Status.PARTIAL, QCRun.Status.FAILED, QCRun.Status.CANCELLED],
)
def test_terminal_final_has_only_its_status_reason(final_world, terminal):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    _candidate(final, "late-new")
    _break_ledger(final, "failed_unit")
    final.status = terminal
    final.save(update_fields=["status"])
    assert _reasons(origin) == [f"final_run_{terminal}"]


@pytest.mark.django_db
def test_no_reasons_when_a_valid_final_is_selected(final_world):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    assert _reasons(origin) == []
    assert select_operational_source(origin)[1] == "selected_final"


@pytest.mark.django_db
def test_reasons_of_several_attempts_are_merged(final_world):  # noqa: F811
    origin, failed = final_world["run"], final_world["final"]
    _complete_final(failed)
    _candidate(failed, "attempt-one-new")
    retry = QCRun.objects.create(
        snapshot=failed.snapshot,
        config_version=failed.config_version,
        seed=failed.seed,
        dataset_id=failed.dataset_id,
        scope_hash=failed.scope_hash,
        created_by=failed.created_by,
        origin_run=origin,
        is_final=True,
        idempotency_key=f"{failed.idempotency_key}-retry",
    )
    _complete_final(retry)
    LedgerUnit.objects.filter(run=retry).update(outcome="pending")
    assert _reasons(origin) == ["coverage_incomplete", "new_candidate_unreviewed"]


@pytest.mark.django_db
def test_get_run_detail_lists_all_reasons_and_writes_nothing(final_world):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    _candidate(final, "api-new")
    _break_ledger(final, "failed_unit")
    api = _client(final_world["reviewer"])

    with CaptureQueriesContext(connection) as queries:
        body = api.get(f"/api/runs/{origin.pk}/").json()

    assert body["operational_source"]["blocked_reasons"] == [
        "coverage_incomplete",
        "new_candidate_unreviewed",
    ]
    writes = [
        q["sql"]
        for q in queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert writes == []


def _retry_attempt(origin: QCRun, base: QCRun, suffix: str) -> QCRun:
    return QCRun.objects.create(
        snapshot=base.snapshot,
        config_version=base.config_version,
        seed=base.seed,
        dataset_id=base.dataset_id,
        scope_hash=base.scope_hash,
        created_by=base.created_by,
        origin_run=origin,
        is_final=True,
        idempotency_key=f"{base.idempotency_key}-{suffix}",
    )


@pytest.mark.django_db
def test_two_attempts_with_the_same_reason_are_listed_once(final_world):  # noqa: F811
    origin, first = final_world["run"], final_world["final"]
    _complete_final(first)
    LedgerUnit.objects.filter(run=first).update(outcome="pending")
    second = _retry_attempt(origin, first, "same-reason")
    _complete_final(second)
    LedgerUnit.objects.filter(run=second).update(outcome="pending")

    assert [
        a["reason"] for a in run_lineage_fields(origin)["operational_source"]["final_attempts"]
    ] == [  # type: ignore[index]
        "coverage_incomplete",
        "coverage_incomplete",
    ]
    assert _reasons(origin) == ["coverage_incomplete"]


@pytest.mark.django_db
def test_valid_selected_final_hides_blockers_of_other_attempts(final_world):  # noqa: F811
    """Intended: a valid final means the scope is not blocked, whatever an older attempt said."""

    origin, broken = final_world["run"], final_world["final"]
    _complete_final(broken)
    _break_ledger(broken, "failed_unit")
    _candidate(broken, "old-attempt-new")
    valid = _retry_attempt(origin, broken, "valid")
    _complete_final(valid)

    source = run_lineage_fields(origin)["operational_source"]
    assert source["scope_complete"] is True and source["run_id"] == valid.pk  # type: ignore[index]
    assert source["blocked_reasons"] == []  # type: ignore[index]
    assert {a["run_id"] for a in source["final_attempts"]} == {broken.pk, valid.pk}  # type: ignore[index]


@pytest.mark.django_db
def test_origin_with_open_issue_reports_only_that_reason(final_world):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    _complete_final(final)
    Issue.objects.filter(pk=final_world["issue"].pk).update(state=Issue.State.PENDING_REVIEW)

    source = run_lineage_fields(origin)["operational_source"]
    assert source["blocked_reasons"] == ["origin_has_open_issue"]  # type: ignore[index]
    assert source["final_attempts"] == []  # type: ignore[index]
    assert source["scope_complete"] is False and source["run_id"] == origin.pk  # type: ignore[index]


@pytest.mark.django_db
def test_origin_without_any_final_attempt_reports_no_valid_final(final_world):  # noqa: F811
    origin, final = final_world["run"], final_world["final"]
    QCRun.objects.filter(pk=final.pk).update(is_final=False)  # no final attempt remains

    source = run_lineage_fields(origin)["operational_source"]
    assert source["blocked_reasons"] == ["no_valid_final"]  # type: ignore[index]
    assert source["final_attempts"] == []  # type: ignore[index]
