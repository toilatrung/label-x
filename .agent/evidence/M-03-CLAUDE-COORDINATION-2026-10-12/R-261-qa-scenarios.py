"""Independent QA scenarios for PR #261 (#238). Written by label-x-7a, not the PR author.

Everything goes through the real HTTP API; time is moved by editing Lease.expires_at in the DB
(never by patching clocks). Rework recheck artifacts are stubbed exactly like the existing probes.
"""
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from review.models import FrameReview, Issue, Lease, ReviewDecision, ReworkRequest
from runs.models import QCRun
from tests.review.test_queue_lease import client, next_url
from tests.review.test_rework import changed_snapshot

pytest_plugins = ["tests.review.test_queue_lease"]


@pytest.fixture(autouse=True)
def _storage(monkeypatch):
    from django.core.files.storage import storages

    monkeypatch.setattr(storages["snapshots"], "url", lambda name: f"https://storage.test/{name}")


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.CVAT_BASE_URL = "http://localhost:8080"
    settings.ORCHESTRATION_AUTO_DISPATCH = False
    settings.FINAL_RUN_AUTO_DISPATCH = False


def claim(user, world):
    return client(user).post(next_url(), {"run_id": world["run"].pk}, format="json")


def lease_of(resp):
    return Lease.objects.get(pk=resp.data["lease"]["id"])


def new_issue(user, lease, world):
    r = client(user).post(
        "/api/issues/",
        {
            "frame_id": lease.frame_review_id,
            "lease_id": lease.pk,
            "family": "E1",
            "anchor": {
                "kind": "manual_region",
                "objects": [],
                "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
                "policy_version": "anchor-v1",
            },
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    return r.data["id"]


def decide(user, lease, issue_id, world, action="confirm"):
    body = {"lease_id": lease.pk, "action": action, "revision": world["run"].snapshot.revision_sha256}
    if action == "confirm":
        body.update(family="E1", severity="medium")
    else:
        body["reason"] = "because"
    r = client(user).post(f"/api/issues/{issue_id}/decisions/", body, format="json")
    assert r.status_code == 201, r.data
    return r


def expire(lease):
    Lease.objects.filter(pk=lease.pk).update(expires_at=timezone.now() - timedelta(seconds=1))


def rework(user, issue_id, world):
    r = client(user).post(
        "/api/rework/",
        {
            "issue_id": issue_id,
            "instruction": "fix box",
            "annotator_user_id": world["author"].pk,
            "due_at": "2026-10-13T10:00:00Z",
            "severity": "medium",
            "cvat_deep_link": "http://localhost:8080/tasks/200/jobs/100?frame=0",
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    return ReworkRequest.objects.get(pk=r.data["id"])


def submit_and_verify(rw, world, monkeypatch, verifier=None, passed=True):
    snap = changed_snapshot(world)
    run = QCRun.objects.create(
        snapshot=snap,
        config_version=world["run"].config_version,
        seed=1,
        status=QCRun.Status.COMPLETED,
        origin_run=world["run"],
        dataset_id=42,
        scope_hash=snap.revision_sha256,
        created_by=world["author"],
    )
    monkeypatch.setattr("review.rework_service._build_recheck_artifacts", lambda **kw: (snap, run))
    s = client(world["author"]).post(
        f"/api/rework/{rw.pk}/submitted/", {"cvat_revision": snap.revision_sha256}, format="json"
    )
    assert s.status_code == 202, s.data
    body = {"passed": passed, "revision": snap.revision_sha256}
    if not passed:
        body["reason"] = "still wrong"
    v = client(verifier or world["other"]).post(f"/api/rework/{rw.pk}/verify/", body, format="json")
    assert v.status_code == 200, v.data
    return v


def frame_of(world):
    return FrameReview.objects.get(run=world["run"], snapshot_frame=world["frame"])


def complete(user, lease):
    return client(user).post(
        f"/api/frames/{lease.frame_review_id}/complete/", {"lease_id": lease.pk}, format="json"
    )


def complete_audits(frame):
    return AuditEvent.objects.filter(
        action="frame.complete", object_type="frame", object_id=str(frame.pk)
    ).count()


# (a) F1 ---------------------------------------------------------------------------------------
@pytest.mark.django_db
def test_a_f1_expired_lease_does_not_overwrite_handed_over_frame(world, monkeypatch):
    a, b = world["reviewer"], world["other"]
    lease = lease_of(claim(a, world))
    issue_id = new_issue(a, lease, world)
    decide(a, lease, issue_id, world)
    rw = rework(a, issue_id, world)
    expire(lease)  # holder walked away; lease expired but nothing materialised it
    submit_and_verify(rw, world, monkeypatch, verifier=b)
    assert frame_of(world).state == FrameReview.State.AWAITING_FOLLOWUP
    r = claim(b, world)  # reviewer B claims again: this is where the old code overwrote the frame
    assert r.status_code == 204, r.data
    assert frame_of(world).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease.pk).closed_at is not None


# (b) undecided issue keeps the frame in review until the reviewer finishes ----------------------
@pytest.mark.django_db
def test_b_undecided_issue_blocks_followup_until_complete(world, monkeypatch):
    a = world["reviewer"]
    lease = lease_of(claim(a, world))
    decided = new_issue(a, lease, world)
    decide(a, lease, decided, world)
    undecided = new_issue(a, lease, world)
    rw = rework(a, decided, world)
    submit_and_verify(rw, world, monkeypatch)
    f = frame_of(world)
    assert f.state == FrameReview.State.IN_REVIEW  # still has an undecided issue
    assert Lease.objects.get(pk=lease.pk).closed_at is None  # lease untouched
    rw.refresh_from_db()
    assert rw.status == ReworkRequest.Status.RESOLVED  # verification still recorded
    expire(lease)
    resumed = claim(a, world)  # expiry -> incomplete -> resume
    assert resumed.status_code == 200 and resumed.data["resumed"] is True, resumed.data
    assert frame_of(world).state == FrameReview.State.IN_REVIEW
    new_lease = lease_of(resumed)
    assert new_lease.pk != lease.pk
    decide(a, new_lease, undecided, world, action="reject")
    done = complete(a, new_lease)
    assert done.status_code == 200, done.data
    assert frame_of(world).state == FrameReview.State.AWAITING_FOLLOWUP  # hook: reworks resolved


# (c) reviewer forgets to complete -----------------------------------------------------------------
@pytest.mark.django_db
def test_c_forgotten_complete_verify_hands_frame_over(world, monkeypatch):
    a = world["reviewer"]
    lease = lease_of(claim(a, world))
    issue_id = new_issue(a, lease, world)
    decide(a, lease, issue_id, world)
    rw = rework(a, issue_id, world)
    submit_and_verify(rw, world, monkeypatch)
    assert frame_of(world).state == FrameReview.State.AWAITING_FOLLOWUP
    assert Lease.objects.get(pk=lease.pk).closed_at is not None


# (d) frames/complete -------------------------------------------------------------------------------
@pytest.mark.django_db
def test_d1_former_holder_gets_200_once_audited_and_repeat_is_idempotent(world, monkeypatch):
    a = world["reviewer"]
    lease = lease_of(claim(a, world))
    issue_id = new_issue(a, lease, world)
    decide(a, lease, issue_id, world)
    submit_and_verify(rework(a, issue_id, world), world, monkeypatch)
    f = frame_of(world)
    assert complete_audits(f) == 0
    r1 = complete(a, lease)
    assert r1.status_code == 200, r1.data
    assert complete_audits(f) == 1
    before = ReviewDecision.objects.count()
    r2 = complete(a, lease)
    assert r2.status_code == 200
    assert complete_audits(f) == 1 and ReviewDecision.objects.count() == before
    assert frame_of(world).state == FrameReview.State.AWAITING_FOLLOWUP


@pytest.mark.django_db
def test_d2_non_holder_cannot_use_someone_elses_lease(world, monkeypatch):
    a, b = world["reviewer"], world["other"]
    lease = lease_of(claim(a, world))
    issue_id = new_issue(a, lease, world)
    decide(a, lease, issue_id, world)
    submit_and_verify(rework(a, issue_id, world), world, monkeypatch)
    r = complete(b, lease)
    assert r.status_code in (403, 409), (r.status_code, r.data)
    assert complete_audits(frame_of(world)) == 0


@pytest.mark.django_db
def test_d3_displaced_holder_complete_is_409_and_frame_stays_in_review(world):
    a, b = world["reviewer"], world["other"]
    lease_a = lease_of(claim(a, world))
    issue_id = new_issue(a, lease_a, world)
    decide(a, lease_a, issue_id, world)
    expire(lease_a)
    f = frame_of(world)
    # claim_next materialises the expiry (frame -> incomplete reserved for A); lift the reservation
    assert claim(b, world).status_code == 204
    FrameReview.objects.filter(pk=f.pk).update(incomplete_since=timezone.now() - timedelta(days=1))
    grant_b = claim(b, world)
    assert grant_b.status_code == 200, grant_b.data
    assert frame_of(world).state == FrameReview.State.IN_REVIEW
    r = complete(a, lease_a)
    assert r.status_code == 409 and r.data["code"] == "LEASE_CONFLICT", (r.status_code, r.data)
    assert r.data["details"]["frame_state"] == "in_review"
    assert frame_of(world).state == FrameReview.State.IN_REVIEW


@pytest.mark.django_db
def test_d3b_old_holder_after_other_reviewer_finished(world):
    """A lost the frame to B and B finished it. What does A's stale lease get?"""
    a, b = world["reviewer"], world["other"]
    lease_a = lease_of(claim(a, world))
    issue_id = new_issue(a, lease_a, world)
    decide(a, lease_a, issue_id, world)
    expire(lease_a)
    claim(b, world)
    FrameReview.objects.filter(pk=frame_of(world).pk).update(
        incomplete_since=timezone.now() - timedelta(days=1)
    )
    lease_b = lease_of(claim(b, world))
    assert complete(b, lease_b).status_code == 200
    assert frame_of(world).state == FrameReview.State.REVIEWED
    r = complete(a, lease_a)
    # Recorded for the report; the PR text says only the (former) holder of THIS completion gets 200.
    print("D3B_STALE_HOLDER_AFTER_OTHER_FINISHED", r.status_code, r.data)
    assert r.status_code == 409, (r.status_code, r.data)


@pytest.mark.django_db
def test_d4_retry_after_completed_is_200(world, monkeypatch):
    a = world["reviewer"]
    lease = lease_of(claim(a, world))
    issue_id = new_issue(a, lease, world)
    decide(a, lease, issue_id, world)
    submit_and_verify(rework(a, issue_id, world), world, monkeypatch)
    assert complete(a, lease).status_code == 200
    FrameReview.objects.filter(pk=frame_of(world).pk).update(state=FrameReview.State.COMPLETED)
    r = complete(a, lease)
    assert r.status_code == 200, r.data
    assert frame_of(world).state == FrameReview.State.COMPLETED


@pytest.mark.django_db
def test_d5_undecided_issue_blocks_idempotent_200(world, monkeypatch):
    a = world["reviewer"]
    lease = lease_of(claim(a, world))
    decided = new_issue(a, lease, world)
    decide(a, lease, decided, world)
    new_issue(a, lease, world)  # stays undecided
    r = complete(a, lease)
    assert r.status_code == 422, (r.status_code, r.data)


# (e) escalated issue is not "undecided" ------------------------------------------------------------
@pytest.mark.django_db
def test_e_escalated_issue_does_not_block_followup(world, monkeypatch):
    a = world["reviewer"]
    lease = lease_of(claim(a, world))
    decided = new_issue(a, lease, world)
    decide(a, lease, decided, world)
    escalated = new_issue(a, lease, world)
    decide(a, lease, escalated, world, action="escalate")
    assert Issue.objects.get(pk=escalated).state == Issue.State.ESCALATED
    submit_and_verify(rework(a, decided, world), world, monkeypatch)
    assert frame_of(world).state == FrameReview.State.AWAITING_FOLLOWUP


# (f) live lease on a frame that already left in_review ---------------------------------------------
@pytest.mark.django_db
def test_f_claim_does_not_resume_and_renew_is_409_for_moved_on_frame(world):
    a = world["reviewer"]
    lease = lease_of(claim(a, world))
    FrameReview.objects.filter(pk=lease.frame_review_id).update(
        state=FrameReview.State.AWAITING_FOLLOWUP
    )
    renew = client(a).post(f"/api/leases/{lease.pk}/renew/", {}, format="json")
    assert renew.status_code == 409 and renew.data["code"] == "LEASE_CONFLICT"
    assert Lease.objects.get(pk=lease.pk).closed_at is not None
    again = claim(a, world)
    assert again.status_code == 204, again.data  # no "resumed" grant on the moved-on frame


@pytest.mark.django_db
def test_f2_claim_on_live_lease_of_moved_on_frame_never_resumes(world):
    a = world["reviewer"]
    lease = lease_of(claim(a, world))
    FrameReview.objects.filter(pk=lease.frame_review_id).update(state=FrameReview.State.REVIEWED)
    r = claim(a, world)  # claim BEFORE any renew
    assert r.status_code == 204, r.data


# permissions / scope -------------------------------------------------------------------------------
@pytest.mark.django_db
def test_p_self_review_role_scope_and_single_lease(world):
    a = world["reviewer"]
    # one lease per reviewer: a second claim returns the same lease (resumed)
    first = claim(a, world)
    second = claim(a, world)
    assert second.status_code == 200 and second.data["lease"]["id"] == first.data["lease"]["id"]
    assert second.data["resumed"] is True
    assert Lease.objects.filter(holder=a, closed_at__isnull=True).count() == 1
    frame_id = first.data["frame"]["id"]
    # annotator cannot claim; reviewer scoped to another dataset is out of scope
    assert claim(world["author"], world).status_code == 403
    outsider = User.objects.create_user("outsider-qa")
    RoleAssignment.objects.create(user=outsider, role=Role.REVIEWER, dataset_id=999)
    assert claim(outsider, world).status_code == 403
    # alias account of the job assignee (same natural person, other CVAT id)
    me = User.objects.create_user("self-reviewer-qa")
    RoleAssignment.objects.create(user=me, role=Role.REVIEWER, dataset_id=42)
    author_emp = CvatIdentity.objects.get(user=world["author"]).employee
    CvatIdentity.objects.create(user=me, cvat_user_id=7777, employee=author_emp)
    assert claim(me, world).status_code == 204  # frames it may not review are never granted
    denied = client(me).get(f"/api/frames/{frame_id}/issues/")
    assert denied.status_code == 403, denied.data
    assert denied.data["code"] == "SELF_REVIEW_FORBIDDEN", denied.data
