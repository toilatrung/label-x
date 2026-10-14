"""T-038 escalation, adjudication, and versioned decision cases test suite."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import storages
from django.db import DatabaseError, connection, connections
from django.utils import timezone

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment
from audit.models import AuditEvent
from guideline.models import GuidelineRule, GuidelineVersion
from review.models import (
    DecisionCase,
    FrameReview,
    GuidelineGap,
    Issue,
    ReviewDecision,
    ReworkRequest,
)
from tests.review.test_queue_lease import client

pytest_plugins = ["tests.review.test_queue_lease"]
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def snapshot_storage_mock(monkeypatch):
    monkeypatch.setattr(
        storages["snapshots"],
        "url",
        lambda name: f"https://storage.test/{name}",
    )


@pytest.fixture
def adj_world(world):
    admin = world["admin"]
    run = world["run"]
    frame = world["frame"]

    # 1. Setup guideline version and rule
    gv, _ = GuidelineVersion.objects.get_or_create(
        version_tag="guide", defaults={"name": "guide", "file_checksum": "a" * 64}
    )
    rule, _ = GuidelineRule.objects.get_or_create(
        version=gv,
        rule_id="RULE-01",
        defaults={"section": "sec1", "content": "Rule 1 text"},
    )

    # 2. Setup QA Lead (dataset 42)
    qa_user = User.objects.create_user("qa-lead-t038")
    RoleAssignment.objects.create(user=qa_user, role=Role.QA_LEAD, dataset_id=42)
    qa_emp = EmployeeIdentity.objects.create(
        employee_id="person-qa-lead", verified_at=timezone.now(), verified_by=admin
    )
    CvatIdentity.objects.create(user=qa_user, cvat_user_id=1704, employee=qa_emp)

    # 3. Setup second QA Lead (dataset 42) for multiple adjudications
    qa2_user = User.objects.create_user("qa-lead-2-t038")
    RoleAssignment.objects.create(user=qa2_user, role=Role.QA_LEAD, dataset_id=42)
    qa2_emp = EmployeeIdentity.objects.create(
        employee_id="person-qa-lead-2", verified_at=timezone.now(), verified_by=admin
    )
    CvatIdentity.objects.create(user=qa2_user, cvat_user_id=1705, employee=qa2_emp)

    # 4. Setup Super Admin
    sa_user = User.objects.create_user("sa-t038")
    RoleAssignment.objects.create(user=sa_user, role=Role.SUPER_ADMIN, dataset_id=None)
    sa_emp = EmployeeIdentity.objects.create(
        employee_id="person-super-admin", verified_at=timezone.now(), verified_by=admin
    )
    CvatIdentity.objects.create(user=sa_user, cvat_user_id=1706, employee=sa_emp)

    # 5. Create FrameReview and an escalated Issue
    frame_rev, _ = FrameReview.objects.get_or_create(
        run=run, snapshot_frame=frame, defaults={"state": FrameReview.State.IN_REVIEW}
    )

    issue = Issue.objects.create(
        frame_review=frame_rev,
        family=Issue.Family.E1,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.ESCALATED,
        anchor={
            "kind": "manual_region",
            "objects": [],
            "bbox": {"x1": 1, "y1": 1, "x2": 10, "y2": 10},
        },
        description="Escalated candidate issue",
        rule_ids=["RULE-01"],
        created_by=world["reviewer"],
    )

    # Reviewer decision that escalated the issue
    audit = AuditEvent.objects.create(
        actor=world["reviewer"],
        action="issue.escalate",
        object_type="issue",
        object_id=str(issue.pk),
        before={"state": "in_review"},
        after={"state": "escalated"},
        revision=run.snapshot.revision_sha256,
        reason="Uncertain about bbox classification",
    )
    esc_dec = ReviewDecision.objects.create(
        issue=issue,
        actor=world["reviewer"],
        actor_role="reviewer",
        action=ReviewDecision.Action.ESCALATE,
        revision=run.snapshot.revision_sha256,
        reason="Uncertain about bbox classification",
        rule_ids=["RULE-01"],
        audit_event=audit,
    )

    return {
        **world,
        "qa_lead": qa_user,
        "qa_lead_2": qa2_user,
        "super_admin": sa_user,
        "issue": issue,
        "escalator_decision": esc_dec,
        "rule": rule,
    }


def test_escalator_cannot_self_adjudicate(adj_world):
    """The user who escalated the issue cannot adjudicate it (403 SAME_REQUESTER_APPROVER)."""
    reviewer = adj_world["reviewer"]
    RoleAssignment.objects.create(user=reviewer, role=Role.QA_LEAD, dataset_id=42)

    issue = adj_world["issue"]
    resp = client(reviewer).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Self adjudicate"},
        format="json",
    )
    assert resp.status_code == 403, resp.data
    assert resp.data["code"] == "SAME_REQUESTER_APPROVER"

    audit = AuditEvent.objects.filter(
        actor=reviewer, action="issues.adjudicate.rejected", object_id=str(issue.pk)
    ).first()
    assert audit is not None


def test_same_employee_identity_alias_cannot_adjudicate(adj_world):
    """Two different accounts sharing the same EmployeeIdentity cannot adjudicate (FR-SEC-04)."""
    reviewer = adj_world["reviewer"]
    rev_identity = CvatIdentity.objects.get(user=reviewer)

    alias_qa = User.objects.create_user("qa-alias-same-person")
    RoleAssignment.objects.create(user=alias_qa, role=Role.QA_LEAD, dataset_id=42)
    CvatIdentity.objects.create(user=alias_qa, cvat_user_id=9999, employee=rev_identity.employee)

    issue = adj_world["issue"]
    resp = client(alias_qa).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Alias adjudication attempt"},
        format="json",
    )
    assert resp.status_code == 403, resp.data
    assert resp.data["code"] == "SAME_REQUESTER_APPROVER"


def test_adjudicator_without_verified_identity_forbidden(adj_world):
    """Adjudicator without verified EmployeeIdentity is denied 403 (fail-closed)."""
    unverified_qa = User.objects.create_user("unverified-qa")
    RoleAssignment.objects.create(user=unverified_qa, role=Role.QA_LEAD, dataset_id=42)

    issue = adj_world["issue"]
    resp = client(unverified_qa).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "No identity"},
        format="json",
    )
    assert resp.status_code == 403, resp.data
    assert resp.data["code"] == "IDENTITY_MAPPING_MISSING"


def test_wrong_role_adjudication_forbidden(adj_world):
    """Reviewer or annotator cannot adjudicate issues (403)."""
    other_reviewer = adj_world["other"]
    issue = adj_world["issue"]
    resp = client(other_reviewer).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Reviewer attempt"},
        format="json",
    )
    assert resp.status_code == 403, resp.data


def test_out_of_scope_dataset_forbidden(adj_world):
    """QA Lead assigned to another dataset cannot adjudicate issue in dataset 42."""
    admin = adj_world["admin"]
    out_qa = User.objects.create_user("out-of-scope-qa")
    RoleAssignment.objects.create(user=out_qa, role=Role.QA_LEAD, dataset_id=99)
    emp = EmployeeIdentity.objects.create(
        employee_id="person-out-qa", verified_at=timezone.now(), verified_by=admin
    )
    CvatIdentity.objects.create(user=out_qa, cvat_user_id=8888, employee=emp)

    issue = adj_world["issue"]
    resp = client(out_qa).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Out of scope"},
        format="json",
    )
    assert resp.status_code == 403, resp.data
    assert resp.data["code"] == "OUT_OF_SCOPE"


def test_valid_adjudication_confirm(adj_world):
    """Valid confirm adjudication transitions issue to confirmed, creates v1 case and audit."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    resp = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {
            "outcome": "confirm",
            "rule_id": "RULE-01",
            "correct_label": "car",
            "reason": "Clear missing vehicle",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    data = resp.data
    assert data["outcome"] == "confirm"
    assert data["rule_id"] == "RULE-01"
    assert data["correct_label"] == "car"
    assert data["case_version"] == "v1"
    assert data["actor_user_id"] == qa_lead.pk
    assert "created_at" in data

    # Verify issue state
    issue.refresh_from_db()
    assert issue.state == Issue.State.CONFIRMED

    # Verify persisted DecisionCase
    case = DecisionCase.objects.get(pk=data["id"])
    assert case.case_version == "v1"
    assert case.outcome == "confirm"
    assert case.actor_id == qa_lead.pk

    # Verify audit event
    audit = AuditEvent.objects.filter(
        actor=qa_lead, action="issue.adjudicate.confirm", object_id=str(issue.pk)
    ).first()
    assert audit is not None
    assert audit.before["state"] == "escalated"
    assert audit.after["state"] == "confirmed"
    assert audit.after["case_version"] == "v1"


def test_valid_adjudication_reject(adj_world):
    """Valid reject adjudication transitions issue to rejected."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    resp = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {
            "outcome": "reject",
            "rule_id": "RULE-01",
            "reason": "False alarm background noise",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["outcome"] == "reject"
    assert resp.data["case_version"] == "v1"

    issue.refresh_from_db()
    assert issue.state == Issue.State.REJECTED


def test_valid_adjudication_guideline_gap(adj_world):
    """guideline_gap outcome keeps issue in escalated state (FR-ESC-05 deferred)."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    resp = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {
            "outcome": "guideline_gap",
            "rule_id": "RULE-01",
            "reason": "Corner case not covered in current guideline version",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    assert resp.data["outcome"] == "guideline_gap"
    assert resp.data["case_version"] == "v1"

    issue.refresh_from_db()
    assert issue.state == Issue.State.ESCALATED
    gap = GuidelineGap.objects.get(issue=issue, rule_id="RULE-01")
    assert gap.status == GuidelineGap.Status.OPEN
    assert gap.guideline_version == "guide"


def test_adjudication_request_rework_creates_model_and_replays(adj_world, settings):
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]
    issue.severity = Issue.Severity.MEDIUM
    issue.save(update_fields=["severity"])
    settings.CVAT_BASE_URL = "http://cvat.test"
    settings.REWORK_DEFAULT_DUE_HOURS = 72
    key = str(uuid4())
    body = {
        "outcome": "confirm",
        "rule_id": "RULE-01",
        "reason": "Sửa annotation theo kết luận phân xử",
        "after_adjudication": "request_rework",
    }

    first = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert first.status_code == 201, first.data
    assert first.data["rework_id"] is not None
    rework = ReworkRequest.objects.get(pk=first.data["rework_id"])
    assert rework.issue_id == issue.pk
    assert rework.annotator_id == adj_world["author"].pk
    assert rework.cvat_deep_link.endswith("/tasks/200/jobs/100?frame=0")
    issue.refresh_from_db()
    assert issue.state == Issue.State.FIX_PENDING

    replay = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        body,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert replay.status_code == 201
    assert replay.data["id"] == first.data["id"]
    assert replay.data["rework_id"] == rework.pk
    assert DecisionCase.objects.filter(issue=issue).count() == 1
    assert ReworkRequest.objects.filter(issue=issue).count() == 1


def test_request_rework_requires_confirm_without_partial_write(adj_world):
    issue = adj_world["issue"]
    response = client(adj_world["qa_lead"]).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {
            "outcome": "reject",
            "rule_id": "RULE-01",
            "reason": "Không phải lỗi",
            "after_adjudication": "request_rework",
        },
        format="json",
    )
    assert response.status_code == 422
    assert not DecisionCase.objects.filter(issue=issue).exists()
    issue.refresh_from_db()
    assert issue.state == Issue.State.ESCALATED


def test_guideline_gap_collection_and_similar_cases(adj_world):
    issue = adj_world["issue"]
    created = client(adj_world["qa_lead"]).post(
        "/api/guideline-gaps/",
        {"rule_id": "RULE-01", "description": "Thiếu ví dụ cho trường hợp biên"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=str(uuid4()),
    )
    assert created.status_code == 201, created.data
    assert created.data["issue_id"] is None
    duplicate = client(adj_world["qa_lead"]).post(
        "/api/guideline-gaps/",
        {"rule_id": "RULE-01", "description": "Báo trùng gap đang mở"},
        format="json",
    )
    assert duplicate.status_code == 409
    listed = client(adj_world["reviewer"]).get(
        "/api/guideline-gaps/", {"status": "open", "rule_id": "RULE-01"}
    )
    assert listed.status_code == 200
    assert [row["id"] for row in listed.data["results"]] == [created.data["id"]]

    prior_issue = Issue.objects.create(
        frame_review=issue.frame_review,
        family=issue.family,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.CONFIRMED,
        anchor=issue.anchor,
        rule_ids=["RULE-01"],
        created_by=adj_world["reviewer"],
    )
    prior_case = DecisionCase.objects.create(
        issue=prior_issue,
        case_version="v1",
        outcome=DecisionCase.Outcome.CONFIRM,
        rule_id="RULE-01",
        reason="Case tương tự",
        actor=adj_world["qa_lead"],
    )
    similar = client(adj_world["reviewer"]).get(f"/api/issues/{issue.pk}/similar-cases/")
    assert similar.status_code == 200, similar.data
    assert similar.data["results"][0]["case"]["id"] == prior_case.pk
    assert similar.data["results"][0]["similarity"] == 1.0


def test_unsupported_outcome_rejected(adj_world):
    """Outcomes outside confirm, reject, guideline_gap are rejected 400 VALIDATION_ERROR."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    for bad_outcome in ["guideline_missing", "uncertain", "unknown"]:
        resp = client(qa_lead).post(
            f"/api/issues/{issue.pk}/adjudications/",
            {"outcome": bad_outcome, "rule_id": "RULE-01", "reason": "Test bad outcome"},
            format="json",
        )
        assert resp.status_code == 400, resp.data
        assert resp.data["code"] == "VALIDATION_ERROR"


def test_validation_rule_id_nonexistent(adj_world):
    """rule_id not present in snapshot guideline version is rejected 422 BUSINESS_RULE_UNMET."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    resp = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "NON-EXISTENT-RULE", "reason": "Rule test"},
        format="json",
    )
    assert resp.status_code == 422, resp.data
    assert resp.data["code"] == "BUSINESS_RULE_UNMET"


def test_validation_missing_reason(adj_world):
    """Missing or empty reason is rejected 400 VALIDATION_ERROR."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    resp = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "   "},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert resp.data["code"] == "VALIDATION_ERROR"


def test_super_admin_requires_override_reason(adj_world):
    """Super Admin acting without override_reason is rejected 400 (FR-SEC-06)."""
    sa = adj_world["super_admin"]
    issue = adj_world["issue"]

    resp = client(sa).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Admin decide"},
        format="json",
    )
    assert resp.status_code == 400, resp.data
    assert resp.data["code"] == "VALIDATION_ERROR"

    resp_ok = client(sa).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {
            "outcome": "confirm",
            "rule_id": "RULE-01",
            "reason": "Admin decide",
            "override_reason": "Urgent production review override",
        },
        format="json",
    )
    assert resp_ok.status_code == 201, resp_ok.data


def test_invalid_transition_from_non_escalated_rejected(adj_world):
    """Adjudicating non-escalated issue returns 409 without partial save."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    issue.state = Issue.State.PENDING_REVIEW
    issue.save(update_fields=["state"])

    initial_cases = DecisionCase.objects.count()
    resp = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Invalid transition test"},
        format="json",
    )
    assert resp.status_code == 409, resp.data
    assert resp.data["code"] == "INVALID_TRANSITION"

    assert DecisionCase.objects.count() == initial_cases
    issue.refresh_from_db()
    assert issue.state == Issue.State.PENDING_REVIEW


def test_decision_case_version_increments_and_lookups(adj_world):
    """Case version increments correctly (v1, v2) and UC-12 read lookups retrieve exact versions."""
    qa1 = adj_world["qa_lead"]
    qa2 = adj_world["qa_lead_2"]
    issue = adj_world["issue"]

    # 1. First adjudication with guideline_missing keeps issue escalated
    r1 = client(qa1).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "guideline_gap", "rule_id": "RULE-01", "reason": "Version 1"},
        format="json",
    )
    assert r1.status_code == 201
    assert r1.data["case_version"] == "v1"
    case1_id = r1.data["id"]

    # 2. Second adjudication with confirm transitions issue to confirmed
    r2 = client(qa2).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Version 2 after update"},
        format="json",
    )
    assert r2.status_code == 201
    assert r2.data["case_version"] == "v2"
    case2_id = r2.data["id"]

    # 3. Lookup by ID (UC-12)
    get1 = client(qa1).get(f"/api/decision-cases/{case1_id}/")
    assert get1.status_code == 200
    assert get1.data["case_version"] == "v1"
    assert get1.data["outcome"] == "guideline_gap"
    assert [h["case_version"] for h in get1.data["history"]] == ["v1", "v2"]

    get2 = client(qa1).get(f"/api/decision-cases/{case2_id}/")
    assert get2.status_code == 200
    assert get2.data["case_version"] == "v2"
    assert get2.data["outcome"] == "confirm"

    # 4. Lookup list by issue and rule_id
    list_issue = client(qa1).get(f"/api/decision-cases/?issue={issue.pk}")
    assert list_issue.status_code == 200
    assert len(list_issue.data["results"]) == 2
    versions = [c["case_version"] for c in list_issue.data["results"]]
    assert versions == ["v1", "v2"]

    list_rule = client(qa1).get("/api/decision-cases/?rule_id=RULE-01")
    assert list_rule.status_code == 200
    assert len(list_rule.data["results"]) == 2


def test_decision_case_history_append_only(adj_world):
    """DecisionCase is append-only; update/delete raise error and trigger blocks mutation."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    resp = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Append-only test"},
        format="json",
    )
    assert resp.status_code == 201
    case = DecisionCase.objects.get(pk=resp.data["id"])

    # 1. ORM update rejection
    with pytest.raises(ValueError, match="DecisionCase is append-only"):
        case.reason = "Modified reason"
        case.save()

    # 2. ORM delete rejection
    with pytest.raises(ValueError, match="DecisionCase is append-only"):
        case.delete()

    # 3. QuerySet update rejection
    with pytest.raises(ValueError, match="DecisionCase is append-only"):
        DecisionCase.objects.filter(pk=case.pk).update(reason="New reason")

    # 4. PostgreSQL trigger rejection on raw UPDATE
    with connection.cursor() as cursor:
        with pytest.raises(DatabaseError, match="review_decision_case is append-only"):
            cursor.execute(
                "UPDATE review_decision_case SET reason = 'hack' WHERE id = %s", [case.pk]
            )

    # 5. PostgreSQL trigger rejection on raw DELETE
    with connection.cursor() as cursor:
        with pytest.raises(DatabaseError, match="review_decision_case is append-only"):
            cursor.execute("DELETE FROM review_decision_case WHERE id = %s", [case.pk])


def test_audit_failure_rolls_back_transaction(adj_world, monkeypatch):
    """If audit logging fails, the whole adjudication transaction rolls back cleanly."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    def _failing_audit(**kwargs):
        raise RuntimeError("Simulated Audit Storage Failure")

    monkeypatch.setattr("review.adjudication_service.append_audit_event", _failing_audit)

    initial_cases = DecisionCase.objects.count()
    with pytest.raises(RuntimeError, match="Simulated Audit Storage Failure"):
        client(qa_lead).post(
            f"/api/issues/{issue.pk}/adjudications/",
            {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Rollback test"},
            format="json",
        )

    # State must not be updated, no case created
    issue.refresh_from_db()
    assert issue.state == Issue.State.ESCALATED
    assert DecisionCase.objects.count() == initial_cases


def test_idempotency_retry_same_response_and_conflict_on_changed_body(adj_world):
    """Idempotency-Key returns original response on replay, and 409 if body changes."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]
    key = str(uuid4())

    body1 = {"outcome": "confirm", "rule_id": "RULE-01", "reason": "Original reason"}
    resp1 = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        body1,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert resp1.status_code == 201

    # Replay with same body
    resp2 = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        body1,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert resp2.status_code == 200 or resp2.status_code == 201
    assert resp2.data["id"] == resp1.data["id"]
    assert resp2.data["case_version"] == resp1.data["case_version"]

    # Replay with changed body -> 409 IDEMPOTENCY_KEY_REUSED
    body2 = {"outcome": "reject", "rule_id": "RULE-01", "reason": "Different reason"}
    resp3 = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        body2,
        format="json",
        HTTP_IDEMPOTENCY_KEY=key,
    )
    assert resp3.status_code == 409
    assert resp3.data["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_adjudication_does_not_affect_kpi2b(adj_world):
    """Adjudication does not create reviewer confirm or affect KPI-2b numerator (DEC-009)."""
    qa_lead = adj_world["qa_lead"]
    issue = adj_world["issue"]

    resp = client(qa_lead).post(
        f"/api/issues/{issue.pk}/adjudications/",
        {"outcome": "confirm", "rule_id": "RULE-01", "reason": "KPI isolation test"},
        format="json",
    )
    assert resp.status_code == 201

    reviewer_confirms = ReviewDecision.objects.filter(
        issue=issue, actor_role="reviewer", action=ReviewDecision.Action.CONFIRM
    ).count()
    assert reviewer_confirms == 0


def test_get_escalations_list_and_cursor_pagination(adj_world):
    """GET /api/escalations/ lists issues oldest first, supports run filter and cursor."""
    qa_lead = adj_world["qa_lead"]
    run = adj_world["run"]
    issue1 = adj_world["issue"]

    issue2 = Issue.objects.create(
        frame_review=issue1.frame_review,
        family=Issue.Family.E2,
        origin=Issue.Origin.REVIEWER,
        state=Issue.State.ESCALATED,
        anchor={
            "kind": "manual_region",
            "objects": [],
            "bbox": {"x1": 2, "y1": 2, "x2": 20, "y2": 20},
        },
        description="Second escalated issue",
        rule_ids=["RULE-01"],
        created_by=adj_world["reviewer"],
    )

    resp = client(qa_lead).get(f"/api/escalations/?run={run.pk}")
    assert resp.status_code == 200, resp.data
    results = resp.data["results"]
    assert len(results) >= 2
    ids = [r["id"] for r in results]
    assert issue1.pk in ids
    assert issue2.pk in ids
    assert ids.index(issue1.pk) < ids.index(issue2.pk)

    resp_cursor = client(qa_lead).get(f"/api/escalations/?run={run.pk}&cursor={issue1.pk}")
    assert resp_cursor.status_code == 200
    cursor_ids = [r["id"] for r in resp_cursor.data["results"]]
    assert issue1.pk not in cursor_ids
    assert issue2.pk in cursor_ids


def test_concurrency_adjudication_atomic(adj_world):
    """Two concurrent adjudications for the same issue are serialized safely on PostgreSQL."""
    qa1 = adj_world["qa_lead"]
    qa2 = adj_world["qa_lead_2"]
    issue = adj_world["issue"]

    def _adjudicate(user, outcome, reason):
        r = client(user).post(
            f"/api/issues/{issue.pk}/adjudications/",
            {"outcome": outcome, "rule_id": "RULE-01", "reason": reason},
            format="json",
        )
        return r.status_code

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(_adjudicate, qa1, "confirm", "Concurrent 1")
        f2 = ex.submit(_adjudicate, qa2, "reject", "Concurrent 2")
        statuses = [f1.result(), f2.result()]

    connections.close_all()

    assert 201 in statuses
    assert 409 in statuses
    assert DecisionCase.objects.filter(issue=issue).count() == 1


def test_case_list_filters_version_outcome_pagination_and_legacy_mapping(adj_world, monkeypatch):
    qa1 = adj_world["qa_lead"]
    qa2 = adj_world["qa_lead_2"]
    issue = adj_world["issue"]
    for api_user, outcome in ((qa1, "guideline_gap"), (qa2, "confirm")):
        done = client(api_user).post(
            f"/api/issues/{issue.pk}/adjudications/",
            {"outcome": outcome, "rule_id": "RULE-01", "reason": "r"},
            format="json",
        )
        assert done.status_code == 201, done.data
    # A pre-R05 row persisted with the legacy outcome must read as the public enum.
    legacy = DecisionCase(
        issue=issue,
        case_version="v0",
        outcome="guideline_missing",
        rule_id="RULE-01",
        reason="legacy",
        actor=qa1,
    )
    legacy.save()

    api = client(qa1)
    gap = api.get("/api/decision-cases/?outcome=guideline_gap")
    assert sorted(c["case_version"] for c in gap.data["results"]) == ["v0", "v1"]
    assert {c["outcome"] for c in gap.data["results"]} == {"guideline_gap"}
    assert api.get("/api/decision-cases/?outcome=guideline_missing").status_code == 400
    one = api.get("/api/decision-cases/?version=v2")
    assert [c["outcome"] for c in one.data["results"]] == ["confirm"]
    assert api.get("/api/decision-cases/?issue=abc").status_code == 400

    monkeypatch.setattr("review.adjudication_service.CASE_PAGE_SIZE", 2)
    first = api.get(f"/api/decision-cases/?issue={issue.pk}")
    assert len(first.data["results"]) == 2 and first.data["next"]
    second = api.get(first.data["next"])
    seen = [c["id"] for c in first.data["results"] + second.data["results"]]
    assert len(seen) == len(set(seen)) == 3 and second.data["next"] is None
    # detail exposes the append-only history of the issue
    detail = api.get(f"/api/decision-cases/{legacy.pk}/")
    assert detail.data["outcome"] == "guideline_gap"
    assert len(detail.data["history"]) == 3


def test_case_list_out_of_scope_reviewer_sees_nothing(adj_world):
    outsider = User.objects.create_user("outsider-r05")
    assert client(outsider).get("/api/decision-cases/").status_code == 403
