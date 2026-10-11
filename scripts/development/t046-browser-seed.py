"""Seed isolated PostgreSQL database labelx_t046_browser for T-046 browser E2E verification.
Strictly ensures no write operations ever hit the develop database 'labelx'.
"""
from __future__ import annotations

import decimal
import json
import os
import sys
from pathlib import Path

EXPECTED_DATABASE = "labelx_t046_browser"
ROOT = Path(__file__).resolve().parents[2]
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
from review.models import DecisionCase, FrameReview, Issue, Lease, ReviewDecision  # noqa: E402
from runs.models import ConfigVersion, QCRun, RunRanking, RunRankingEntry  # noqa: E402
from snapshots.normalization import FrameExport, JobExport  # noqa: E402
from snapshots.services import create_locked_snapshot  # noqa: E402


def abort(message: str) -> None:
    raise SystemExit(f"T-046 seed refused: {message}")


configured_database = connection.settings_dict.get("NAME")
print(f"=== CHECKING TEST DATABASE: configured='{configured_database}', expected='{EXPECTED_DATABASE}' ===")
if os.environ.get("LABELX_T046_BROWSER_DATABASE") != EXPECTED_DATABASE:
    abort("LABELX_T046_BROWSER_DATABASE guard is missing or incorrect")
if configured_database != EXPECTED_DATABASE:
    abort(f"connected database is {configured_database!r}, expected {EXPECTED_DATABASE!r}")

password = os.environ.get("LABELX_T046_PASSWORD")
if not password or len(password) < 12:
    abort("LABELX_T046_PASSWORD must contain at least 12 characters")


@transaction.atomic
def seed() -> dict[str, object]:
    print("Clearing any prior seed data in labelx_t046_browser...")
    verifier = User.objects.create_user("t046_verifier", password=password)
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

    qalead = actor("t046_qalead", Role.QA_LEAD, 4601, "T046-QA")
    super_admin = actor("t046_superadmin", Role.SUPER_ADMIN, 4602, "T046-SA", dataset_id=None)
    reviewer = actor("t046_reviewer", Role.REVIEWER, 4603, "T046-REVIEWER")
    annotator = actor("t046_annotator", Role.ANNOTATOR, 4604, "T046-ANNOTATOR")
    actor("t046_unmapped_qa", Role.QA_LEAD, None, None)
    self_qa = actor("t046_self_qa", Role.QA_LEAD, 4606, "T046-SELF")
    actor("t046_outscope_qa", Role.QA_LEAD, 4607, "T046-OUT", dataset_id=99)
    reviewer_employee = CvatIdentity.objects.get(user=reviewer).employee
    actor(
        "t046_alias_qa",
        Role.QA_LEAD,
        4608,
        None,
        employee=reviewer_employee,
    )

    guideline = GuidelineVersion.objects.create(
        version_tag="t046-guide-v1",
        name="T-046 browser guideline",
        file_checksum="4" * 64,
    )
    rule_1 = GuidelineRule.objects.create(
        version=guideline,
        rule_id="RULE-01",
        section="Bbox geometry",
        content="Bounding box annotation must tightly encompass vehicle boundaries.",
    )
    rule_2 = GuidelineRule.objects.create(
        version=guideline,
        rule_id="RULE-02",
        section="Classification",
        content="Differentiate clearly between truck and large car.",
    )

    snapshot = create_locked_snapshot(
        dataset_id=42,
        created_by=verifier,
        taxonomy_version="t046-taxonomy",
        guideline_version=guideline.version_tag,
        provenance={"purpose": "T-046 browser E2E evidence"},
        jobs=[
            JobExport(
                cvat_job_id=46001,
                cvat_task_id=46002,
                assignee_cvat_user_id=4604,
                assignee_user_id=annotator.pk,
                source_updated_at="2026-10-11T00:00:00Z",
                annotations={
                    "shapes": [
                        {
                            "id": 1,
                            "label_id": 1,
                            "type": "rectangle",
                            "frame": 0,
                            "label": "car",
                            "points": [100.0, 150.0, 400.0, 350.0],
                            "occluded": False,
                            "z_order": 0,
                            "attributes": [],
                        }
                    ],
                    "tracks": [],
                },
                frames=[
                    FrameExport(
                        frame_index=0,
                        file_name="t046.jpg",
                        width=1280,
                        height=720,
                        media_bytes=b"t046-browser-frame-bytes",
                        media_storage_key="t046/browser.jpg",
                    )
                ],
            )
        ],
    )
    frame = snapshot.jobs.get().frames.get()
    revision = snapshot.revision_sha256
    config = ConfigVersion.objects.create(
        name="T-046 browser config",
        status=ConfigVersion.Status.PUBLISHED,
        payload={"iou_threshold": 0.85},
        created_by=verifier,
    )
    run = QCRun.objects.create(
        snapshot=snapshot,
        config_version=config,
        seed=46,
        status=QCRun.Status.COMPLETED,
        dataset_id=42,
        scope_hash="8" * 64,
        created_by=verifier,
    )

    risk_ranking = RunRanking.objects.create(
        run=run,
        source=RunRanking.Source.RISK,
        seed=46,
        score_version="v0",
        content_hash="a" * 64,
        ranking_hash="b" * 64,
    )
    random_ranking = RunRanking.objects.create(
        run=run,
        source=RunRanking.Source.RANDOM_AUDIT,
        seed=46,
        score_version="v0",
        content_hash="c" * 64,
        ranking_hash="d" * 64,
    )

    RunRankingEntry.objects.create(
        ranking=risk_ranking,
        snapshot_frame=frame,
        rank=1,
        score=decimal.Decimal("0.920000000000"),
        baseline_score=decimal.Decimal("0.920000000000"),
        missing_evidence=False,
        issue_counts={"E2": 1},
        explanation={"top_engine": "geometry_engine", "risk_factors": ["iou_below_threshold"]},
        tie_break_hash="e" * 64,
    )
    RunRankingEntry.objects.create(
        ranking=random_ranking,
        snapshot_frame=frame,
        rank=1,
        score=decimal.Decimal("0.500000000000"),
        baseline_score=decimal.Decimal("0.500000000000"),
        missing_evidence=False,
        issue_counts={"E2": 1},
        explanation={"sample_type": "uniform_random"},
        tie_break_hash="f" * 64,
    )

    frame_review = FrameReview.objects.create(
        run=run,
        snapshot_frame=frame,
        state=FrameReview.State.IN_REVIEW,
    )

    evidence_data = [
        {
            "engine": "geometry_overlap",
            "rule_id": "RULE-01",
            "expected": "car",
            "actual": "car",
            "prediction": "car",
            "confidence": 0.94,
            "iou": 0.62,
        }
    ]

    issue_1 = Issue.objects.create(
        frame_review=frame_review,
        family=Issue.Family.E2,
        origin=Issue.Origin.ENGINE,
        state=Issue.State.IN_REVIEW,
        anchor={
            "kind": "manual_region",
            "objects": [1],
            "bbox": {"x1": 100, "y1": 150, "x2": 400, "y2": 350},
            "uuid": "46000000-0000-4000-8000-000000000001",
        },
        description="Geometry engine detected IoU below 0.85 threshold",
        n_i=1,
        q_i=0.94,
        severity=Issue.Severity.MEDIUM,
        rule_ids=["RULE-01"],
        reviewer_evidence=evidence_data,
        links=[{"rel": "cvat", "href": "http://localhost:8080/tasks/46002/jobs/46001"}],
        created_by=verifier,
    )

    def create_escalation(escalator: User, reason: str, index: int, role: str = Role.REVIEWER) -> tuple[Issue, ReviewDecision]:
        issue = Issue.objects.create(
            frame_review=frame_review,
            family=Issue.Family.E2,
            origin=Issue.Origin.REVIEWER,
            state=Issue.State.ESCALATED,
            anchor={
                "kind": "manual_region",
                "objects": [index],
                "bbox": {"x1": 10 * index, "y1": 20 * index, "x2": 100 + 10 * index, "y2": 200 + 20 * index},
                "uuid": f"46000000-0000-4000-8000-0000000000{index:02d}",
            },
            description=reason,
            n_i=1,
            q_i=0.97,
            severity=Issue.Severity.MEDIUM,
            rule_ids=["RULE-01"],
            reviewer_evidence=evidence_data,
            links=[{"rel": "cvat", "href": "http://localhost:8080/tasks/46002/jobs/46001"}],
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
            actor_role=role,
            action=ReviewDecision.Action.ESCALATE,
            revision=revision,
            reason=reason,
            rule_ids=["RULE-01"],
            reference_match_status=ReviewDecision.ReferenceMatch.NOT_EVALUATED,
            audit_event=audit,
            idempotency_key=f"t046-esc-key-{index}",
            request_hash=f"{index}" * 64,
        )
        return issue, decision

    issue_2, decision_2 = create_escalation(reviewer, "Reviewer requested senior clarification on ambiguous geometry boundary", 2)
    issue_3, _ = create_escalation(self_qa, "Escalated by self QA user for self-adjudication guard check", 3, role=Role.QA_LEAD)
    issue_4, _ = create_escalation(reviewer, "Escalated by reviewer sharing employee identity for alias check", 4)

    lease = Lease.objects.create(
        frame_review=frame_review,
        holder=reviewer,
        queue_source="risk",
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )

    decision_case = DecisionCase.objects.create(
        issue=issue_2,
        review_decision=decision_2,
        case_version="v1",
        outcome=DecisionCase.Outcome.GUIDELINE_MISSING,
        rule_id="RULE-01",
        correct_label="car",
        reason="Historical case for reusable lookup: IoU under 0.85 requires rejection and fix",
        actor=qalead,
    )

    return {
        "status": "seeded",
        "database": EXPECTED_DATABASE,
        "run_id": run.pk,
        "frame_id": frame.pk,
        "issue_1_id": issue_1.pk,
        "issue_2_id": issue_2.pk,
        "issue_3_id": issue_3.pk,
        "issue_4_id": issue_4.pk,
        "decision_case_id": decision_case.pk,
        "lease_id": lease.pk,
        "revision": revision,
    }


if __name__ == "__main__":
    result = seed()
    meta_path = Path(__file__).resolve().parent / "t046-seed-meta.json"
    meta_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
