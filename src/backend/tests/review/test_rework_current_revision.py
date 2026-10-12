"""GET /api/rework/{id}/current-revision/: read-only revision the next submit would claim."""

import httpx
import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext

from accounts.models import Role, RoleAssignment
from audit.models import AuditEvent
from review import rework_service
from review.models import ReworkRecheck, ReworkRequest
from runs.models import QCRun
from snapshots.models import Snapshot
from tests.review.test_queue_lease import client
from tests.review.test_rework import (  # noqa: F401 - fixtures
    changed_snapshot,
    confirmed,
    create_request,
    cvat_base_url,
)

pytest_plugins = ["tests.review.test_queue_lease"]
REVISION = "b" * 64


@pytest.fixture
def rework(confirmed, world):  # noqa: F811
    created = create_request(confirmed, world)
    assert created.status_code == 201, created.data
    return ReworkRequest.objects.get(pk=created.data["id"])


@pytest.fixture(autouse=True)
def clean_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def current(monkeypatch):
    seen: list[tuple[int, int]] = []

    def fake(*, dataset_id, cvat_job_id, client=None):
        seen.append((dataset_id, cvat_job_id))
        return REVISION

    monkeypatch.setattr(rework_service, "compute_job_revision", fake)
    return seen


def _url(rework):
    return f"/api/rework/{rework.pk}/current-revision/"


def _counts():
    return (
        Snapshot.objects.count(),
        QCRun.objects.count(),
        AuditEvent.objects.count(),
        ReworkRecheck.objects.count(),
    )


@pytest.mark.django_db
def test_annotator_reads_current_revision_without_any_db_write(rework, world, current):
    before = _counts()
    row_before = ReworkRequest.objects.filter(pk=rework.pk).values().get()
    with CaptureQueriesContext(connection) as queries:
        response = client(world["author"]).get(_url(rework))
    assert response.status_code == 200, response.data
    writes = [
        q["sql"]
        for q in queries
        if q["sql"].lstrip().split(None, 1)[0].upper() not in {"SELECT", "SAVEPOINT", "RELEASE"}
    ]
    assert writes == []
    assert ReworkRequest.objects.filter(pk=rework.pk).values().get() == row_before
    assert response.data["rework_status"] == "fix_pending"
    assert response.data["rework_id"] == rework.pk
    assert response.data["cvat_job_id"] == 100
    assert response.data["revision_sha256"] == REVISION
    assert response.data["original_revision"] == rework.original_revision
    assert response.data["unchanged"] is False
    assert response.data["read_at"]
    assert current == [(42, 100)]
    assert _counts() == before


@pytest.mark.django_db
def test_unchanged_true_when_revision_equals_original(rework, world, monkeypatch):
    monkeypatch.setattr(
        rework_service, "compute_job_revision", lambda **_kw: rework.original_revision
    )
    response = client(world["author"]).get(_url(rework))
    assert response.status_code == 200 and response.data["unchanged"] is True
    submit = client(world["author"]).post(
        _url(rework).replace("current-revision", "submitted"),
        {"cvat_revision": response.data["revision_sha256"]},
        format="json",
    )
    assert submit.status_code == 409 and submit.data["code"] == "REVISION_UNCHANGED"


@pytest.mark.django_db
def test_unchanged_true_for_an_earlier_submitted_round(rework, world, monkeypatch):
    snapshot = changed_snapshot(world)
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=world["run"].config_version,
        seed=world["run"].seed,
        status=QCRun.Status.QUEUED,
        origin_run=world["run"],
        dataset_id=42,
        scope_hash=snapshot.revision_sha256,
        created_by=world["author"],
    )
    monkeypatch.setattr(rework_service, "_build_recheck_artifacts", lambda **_kw: (snapshot, run))
    monkeypatch.setattr(
        rework_service, "compute_job_revision", lambda **_kw: snapshot.revision_sha256
    )
    before = client(world["author"]).get(_url(rework))
    assert before.data["unchanged"] is False
    submitted = client(world["author"]).post(
        _url(rework).replace("current-revision", "submitted"),
        {"cvat_revision": before.data["revision_sha256"]},
        format="json",
    )
    assert submitted.status_code == 202, submitted.data
    after = client(world["author"]).get(_url(rework))
    assert after.data["revision_sha256"] == snapshot.revision_sha256
    assert after.data["unchanged"] is True


@pytest.mark.django_db
def test_other_annotator_gets_404_and_scopeless_user_403(rework, world, current):
    other = User.objects.create_user("other-annotator")
    RoleAssignment.objects.create(user=other, role=Role.ANNOTATOR, dataset_id=42)
    outsider = User.objects.create_user("outsider")
    RoleAssignment.objects.create(user=outsider, role=Role.ANNOTATOR, dataset_id=999)
    before = _counts()
    assert client(other).get(_url(rework)).status_code == 404
    forbidden = client(outsider).get(_url(rework))
    assert forbidden.status_code == 403
    assert current == []  # CVAT is never read for a caller that may not see the rework
    assert Snapshot.objects.count() == before[0] and QCRun.objects.count() == before[1]


@pytest.mark.django_db
def test_reviewer_in_dataset_can_read_and_missing_rework_is_404(rework, world, current):
    assert client(world["reviewer"]).get(_url(rework)).status_code == 200
    assert client(world["reviewer"]).get("/api/rework/999999/current-revision/").status_code == 404


@pytest.mark.django_db
def test_cvat_failure_is_a_clear_business_error_and_writes_nothing(rework, world, monkeypatch):
    def boom(**_kw):
        raise httpx.ConnectError("secret-host")

    monkeypatch.setattr(rework_service, "compute_job_revision", boom)
    before = _counts()
    response = client(world["author"]).get(_url(rework))
    assert response.status_code == 502
    assert response.data["code"] == "BUSINESS_RULE_UNMET"
    assert "secret-host" not in str(response.data)
    assert _counts() == before


@pytest.mark.django_db
def test_write_methods_are_not_allowed(rework, world, current):
    assert client(world["author"]).post(_url(rework), {}, format="json").status_code == 405


@pytest.mark.django_db
def test_malformed_cvat_payload_is_502_not_500(rework, world, monkeypatch):
    def missing_key(**_kw):
        raise KeyError("frames")

    monkeypatch.setattr(rework_service, "compute_job_revision", missing_key)
    response = client(world["author"]).get(_url(rework))
    assert response.status_code == 502 and response.data["code"] == "BUSINESS_RULE_UNMET"


@pytest.mark.django_db
def test_resolved_rework_reports_its_status(rework, world, current):
    ReworkRequest.objects.filter(pk=rework.pk).update(status=ReworkRequest.Status.RESOLVED)
    response = client(world["author"]).get(_url(rework))
    assert response.status_code == 200 and response.data["rework_status"] == "resolved"


@pytest.mark.django_db
def test_throttle_is_per_user_and_scoped_to_this_endpoint(rework, world, current):
    author = client(world["author"])
    assert [author.get(_url(rework)).status_code for _ in range(6)] == [200] * 6
    limited = author.get(_url(rework))
    assert limited.status_code == 429
    assert limited.data["code"] == "BUSINESS_RULE_UNMET"
    assert limited.data["details"]["retry_after_seconds"] >= 1
    assert limited["Retry-After"]
    # another user is unaffected; so are other endpoints of the throttled user
    assert client(world["reviewer"]).get(_url(rework)).status_code == 200
    assert author.get(f"/api/rework/{rework.pk}/").status_code == 200
    assert author.get("/api/rework/?dataset_id=42").status_code == 200
