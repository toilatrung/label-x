"""Comprehensive tests for RBAC, dataset scope, and workflow permissions (T-012, Issue #41).

Covers all Acceptance Criteria and Review Findings:
- AC 1 & Finding 7: Table-driven role tests across all 7 roles derived from rbac-matrix.
- AC 1 & Finding 2: Strict RoleAssignment lookup; superuser without RoleAssignment is rejected.
- AC 1 & Finding 3: Fail-closed dataset scope: missing, invalid type, and conflicting dataset_id.
- AC 2 & Finding 4: Separation of duties and anti-self-review fail-closed when identity is missing.
- AC 2 & DEC-011: Unique cvat_user_id prevents duplicate mapping; second account fails closed.
- AC 2: Non-overridable anti-self-review invariant (Super Admin cannot self-review).
- AC 3 & Finding 5: Override flow: view automatically labels audit with is_override=True.
- AC 3 & Finding 5: Override without reason returns 422 and records rejection audit.
- WorkflowPermissions API endpoint returns 7 roles in matrix and workflow rules.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.urls import include, path
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.views import APIView

from accounts.models import CvatIdentity, Role, RoleAssignment
from accounts.permissions import (
    HasRoleAndDatasetScope,
    append_action_audit,
    check_anti_self_review,
    check_separation_of_duties,
    check_super_admin_override,
)
from audit.models import AuditEvent
from config.exceptions import ApiError

User = get_user_model()
pytestmark = pytest.mark.django_db(transaction=True)


class DummyRunOperationView(APIView):
    """Simulates /api/runs/ operation requiring QA Lead or Super Admin in dataset scope."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = [Role.QA_LEAD, Role.SUPER_ADMIN]
    action_name = "run.create"
    requires_dataset = True

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(
            {"status": "created", "action": "run.create"}, status=status.HTTP_201_CREATED
        )


class DummyReviewOperationView(APIView):
    """Simulates review workspace operation requiring Reviewer, QA Lead, or Super Admin."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = [Role.REVIEWER, Role.QA_LEAD, Role.SUPER_ADMIN]
    action_name = "review.access"
    requires_dataset = True

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok", "action": "review.access"})

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok", "action": "review.access"})


class DummyDatasetAccessView(APIView):
    """Simulates dataset read operation open to all roles in dataset scope (datasets_list)."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = [
        Role.ANNOTATOR,
        Role.REVIEWER,
        Role.QA_LEAD,
        Role.QC_ADMIN,
        Role.SUPER_ADMIN,
        Role.PRODUCT_OWNER,
        Role.DATA_MODEL_OWNER,
    ]
    action_name = "dataset.read"
    requires_dataset = True

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok", "action": "dataset.read"})

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok", "action": "dataset.read"})


class DummySystemWideView(APIView):
    """Simulates a system-wide view that does not require dataset scope."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = [Role.QA_LEAD, Role.QC_ADMIN, Role.SUPER_ADMIN]
    action_name = "system.view"
    requires_dataset = False
    scope_type = "system"

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok", "action": "system.view"})

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok", "action": "system.view"})


class DummyOverrideActionView(APIView):
    """Representative view for operations supporting Super Admin override (Finding 5)."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = [Role.QA_LEAD, Role.SUPER_ADMIN]
    action_name = "run.override_action"
    requires_dataset = True

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        check_super_admin_override(request=request, action=self.action_name)
        with transaction.atomic():
            append_action_audit(
                request=request,
                action=self.action_name,
                object_type="dataset",
                object_id=request.data.get("dataset_id", "global"),
                after={"status": "completed", "dataset_id": request.data.get("dataset_id")},
            )
        return Response({"status": "completed"}, status=status.HTTP_200_OK)


class DummyRunDetailView(APIView):
    """Object endpoint: pk is run_id (42), real dataset_id is 10 (Findings 7 & 8)."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = [Role.QA_LEAD, Role.SUPER_ADMIN]
    action_name = "run.detail"
    requires_dataset = True

    def get_dataset_id(self, request: Request) -> int | None:
        run_id = self.kwargs.get("pk")
        if run_id == 42:
            return 10
        return None

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok", "run_id": kwargs.get("pk"), "dataset_id": 10})

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok", "run_id": kwargs.get("pk"), "dataset_id": 10})


class DummyUnconfiguredView(APIView):
    """View that forgot to declare allowed_roles (Review Finding 6)."""

    permission_classes = [HasRoleAndDatasetScope]
    requires_dataset = False
    scope_type = "system"

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response({"status": "ok"})


class DummyFailingMutationView(APIView):
    """View where mutation fails after writing audit inside atomic block (Review Finding 5)."""

    permission_classes = [HasRoleAndDatasetScope]
    allowed_roles = [Role.SUPER_ADMIN]
    action_name = "test.failing_mutation"
    requires_dataset = False
    scope_type = "system"

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        with transaction.atomic():
            append_action_audit(
                request=request,
                action=self.action_name,
                object_type="operation",
                object_id="fail_test",
                after={"status": "in_progress"},
            )
            raise RuntimeError("Database mutation failed abruptly!")


# Test URL configuration for full pipeline integration tests
urlpatterns = [
    path("api/auth/", include("accounts.urls")),
    path("api/test/override/", DummyOverrideActionView.as_view(), name="test-override"),
    path("api/test/run/<int:pk>/", DummyRunDetailView.as_view(), name="test-run-detail"),
    path("api/test/unconfigured/", DummyUnconfiguredView.as_view(), name="test-unconfigured"),
    path(
        "api/test/failing-mutation/",
        DummyFailingMutationView.as_view(),
        name="test-failing-mutation",
    ),
]


def _create_user(username_prefix: str) -> Any:
    uid = uuid.uuid4().hex[:6]
    return User.objects.create_user(
        username=f"{username_prefix}_{uid}",
        email=f"{username_prefix}_{uid}@labelx.dev",
        password="TestPassword123!",
    )


# ---------------------------------------------------------------------------
# AC 1 & Finding 7: Table-driven role tests across all 7 roles from rbac-matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role,allowed_view_cls,forbidden_view_cls,is_system_wide",
    [
        (Role.ANNOTATOR, DummyDatasetAccessView, DummyRunOperationView, False),
        (Role.REVIEWER, DummyReviewOperationView, DummyRunOperationView, False),
        (Role.QA_LEAD, DummyRunOperationView, None, False),
        (Role.QC_ADMIN, DummySystemWideView, DummyRunOperationView, True),
        (Role.SUPER_ADMIN, DummyRunOperationView, None, True),
        (Role.PRODUCT_OWNER, DummyDatasetAccessView, DummyReviewOperationView, False),
        (Role.DATA_MODEL_OWNER, DummyDatasetAccessView, DummyReviewOperationView, False),
    ],
)
def test_rbac_matrix_all_7_roles_table_driven(
    role: Role,
    allowed_view_cls: type[APIView] | None,
    forbidden_view_cls: type[APIView] | None,
    is_system_wide: bool,
) -> None:
    """Every role has explicit allowed, forbidden, and scope boundary checks per rbac-matrix."""
    factory = APIRequestFactory()
    user = _create_user(f"user_{role.value}")
    dataset_scope = None if is_system_wide else 10
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_scope)

    # 1. Allowed operation in scope
    if allowed_view_cls is not None:
        req = factory.post("/api/test/?dataset_id=10", {"dataset_id": 10}, format="json")
        req.user = user
        view = allowed_view_cls.as_view()
        resp = view(req)
        assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)

    # 2. Forbidden operation
    if forbidden_view_cls is not None:
        req_forbid = factory.post("/api/test/?dataset_id=10", {"dataset_id": 10}, format="json")
        req_forbid.user = user
        view_forbid = forbidden_view_cls.as_view()

        resp_forbid = view_forbid(req_forbid)
        assert resp_forbid.status_code == status.HTTP_403_FORBIDDEN
        assert resp_forbid.data["code"] == "FORBIDDEN"

        event = AuditEvent.objects.filter(actor=user).order_by("-id").first()
        assert event is not None
        assert event.action.endswith(".rejected")
        assert event.after["code"] == "FORBIDDEN"

    # 3. Out-of-scope check (for scoped roles)
    if not is_system_wide and allowed_view_cls is not None:
        req_out = factory.post("/api/test/?dataset_id=999", {"dataset_id": 999}, format="json")
        req_out.user = user
        view_out = allowed_view_cls.as_view()

        resp_out = view_out(req_out)
        assert resp_out.status_code == status.HTTP_403_FORBIDDEN
        assert resp_out.data["code"] == "OUT_OF_SCOPE"

        event_out = AuditEvent.objects.filter(actor=user).order_by("-id").first()
        assert event_out is not None
        assert event_out.after["code"] == "OUT_OF_SCOPE"


# ---------------------------------------------------------------------------
# AC 1 & Finding 2: Strict RoleAssignment lookup; NO is_superuser bypass
# ---------------------------------------------------------------------------


def test_superuser_without_role_assignment_is_rejected_403():
    """Superuser without RoleAssignment has no bypass and must be rejected 403."""
    factory = APIRequestFactory()
    admin_user = _create_user("super_bypass")
    admin_user.is_superuser = True
    admin_user.save()

    request = factory.post("/api/runs/?dataset_id=10", {"dataset_id": 10}, format="json")
    request.user = admin_user
    view = DummyRunOperationView.as_view()

    response = view(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "FORBIDDEN"

    event = AuditEvent.objects.filter(actor=admin_user).order_by("-id").first()
    assert event is not None
    assert event.after["code"] == "FORBIDDEN"


def test_superuser_without_super_admin_role_cannot_override():
    """Superuser flag without Role.SUPER_ADMIN assignment cannot override."""
    factory = APIRequestFactory()
    user = _create_user("su_no_role")
    user.is_superuser = True
    user.save()

    request = factory.post(
        "/api/action/?override=true&override_reason=Emergency",
        {"override": True, "override_reason": "Emergency"},
    )
    request.user = user

    with pytest.raises(ApiError) as exc_info:
        check_super_admin_override(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "FORBIDDEN"


# ---------------------------------------------------------------------------
# AC 1 & Finding 3: Fail-closed dataset scope validation
# ---------------------------------------------------------------------------


def test_dataset_scope_missing_dataset_id_rejected_403_out_of_scope():
    """View requiring dataset scope without dataset_id fails closed with 403 OUT_OF_SCOPE."""
    factory = APIRequestFactory()
    qa_lead = _create_user("qa_missing_ds")
    RoleAssignment.objects.create(user=qa_lead, role=Role.QA_LEAD, dataset_id=10)

    request = factory.post("/api/runs/", {}, format="json")
    request.user = qa_lead
    view = DummyRunOperationView.as_view()

    response = view(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "OUT_OF_SCOPE"

    event = AuditEvent.objects.filter(actor=qa_lead).order_by("-id").first()
    assert event is not None
    assert event.after["code"] == "OUT_OF_SCOPE"


def test_dataset_scope_invalid_dataset_id_type_rejected_400_validation_error():
    """dataset_id with non-integer type is rejected with 400 VALIDATION_ERROR."""
    factory = APIRequestFactory()
    qa_lead = _create_user("qa_invalid_type")
    RoleAssignment.objects.create(user=qa_lead, role=Role.QA_LEAD, dataset_id=10)

    request = factory.post("/api/runs/?dataset_id=abc", {"dataset_id": "abc"}, format="json")
    request.user = qa_lead
    view = DummyRunOperationView.as_view()

    response = view(request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "VALIDATION_ERROR"

    event = AuditEvent.objects.filter(actor=qa_lead).order_by("-id").first()
    assert event is not None
    assert event.after["code"] == "VALIDATION_ERROR"


def test_dataset_scope_conflicting_dataset_id_rejected_400_validation_error():
    """Conflicting dataset_id between query params and body is rejected with 400."""
    factory = APIRequestFactory()
    qa_lead = _create_user("qa_conflict")
    RoleAssignment.objects.create(user=qa_lead, role=Role.QA_LEAD, dataset_id=10)

    request = factory.post("/api/runs/?dataset_id=10", {"dataset_id": 20}, format="json")
    request.user = qa_lead
    view = DummyRunOperationView.as_view()

    response = view(request)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "VALIDATION_ERROR"

    event = AuditEvent.objects.filter(actor=qa_lead).order_by("-id").first()
    assert event is not None
    assert event.after["code"] == "VALIDATION_ERROR"


def test_system_wide_view_does_not_require_dataset_id():
    """System-wide view explicitly declaring requires_dataset=False succeeds without dataset_id."""
    factory = APIRequestFactory()
    qa_lead = _create_user("qa_system_view")
    RoleAssignment.objects.create(user=qa_lead, role=Role.QA_LEAD, dataset_id=10)

    request = factory.get("/api/system/")
    request.user = qa_lead
    view = DummySystemWideView.as_view()

    response = view(request)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "ok"


def test_unauthenticated_user_returns_403_not_authenticated():
    client = APIClient()
    response = client.get("/api/auth/session/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["code"] == "NOT_AUTHENTICATED"


# ---------------------------------------------------------------------------
# AC 2: Separation of Duties & Anti-Self-Review
# ---------------------------------------------------------------------------


def test_cvat_user_id_unique_constraint_prevents_duplicate_mapping():
    """Schema T-011 constraint: PositiveIntegerField(unique=True) prevents duplicate mapping."""
    user1 = _create_user("user_cvat_primary")
    user2 = _create_user("user_cvat_secondary")
    CvatIdentity.objects.create(user=user1, cvat_user_id=12345, cvat_username="worker12345")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CvatIdentity.objects.create(
                user=user2,
                cvat_user_id=12345,
                cvat_username="worker12345_alt",
            )


def test_second_account_missing_mapping_fails_closed_when_adjudicating_with_audit():
    """Second account without mapping fails-closed with 403 and records audit event."""
    factory = APIRequestFactory()
    user2 = _create_user("user_second_account_unmapped")
    RoleAssignment.objects.create(user=user2, role=Role.REVIEWER, dataset_id=10)

    request = factory.post("/api/reviews/claim/")
    request.user = user2

    with pytest.raises(ApiError) as exc_info:
        check_anti_self_review(
            request=request,
            author_cvat_user_id=888,
            action="review.claim",
            object_id="snapshot-001",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"

    event = AuditEvent.objects.filter(actor=user2).order_by("-id").first()
    assert event is not None
    assert event.action == "review.claim.rejected"
    assert event.after["code"] == "IDENTITY_MAPPING_MISSING"
    assert event.object_id == "snapshot-001"


def test_anti_self_review_reviewer_matches_author_rejected():
    factory = APIRequestFactory()
    reviewer = _create_user("reviewer_author")
    CvatIdentity.objects.create(user=reviewer, cvat_user_id=101, cvat_username="author101")

    request = factory.post("/api/reviews/claim/")
    request.user = reviewer

    with pytest.raises(ApiError) as exc_info:
        check_anti_self_review(
            request=request,
            author_cvat_user_id=101,
            action="review.claim",
            object_id="frame-555",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "SELF_REVIEW_FORBIDDEN"

    event = AuditEvent.objects.filter(actor=reviewer).order_by("-id").first()
    assert event is not None
    assert event.action == "review.claim.rejected"
    assert event.after["code"] == "SELF_REVIEW_FORBIDDEN"
    assert event.object_id == "frame-555"


def test_anti_self_review_super_admin_with_override_cannot_self_review():
    factory = APIRequestFactory()
    admin = _create_user("super_admin_self")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)
    CvatIdentity.objects.create(user=admin, cvat_user_id=999, cvat_username="admin999")

    request = factory.post(
        "/api/reviews/claim/?override=true&override_reason=Urgent+QA",
        {
            "override": True,
            "override_reason": "Urgent QA",
        },
    )
    request.user = admin

    with pytest.raises(ApiError) as exc_info:
        check_anti_self_review(
            request=request,
            author_cvat_user_id=999,
            action="review.claim",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "SELF_REVIEW_FORBIDDEN"


def test_separation_of_duties_same_labelx_user_rejected():
    factory = APIRequestFactory()
    user = _create_user("requester_and_approver")

    request = factory.post("/api/adjudicate/")
    request.user = user

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=user.pk,
            action="approval.adjudicate",
            object_id="req-123",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "SAME_REQUESTER_APPROVER"

    event = AuditEvent.objects.filter(actor=user).order_by("-id").first()
    assert event is not None
    assert event.action == "approval.adjudicate.rejected"
    assert event.after["code"] == "SAME_REQUESTER_APPROVER"


def test_separation_of_duties_approver_missing_identity_fails_closed():
    """Approver missing CvatIdentity when comparing identities fails closed with 403."""
    factory = APIRequestFactory()
    approver = _create_user("approver_no_cvat")

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=99999,
            requester_cvat_user_id=555,
            action="approval.adjudicate",
            object_id="req-missing-id",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"

    event = AuditEvent.objects.filter(actor=approver).order_by("-id").first()
    assert event is not None
    assert event.action == "approval.adjudicate.rejected"
    assert event.after["code"] == "IDENTITY_MAPPING_MISSING"


def test_separation_of_duties_cross_account_same_person_rejected():
    factory = APIRequestFactory()
    approver = _create_user("approver_user")
    CvatIdentity.objects.create(user=approver, cvat_user_id=777, cvat_username="cvat777")

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=99999,
            requester_cvat_user_id=777,
            action="approval.adjudicate",
            object_id="req-789",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "SAME_REQUESTER_APPROVER"

    event = AuditEvent.objects.filter(actor=approver).order_by("-id").first()
    assert event is not None
    assert event.action == "approval.adjudicate.rejected"
    assert event.after["code"] == "SAME_REQUESTER_APPROVER"


# ---------------------------------------------------------------------------
# AC 3 & Finding 5: Super Admin Override integration flow & audit labeling
# ---------------------------------------------------------------------------


def test_super_admin_override_without_reason_returns_422_and_records_audit():
    """Super Admin override without reason returns 422 and records audit rejection."""
    factory = APIRequestFactory()
    admin = _create_user("super_admin_no_reason")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)

    request = factory.post("/api/action/?override=true", {"override": True})
    request.user = admin

    with pytest.raises(ApiError) as exc_info:
        check_super_admin_override(request=request)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.error_code == "BUSINESS_RULE_UNMET"

    event = AuditEvent.objects.filter(actor=admin).order_by("-id").first()
    assert event is not None
    assert event.action == "override.action.rejected"
    assert event.after["code"] == "BUSINESS_RULE_UNMET"


def test_super_admin_override_whitespace_reason_returns_422_and_records_audit():
    """Super Admin override with whitespace-only reason returns 422 and records audit."""
    factory = APIRequestFactory()
    admin = _create_user("super_admin_blank_reason")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)

    request = factory.post(
        "/api/action/?override=true&override_reason=   ",
        {
            "override": True,
            "override_reason": "   ",
        },
    )
    request.user = admin

    with pytest.raises(ApiError) as exc_info:
        check_super_admin_override(request=request)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.error_code == "BUSINESS_RULE_UNMET"

    event = AuditEvent.objects.filter(actor=admin).order_by("-id").first()
    assert event is not None
    assert event.after["code"] == "BUSINESS_RULE_UNMET"


def test_non_super_admin_attempting_override_returns_403_and_records_audit():
    factory = APIRequestFactory()
    reviewer = _create_user("reviewer_pretend_admin")
    RoleAssignment.objects.create(user=reviewer, role=Role.REVIEWER, dataset_id=10)

    request = factory.post(
        "/api/action/?override=true&override_reason=ValidReason",
        {
            "override": True,
            "override_reason": "ValidReason",
        },
    )
    request.user = reviewer

    with pytest.raises(ApiError) as exc_info:
        check_super_admin_override(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "FORBIDDEN"

    event = AuditEvent.objects.filter(actor=reviewer).order_by("-id").first()
    assert event is not None
    assert event.action == "override.action.rejected"
    assert event.after["code"] == "FORBIDDEN"


def test_super_admin_override_representative_view_succeeds_and_labels_audit():
    """Representative view executes override and labels audit with is_override=True."""
    factory = APIRequestFactory()
    admin = _create_user("super_admin_view_override")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)

    reason_str = "Khẩn cấp giải phóng lô ảnh theo chỉ đạo PO"
    request = factory.post(
        "/api/override-action/?dataset_id=10&override=true",
        {
            "dataset_id": 10,
            "override": True,
            "override_reason": reason_str,
        },
        format="json",
    )
    request.user = admin
    view = DummyOverrideActionView.as_view()

    response = view(request)
    assert response.status_code == status.HTTP_200_OK

    event = AuditEvent.objects.filter(actor=admin).order_by("-id").first()
    assert event is not None
    assert event.action == "run.override_action"
    assert event.after.get("is_override") is True
    assert event.reason == reason_str


# ---------------------------------------------------------------------------
# WorkflowPermissions API Endpoint
# ---------------------------------------------------------------------------


def test_workflow_permissions_endpoint_serves_matrix_and_rules():
    client = APIClient()
    user = _create_user("qa_user")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=5)
    client.force_authenticate(user=user)

    response = client.get("/api/auth/workflow-permissions/")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "matrix" in data
    assert "rules" in data
    assert "user_roles" in data
    assert len(data["matrix"]) > 0
    assert len(data["rules"]) > 0
    assert data["user_roles"] == [{"role": "qa_lead", "dataset_id": 5}]

    # Verify all 7 roles are represented in matrix entries
    for item in data["matrix"]:
        roles_dict = item["roles"]
        assert len(roles_dict) == 7
        assert "product_owner" in roles_dict
        assert "data_model_owner" in roles_dict

    rules_dict = {r["rule"]: r for r in data["rules"]}
    assert "anti_self_review" in rules_dict
    assert "super_admin_override_reason" in rules_dict
    assert "separation_of_duties" in rules_dict


# ---------------------------------------------------------------------------
# Review P1: Full Integration Pipeline Tests with ATOMIC_REQUESTS=True via APIClient
# ---------------------------------------------------------------------------


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_403_workflow_permissions_through_atomic_requests_pipeline():
    """403 rejection through full Django HTTP stack with ATOMIC_REQUESTS persists audit."""
    client = APIClient()
    annotator = _create_user("annotator_pipeline_test")
    RoleAssignment.objects.create(user=annotator, role=Role.ANNOTATOR, dataset_id=1)
    client.force_authenticate(user=annotator)

    response = client.get("/api/auth/workflow-permissions/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "FORBIDDEN"

    # AuditRejectionMiddleware committed the rejection audit in independent transaction
    event = AuditEvent.objects.filter(
        actor=annotator, action="auth_workflow_permissions.rejected"
    ).first()
    assert event is not None
    assert event.after["code"] == "FORBIDDEN"


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_422_override_missing_reason_through_atomic_requests_pipeline():
    """422 override rejection through full Django HTTP stack persists rejection audit."""
    client = APIClient()
    admin = _create_user("admin_pipeline_422")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)
    client.force_authenticate(user=admin)

    response = client.post(
        "/api/test/override/?dataset_id=10",
        {"override": True, "dataset_id": 10},
        format="json",
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.data["code"] == "BUSINESS_RULE_UNMET"

    event = AuditEvent.objects.filter(actor=admin, action="run.override_action.rejected").first()
    assert event is not None
    assert event.after["code"] == "BUSINESS_RULE_UNMET"


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_mutation_and_audit_rollback_together_on_failure():
    """Mutation and mutation audit roll back together inside atomic block on failure (NFR-08)."""
    client = APIClient()
    admin = _create_user("admin_rollback_test")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)
    client.force_authenticate(user=admin)

    with pytest.raises(RuntimeError):
        client.post("/api/test/failing-mutation/", format="json")

    # Mutation audit must be rolled back and NOT exist in database
    mutation_audit_exists = AuditEvent.objects.filter(
        actor=admin, action="test.failing_mutation"
    ).exists()
    assert not mutation_audit_exists


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_rejection_audit_not_duplicated():
    """Rejection audit is committed exactly once per rejected request."""
    client = APIClient()
    annotator = _create_user("annotator_no_dup")
    RoleAssignment.objects.create(user=annotator, role=Role.ANNOTATOR, dataset_id=1)
    client.force_authenticate(user=annotator)

    response = client.get("/api/auth/workflow-permissions/")
    assert response.status_code == status.HTTP_403_FORBIDDEN

    count = AuditEvent.objects.filter(
        actor=annotator, action="auth_workflow_permissions.rejected"
    ).count()
    assert count == 1


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_rejection_audit_does_not_collect_query_string_secrets():
    """Rejection audit records path only and does not collect query string secrets.

    Note: Payload redaction ([REDACTED]) of before/after/reason dictionaries is
    implemented and proven by T-013 test suite
    (tests/audit/test_audit_log.py:test_snapshots_and_reason_are_redacted_before_storage).
    This test verifies rejection audit records request.path purely without leaking
    query string parameters into audit storage.
    """
    client = APIClient()
    reviewer = _create_user("reviewer_secret_test")
    RoleAssignment.objects.create(user=reviewer, role=Role.REVIEWER, dataset_id=1)
    client.force_authenticate(user=reviewer)

    query_url = "/api/test/override/?dataset_id=1&override=true&secret_token=SuperSecretToken123"
    response = client.post(
        query_url,
        {"override": True},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN

    event = AuditEvent.objects.filter(actor=reviewer, action="run.override_action.rejected").first()
    assert event is not None
    # request.path only records the clean URL path without query string
    assert event.after.get("path") == "/api/test/override/"
    assert "SuperSecretToken123" not in str(event.after)
    assert "SuperSecretToken123" not in str(event.reason)


# ---------------------------------------------------------------------------
# Review P1: Fail-Closed on Missing Configuration (Finding 6)
# ---------------------------------------------------------------------------


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_view_missing_allowed_roles_raises_improperly_configured():
    """HasRoleAndDatasetScope raises ImproperlyConfigured when allowed_roles is missing."""
    client = APIClient()
    admin = _create_user("admin_unconfigured")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)
    client.force_authenticate(user=admin)

    with pytest.raises(ImproperlyConfigured) as exc_info:
        client.get("/api/test/unconfigured/")

    assert "chưa cấu hình allowed_roles" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Review P1: Authoritative Server Hook vs Generic pk (Findings 7 & 8)
# ---------------------------------------------------------------------------


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_object_endpoint_server_hook_resolves_real_dataset_id_not_pk():
    """Server hook get_dataset_id resolves real dataset_id (10), ignoring run pk (42)."""
    client = APIClient()

    # User 1: assigned to real dataset 10 -> ALLOWED
    qa_lead_ds10 = _create_user("qa_lead_real_ds10")
    RoleAssignment.objects.create(user=qa_lead_ds10, role=Role.QA_LEAD, dataset_id=10)
    client.force_authenticate(user=qa_lead_ds10)

    resp1 = client.get("/api/test/run/42/")
    assert resp1.status_code == status.HTTP_200_OK

    # User 2: assigned to dataset 42 (matching pk but NOT real dataset) -> REJECTED 403
    qa_lead_ds42 = _create_user("qa_lead_wrong_ds42")
    RoleAssignment.objects.create(user=qa_lead_ds42, role=Role.QA_LEAD, dataset_id=42)
    client.force_authenticate(user=qa_lead_ds42)

    resp2 = client.get("/api/test/run/42/")
    assert resp2.status_code == status.HTTP_403_FORBIDDEN
    assert resp2.data["code"] == "OUT_OF_SCOPE"


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_object_endpoint_query_body_dataset_id_conflict_rejected_400():
    """Client query or body sending dataset_id conflicting with server hook is rejected 400."""
    client = APIClient()
    qa_lead = _create_user("qa_lead_conflict_test")
    RoleAssignment.objects.create(user=qa_lead, role=Role.QA_LEAD, dataset_id=10)
    client.force_authenticate(user=qa_lead)

    # 1. Attacker attempts query param spoofing
    resp_query = client.get("/api/test/run/42/?dataset_id=999")
    assert resp_query.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_query.data["code"] == "VALIDATION_ERROR"
    assert "Mâu thuẫn dataset_id" in str(resp_query.data["message"])

    # 2. Attacker attempts body spoofing
    resp_body = client.post(
        "/api/test/run/42/",
        {"dataset_id": 999},
        format="json",
    )
    assert resp_body.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_body.data["code"] == "VALIDATION_ERROR"
    assert "Mâu thuẫn dataset_id" in str(resp_body.data["message"])
