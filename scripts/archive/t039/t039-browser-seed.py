"""Seed an isolated PostgreSQL database for T-039 browser/API verification.

This script deliberately refuses to run against any database except the
dedicated ``labelx_t039_browser`` database.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

EXPECTED_DATABASE = "labelx_t039_browser"
ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "src" / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import User  # noqa: E402
from django.db import connection, transaction  # noqa: E402
from django.utils import timezone  # noqa: E402

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment  # noqa: E402
from audit.models import AuditEvent  # noqa: E402
from guideline.models import GuidelineRule, GuidelineVersion  # noqa: E402
from review.models import DecisionCase, FrameReview, Issue, ReviewDecision  # noqa: E402
from runs.models import ConfigVersion, QCRun  # noqa: E402
from snapshots.normalization import FrameExport, JobExport  # noqa: E402
from snapshots.services import create_locked_snapshot  # noqa: E402


def abort(message: str) -> None:
    raise SystemExit(f"T-039 seed refused: {message}")


configured_database = connection.settings_dict.get("NAME")
if os.environ.get("LABELX_T039_BROWSER_DATABASE") != EXPECTED_DATABASE:
    abort("LABELX_T039_BROWSER_DATABASE guard is missing or incorrect")
if configured_database != EXPECTED_DATABASE:
    abort(f"connected database is {configured_database!r}, expected {EXPECTED_DATABASE!r}")

password = os.environ.get("LABELX_T039_PASSWORD")
if not password or len(password) < 12:
    abort("LABELX_T039_PASSWORD must contain at least 12 characters")
if User.objects.filter(username__startswith="t039_").exists():
    abort("seed accounts already exist; recreate the isolated database before rerunning")


@transaction.atomic
def seed() -> dict[str, object]:
    verifier = User.objects.create_user("t039_verifier", password=password)
    RoleAssignment.objects.create(user=verifier, role=Role.SUPER_ADMIN, dataset_id=None)

    def actor(
        username: str,
        role: str,
        cvat_id: int | None,
        employee_id: str | None,
        *,
        dataset_id: int | None = 42,
        employee: EmployeeIdentity | None = None,
    ) -> User:
        user = User.objects.create_user(username, password=password)
        RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
        if cvat_id is not None:
            if employee is None and employee_id is not None:
                employee = EmployeeIdentity.objects.create(
                    employee_id=employee_id,
                    display_name=username,
                    verified_at=timezone.now(),
                    verified_by=verifier,
                )
            CvatIdentity.objects.create(
                user=user,
                cvat_user_id=cvat_id,
                cvat_username=username,
                employee=employee,
            )
        return user

    actor("t039_qalead", Role.QA_LEAD, 3901, "T039-QA")
    super_admin = actor("t039_superadmin", Role.SUPER_ADMIN, 3902, "T039-SA", dataset_id=None)
    reviewer = actor("t039_reviewer", Role.REVIEWER, 3903, "T039-REVIEWER")
    annotator = actor("t039_annotator", Role.ANNOTATOR, 3904, "T039-ANNOTATOR")
    actor("t039_unmapped_qa", Role.QA_LEAD, None, None)
    self_qa = actor("t039_self_qa", Role.QA_LEAD, 3906, "T039-SELF")
    actor("t039_outscope_qa", Role.QA_LEAD, 3907, "T039-OUT", dataset_id=99)
    reviewer_employee = CvatIdentity.objects.get(user=reviewer).employee
    actor(
        "t039_alias_qa",
        Role.QA_LEAD,
        3908,
        None,
        employee=reviewer_employee,
    )

    guideline = GuidelineVersion.objects.create(
        version_tag="t039-guide",
        name="T-039 browser guideline",
        file_checksum="3" * 64,
    )
    GuidelineRule.objects.create(
        version=guideline,
        rule_id="RULE-01",
        section="Browser evidence",
        content="A deterministic rule used only in the isolated T-039 browser database.",
    )

    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=verifier,
        taxonomy_version="t039-taxonomy",
        guideline_version=guideline.version_tag,
        provenance={"purpose": "T-039 browser evidence"},
        jobs=[
            JobExport(
                cvat_job_id=39001,
                cvat_task_id=39002,
                assignee_cvat_user_id=3904,
                assignee_user_id=annotator.pk,
                source_updated_at="2026-10-11T00:00:00Z",
                annotations={"shapes": [], "tracks": []},
                frames=[
                    FrameExport(
                        frame_index=0,
                        file_name="t039.jpg",
                        width=1280,
                        height=720,
                        media_bytes=b"t039-browser-frame",
                        media_storage_key="t039/browser.jpg",
                    )
                ],
            )
        ],
    )
    frame = snapshot.jobs.get().frames.get()
    revision = snapshot.revision_sha256
    config = ConfigVersion.objects.create(
        name="T-039 browser config",
        status=ConfigVersion.Status.PUBLISHED,
        payload={},
        created_by=verifier,
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=config,
        seed=39,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        scope_hash="7" * 64,
        created_by=verifier,
    )
    frame_review = FrameReview.objects.create(run=run, snapshot_frame=frame)

    evidence = [
        {
            "engine": "reference_match",
            "rule_id": "RULE-01",
            "expected": "car",
            "actual": "truck",
            "prediction": "car",
            "confidence": 0.97,
            "iou": 0.42,
        }
    ]

    def escalation(escalator: User, reason: str, index: int) -> tuple[Issue, ReviewDecision]:
        issue = Issue.objects.create(
            frame_review=frame_review,
            family=Issue.Family.E2,
            origin=Issue.Origin.REVIEWER,
            state=Issue.State.ESCALATED,
            anchor={
                "kind": "manual_region",
                "objects": [index],
                "bbox": {"x1": 10, "y1": 20, "x2": 110, "y2": 220},
                "policy_version": "anchor-t039-v1",
            },
            description=reason,
            n_i=1,
            q_i=0.97,
            severity=Issue.Severity.MEDIUM,
            rule_ids=["RULE-01"],
            reviewer_evidence=evidence,
            links=[{"rel": "cvat", "href": "http://localhost:8080/tasks/39002/jobs/39001"}],
            created_by=escalator,
        )
        audit = AuditEvent.objects.create(
            actor=escalator,
            action="issue.escalate",
            object_type="issue",
            object_id=str(issue.pk),
            before={"state": "in_review"},
            after={"state": "escalated"},
            revision=revision,
            reason=reason,
        )
        decision = ReviewDecision.objects.create(
            issue=issue,
            actor=escalator,
            actor_role=Role.REVIEWER,
            action=ReviewDecision.Action.ESCALATE,
            revision=revision,
            reason=reason,
            rule_ids=["RULE-01"],
            reference_version="reference-t039-v1",
            reference_match_status=ReviewDecision.ReferenceMatch.NOT_MATCHED,
            reference_error_ids=["E2"],
            audit_event=audit,
        )
        return issue, decision

    primary, primary_decision = escalation(reviewer, "Primary browser escalation", 1)
    DecisionCase.objects.create(
        issue=primary,
        review_decision=primary_decision,
        case_version="v1",
        outcome=DecisionCase.Outcome.GUIDELINE_MISSING,
        rule_id="RULE-01",
        correct_label="car",
        reason="Historical case for reusable lookup",
        actor=super_admin,
    )
    self_issue, _ = escalation(self_qa, "Same-account separation check", 2)
    alias_issue, _ = escalation(reviewer, "Natural-person alias separation check", 3)
    # 48 fillers make 51 total escalations and exercise the cursor's second page.
    fillers = [
        escalation(reviewer, f"Pagination filler {number:02d}", number)[0]
        for number in range(4, 52)
    ]

    return {
        "database": configured_database,
        "run_id": run.pk,
        "primary_issue_id": primary.pk,
        "self_issue_id": self_issue.pk,
        "alias_issue_id": alias_issue.pk,
        "last_issue_id": fillers[-1].pk,
        "escalation_count": Issue.objects.filter(state=Issue.State.ESCALATED).count(),
        "accounts": [
            "t039_qalead",
            "t039_superadmin",
            "t039_reviewer",
            "t039_annotator",
            "t039_unmapped_qa",
            "t039_self_qa",
            "t039_outscope_qa",
            "t039_alias_qa",
        ],
    }


print(json.dumps(seed(), indent=2, sort_keys=True))
