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

from accounts.models import CvatIdentity, EmployeeIdentity, Role, RoleAssignment
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
    requester = _create_user("requester_cvat_555")
    CvatIdentity.objects.create(user=requester, cvat_user_id=555, cvat_username="cvat555")
    approver = _create_user("approver_no_cvat")

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
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


# ---------------------------------------------------------------------------
# Finding 1: Super Admin Override Edge Cases via Real URL & Permissions
# ---------------------------------------------------------------------------


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_super_admin_missing_override_flag_returns_422_and_no_mutation():
    """Super Admin on override endpoint without override flag returns 422 and no mutation."""
    client = APIClient()
    admin = _create_user("admin_no_flag")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)
    client.force_authenticate(user=admin)

    response = client.post(
        "/api/test/override/?dataset_id=10",
        {"dataset_id": 10},
        format="json",
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.data["code"] == "BUSINESS_RULE_UNMET"

    rejection_event = AuditEvent.objects.filter(
        actor=admin, action="run.override_action.rejected"
    ).first()
    assert rejection_event is not None
    assert rejection_event.after["code"] == "BUSINESS_RULE_UNMET"

    mutation_audit_exists = AuditEvent.objects.filter(
        actor=admin, action="run.override_action"
    ).exists()
    assert not mutation_audit_exists


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_super_admin_override_false_returns_422_and_no_mutation():
    """Super Admin on override endpoint with override=false returns 422 and no mutation."""
    client = APIClient()
    admin = _create_user("admin_false_flag")
    RoleAssignment.objects.create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)
    client.force_authenticate(user=admin)

    response = client.post(
        "/api/test/override/?dataset_id=10",
        {"dataset_id": 10, "override": False},
        format="json",
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.data["code"] == "BUSINESS_RULE_UNMET"

    rejection_event = AuditEvent.objects.filter(
        actor=admin, action="run.override_action.rejected"
    ).first()
    assert rejection_event is not None
    assert rejection_event.after["code"] == "BUSINESS_RULE_UNMET"

    mutation_audit_exists = AuditEvent.objects.filter(
        actor=admin, action="run.override_action"
    ).exists()
    assert not mutation_audit_exists


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_non_super_admin_normal_flow_allowed_without_override():
    """Non-super admin (QA_LEAD) on endpoint without override flag proceeds normally."""
    client = APIClient()
    qa_lead = _create_user("qa_lead_normal")
    RoleAssignment.objects.create(user=qa_lead, role=Role.QA_LEAD, dataset_id=10)
    client.force_authenticate(user=qa_lead)

    response = client.post(
        "/api/test/override/?dataset_id=10",
        {"dataset_id": 10},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK

    mutation_event = AuditEvent.objects.filter(actor=qa_lead, action="run.override_action").first()
    assert mutation_event is not None
    assert mutation_event.after.get("is_override") is not True


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_integration_non_super_admin_attempting_override_flag_returns_403():
    """Non-super admin attempting override=True returns 403 and creates no mutation."""
    client = APIClient()
    qa_lead = _create_user("qa_lead_spoof_override")
    RoleAssignment.objects.create(user=qa_lead, role=Role.QA_LEAD, dataset_id=10)
    client.force_authenticate(user=qa_lead)

    response = client.post(
        "/api/test/override/?dataset_id=10",
        {"dataset_id": 10, "override": True},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "FORBIDDEN"

    rejection_event = AuditEvent.objects.filter(
        actor=qa_lead, action="run.override_action.rejected"
    ).first()
    assert rejection_event is not None

    mutation_audit_exists = AuditEvent.objects.filter(
        actor=qa_lead, action="run.override_action"
    ).exists()
    assert not mutation_audit_exists


# ---------------------------------------------------------------------------
# Finding 2: Authoritative Server Hook & Nonexistent Object 404
# ---------------------------------------------------------------------------


@pytest.mark.urls("tests.accounts.test_rbac_scope")
def test_object_endpoint_nonexistent_object_client_scoped_dataset_returns_404():
    """Object does not exist (get_dataset_id returns None) -> 404 NOT_FOUND."""
    client = APIClient()
    qa_lead = _create_user("qa_lead_obj_404")
    RoleAssignment.objects.create(user=qa_lead, role=Role.QA_LEAD, dataset_id=10)
    client.force_authenticate(user=qa_lead)

    response = client.get("/api/test/run/999/?dataset_id=10")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "NOT_FOUND"

    event = AuditEvent.objects.filter(actor=qa_lead, action="run.detail.rejected").first()
    assert event is not None
    assert event.after["code"] == "NOT_FOUND"
    assert event.object_id == "999"


# ---------------------------------------------------------------------------
# Finding 3: Separation of Duties Fail-Closed Identity Coverage
# ---------------------------------------------------------------------------


def test_separation_of_duties_both_identities_missing_fails_closed():
    """check_separation_of_duties with neither user_id nor cvat_user_id fails closed 403."""
    factory = APIRequestFactory()
    approver = _create_user("approver_both_missing")
    CvatIdentity.objects.create(user=approver, cvat_user_id=301, cvat_username="cvat301")

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=None,
            requester_cvat_user_id=None,
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"

    event = AuditEvent.objects.filter(actor=approver).order_by("-id").first()
    assert event is not None
    assert event.action == "approval.adjudicate.rejected"
    assert event.after["code"] == "IDENTITY_MAPPING_MISSING"


def test_separation_of_duties_requester_missing_mapping_fails_closed():
    """Requester has user_id but no CvatIdentity in DB -> fails closed 403."""
    factory = APIRequestFactory()
    requester = _create_user("requester_no_mapping")
    approver = _create_user("approver_with_mapping")
    CvatIdentity.objects.create(user=approver, cvat_user_id=302, cvat_username="cvat302")

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"

    event = AuditEvent.objects.filter(actor=approver).order_by("-id").first()
    assert event is not None
    assert event.action == "approval.adjudicate.rejected"
    assert event.after["code"] == "IDENTITY_MAPPING_MISSING"


def test_separation_of_duties_approver_missing_mapping_fails_closed():
    """Approver missing CvatIdentity when reviewing a valid requester -> fails closed 403."""
    factory = APIRequestFactory()
    requester = _create_user("requester_valid_mapping")
    CvatIdentity.objects.create(user=requester, cvat_user_id=303, cvat_username="cvat303")
    approver = _create_user("approver_no_mapping")

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"

    event = AuditEvent.objects.filter(actor=approver).order_by("-id").first()
    assert event is not None
    assert event.action == "approval.adjudicate.rejected"
    assert event.after["code"] == "IDENTITY_MAPPING_MISSING"


def test_separation_of_duties_input_identity_conflicts_db_fails_closed():
    """Input requester_cvat_user_id contradicts DB CvatIdentity -> fails closed."""
    factory = APIRequestFactory()
    requester = _create_user("requester_db_mapped")
    CvatIdentity.objects.create(user=requester, cvat_user_id=304, cvat_username="cvat304")
    approver = _create_user("approver_db_mapped")
    CvatIdentity.objects.create(user=approver, cvat_user_id=305, cvat_username="cvat305")

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
            requester_cvat_user_id=9999,  # Contradicts DB (304)
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"

    event = AuditEvent.objects.filter(actor=approver).order_by("-id").first()
    assert event is not None
    assert event.action == "approval.adjudicate.rejected"
    assert event.after["code"] == "IDENTITY_MAPPING_MISSING"


# ============================================================
# F-1: EmployeeIdentity helpers and cross-account tests
# ============================================================


def _make_verified_employee(employee_id: str) -> EmployeeIdentity:
    """Helper: create a verified EmployeeIdentity (simulates IT provisioning)."""
    from django.utils import timezone

    verifier = _create_user(f"verifier_{employee_id}")
    emp = EmployeeIdentity.objects.create(
        employee_id=employee_id,
        display_name=employee_id,
        verified_at=timezone.now(),
        verified_by=verifier,
    )
    return emp


def test_separation_of_duties_two_distinct_valid_identities_allowed():
    """Two distinct valid identities with verified EmployeeIdentity succeeds."""
    factory = APIRequestFactory()
    emp_req = _make_verified_employee("EMP-DISTINCT-REQ")
    emp_app = _make_verified_employee("EMP-DISTINCT-APP")

    requester = _create_user("requester_distinct")
    CvatIdentity.objects.create(
        user=requester, cvat_user_id=306, cvat_username="cvat306", employee=emp_req
    )
    approver = _create_user("approver_distinct")
    CvatIdentity.objects.create(
        user=approver, cvat_user_id=307, cvat_username="cvat307", employee=emp_app
    )

    request = factory.post("/api/adjudicate/")
    request.user = approver

    # Should not raise any error
    check_separation_of_duties(
        request=request,
        requester_user_id=requester.pk,
        requester_cvat_user_id=306,
        action="approval.adjudicate",
    )


def test_f1_same_employee_different_cvat_accounts_rejected():
    """F-1: Two different LabelX/CVAT accounts sharing same EmployeeIdentity -> 403."""
    factory = APIRequestFactory()
    emp = _make_verified_employee("EMP-001")

    # Requester: account A
    requester = _create_user("emp001_account_a")
    CvatIdentity.objects.create(
        user=requester, cvat_user_id=401, cvat_username="cvat401", employee=emp
    )

    # Approver: account B (different LabelX user, different CVAT id, same employee)
    approver = _create_user("emp001_account_b")
    CvatIdentity.objects.create(
        user=approver, cvat_user_id=402, cvat_username="cvat402", employee=emp
    )

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "SAME_REQUESTER_APPROVER"

    # Audit must record the rejection
    event = AuditEvent.objects.filter(actor=approver).order_by("-id").first()
    assert event is not None
    assert event.action == "approval.adjudicate.rejected"
    assert event.after["code"] == "SAME_REQUESTER_APPROVER"


def test_f1_different_employees_allowed():
    """F-1: Two accounts with different verified EmployeeIdentity -> allowed."""
    factory = APIRequestFactory()
    emp_a = _make_verified_employee("EMP-002")
    emp_b = _make_verified_employee("EMP-003")

    requester = _create_user("emp002_user")
    CvatIdentity.objects.create(
        user=requester, cvat_user_id=403, cvat_username="cvat403", employee=emp_a
    )

    approver = _create_user("emp003_user")
    CvatIdentity.objects.create(
        user=approver, cvat_user_id=404, cvat_username="cvat404", employee=emp_b
    )

    request = factory.post("/api/adjudicate/")
    request.user = approver

    # Must not raise
    check_separation_of_duties(
        request=request,
        requester_user_id=requester.pk,
        action="approval.adjudicate",
    )


def test_f1_requester_unverified_employee_fails_closed():
    """F-1: Requester has EmployeeIdentity but unverified -> fail-closed 403."""
    factory = APIRequestFactory()

    # Unverified employee (verified_at=None)
    req_emp = EmployeeIdentity.objects.create(
        employee_id="EMP-UNVERIFIED-REQ",
        display_name="Unverified Req",
        verified_at=None,
        verified_by=None,
    )
    app_emp = _make_verified_employee("EMP-APP-OK")

    requester = _create_user("unverified_req_user")
    CvatIdentity.objects.create(
        user=requester, cvat_user_id=405, cvat_username="cvat405", employee=req_emp
    )

    approver = _create_user("verified_app_user")
    CvatIdentity.objects.create(
        user=approver, cvat_user_id=406, cvat_username="cvat406", employee=app_emp
    )

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"


def test_f1_approver_missing_employee_fails_closed():
    """F-1: Approver has no EmployeeIdentity -> fail-closed 403."""
    factory = APIRequestFactory()
    req_emp = _make_verified_employee("EMP-REQ-OK2")

    requester = _create_user("req_with_emp")
    CvatIdentity.objects.create(
        user=requester, cvat_user_id=407, cvat_username="cvat407", employee=req_emp
    )

    # Approver has CvatIdentity but no employee link
    approver = _create_user("app_no_emp")
    CvatIdentity.objects.create(
        user=approver, cvat_user_id=408, cvat_username="cvat408", employee=None
    )

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"


def test_f1_client_cannot_inject_employee_id():
    """F-1: employee_id from client body has no effect; server resolves from DB only."""
    factory = APIRequestFactory()
    emp_a = _make_verified_employee("EMP-INJ-A")
    emp_b = _make_verified_employee("EMP-INJ-B")

    requester = _create_user("inj_requester")
    CvatIdentity.objects.create(
        user=requester, cvat_user_id=409, cvat_username="cvat409", employee=emp_a
    )

    approver = _create_user("inj_approver")
    CvatIdentity.objects.create(
        user=approver,
        cvat_user_id=410,
        cvat_username="cvat410",
        employee=emp_a,  # same!
    )

    # Client tries to inject a different employee_id in body — must be ignored
    request = factory.post(
        "/api/adjudicate/",
        data={"employee_id": emp_b.employee_id},
        format="json",
    )
    request.user = approver

    # Server resolves from DB -> same employee -> 403 regardless of client input
    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "SAME_REQUESTER_APPROVER"


def test_f1_migration_old_accounts_null_employee_fail_closed():
    """F-1: Legacy CvatIdentity with employee=None cannot approve (fail-closed)."""
    factory = APIRequestFactory()
    req_emp = _make_verified_employee("EMP-LEGACY-REQ")

    requester = _create_user("legacy_req")
    CvatIdentity.objects.create(
        user=requester, cvat_user_id=411, cvat_username="cvat411", employee=req_emp
    )

    # Old account migrated with employee=None (not backfilled)
    approver = _create_user("legacy_approver_old")
    CvatIdentity.objects.create(
        user=approver, cvat_user_id=412, cvat_username="cvat412", employee=None
    )

    request = factory.post("/api/adjudicate/")
    request.user = approver

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request,
            requester_user_id=requester.pk,
            action="approval.adjudicate",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"


def test_f1_provisioning_unprivileged_rejected():
    """F-1: Regular user cannot assign/modify EmployeeIdentity (403 FORBIDDEN)."""
    from accounts.services import assign_employee_identity

    unprivileged_user = _create_user("regular_user_hacker")
    target_user = _create_user("target_victim")
    CvatIdentity.objects.create(user=target_user, cvat_user_id=500, cvat_username="victim_cvat")

    with pytest.raises(ApiError) as exc_info:
        assign_employee_identity(
            actor=unprivileged_user,
            user=target_user,
            employee_id="EMP-HACK-01",
            reason="unauthorized",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "FORBIDDEN"


def test_f1_provisioning_blank_id_rejected():
    """F-1: Blank employee_id is rejected with 400 INVALID_INPUT."""
    from accounts.services import assign_employee_identity

    admin_user = _create_user("admin_provisioner")
    RoleAssignment.objects.create(user=admin_user, role=Role.SUPER_ADMIN, dataset_id=None)

    target_user = _create_user("target_blank")
    CvatIdentity.objects.create(user=target_user, cvat_user_id=899, cvat_username="blank_cvat")

    with pytest.raises(ApiError) as exc_info:
        assign_employee_identity(
            actor=admin_user,
            user=target_user,
            employee_id="   ",
            reason="Test blank rejection",
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.error_code == "INVALID_INPUT"


def test_f1_provisioning_super_admin_success_and_audit():
    """F-1: SUPER_ADMIN assigns EmployeeIdentity via service; audit event recorded inside tx."""
    from accounts.services import assign_employee_identity

    admin_user = _create_user("it_admin_user")
    RoleAssignment.objects.create(user=admin_user, role=Role.SUPER_ADMIN, dataset_id=None)

    target_user = _create_user("engineer_alice")
    CvatIdentity.objects.create(
        user=target_user,
        cvat_user_id=888,
        cvat_username="alice_cvat",
        employee=None,
    )

    emp, event = assign_employee_identity(
        actor=admin_user,
        user=target_user,
        employee_id="EMP-ALICE-01",
        display_name="Alice Engineer",
        reason="Onboarding IT provisioning",
    )

    assert emp.employee_id == "EMP-ALICE-01"
    assert emp.is_verified is True
    assert emp.verified_by == admin_user

    # CvatIdentity linked
    target_user.refresh_from_db()
    assert target_user.cvat_identity.employee == emp

    # Audit event checks
    assert event.actor == admin_user
    assert event.action == "accounts.employee_identity.assigned"
    assert event.object_type == "employee_identity"
    assert event.object_id == "EMP-ALICE-01"
    assert event.before["employee_id"] is None
    assert event.after["employee_id"] == "EMP-ALICE-01"
    assert event.after["is_verified"] is True


def test_f1_provisioning_update_mapping_records_before_and_after_audit():
    """F-1: Updating employee mapping records old and new values in audit event."""
    from accounts.services import assign_employee_identity

    admin_user = _create_user("hr_admin_user")
    RoleAssignment.objects.create(user=admin_user, role=Role.SUPER_ADMIN, dataset_id=None)

    target_user = _create_user("engineer_bob")
    emp_old = _make_verified_employee("EMP-BOB-OLD")
    CvatIdentity.objects.create(
        user=target_user,
        cvat_user_id=889,
        cvat_username="bob_cvat",
        employee=emp_old,
    )

    emp_new, event = assign_employee_identity(
        actor=admin_user,
        user=target_user,
        employee_id="EMP-BOB-NEW",
        reason="HR corrected employee ID",
    )

    assert event.before["employee_id"] == "EMP-BOB-OLD"
    assert event.after["employee_id"] == "EMP-BOB-NEW"


def test_f1_set_cvat_identity_command_with_employee():
    """F-1: set_cvat_identity command uses --actor + --reason for employee assignment."""
    import io

    from django.core.management import call_command

    actor = _create_user("command_actor_su")
    RoleAssignment.objects.create(user=actor, role=Role.SUPER_ADMIN, dataset_id=None)
    test_user = _create_user("command_target_user")

    out = io.StringIO()
    # First create the CVAT identity mapping
    call_command(
        "set_cvat_identity",
        test_user.username,
        "991",
        "--cvat-username",
        "cmd_user_cvat",
        stdout=out,
    )

    # Then assign employee via command
    call_command(
        "set_cvat_identity",
        test_user.username,
        "991",
        "--cvat-username",
        "cmd_user_cvat",
        "--employee-id",
        "EMP-CMD-991",
        "--actor",
        actor.username,
        "--reason",
        "IT provisioning command test",
        stdout=out,
    )

    test_user.refresh_from_db()
    cvat_id = test_user.cvat_identity
    assert cvat_id.cvat_user_id == 991
    assert cvat_id.employee is not None
    assert cvat_id.employee.employee_id == "EMP-CMD-991"
    assert cvat_id.employee.is_verified is True
    assert cvat_id.employee.verified_by == actor


# ============================================================
# F-1 Final: Additional hardening tests
# ============================================================


def test_f1_staff_superuser_without_role_rejected():
    """F-1: is_staff / is_superuser without RoleAssignment does NOT grant provisioning rights."""
    from accounts.services import assign_employee_identity

    hacker = _create_user("staff_super_no_role")
    hacker.is_staff = True
    hacker.is_superuser = True
    hacker.save()

    target = _create_user("victim_of_hacker")
    CvatIdentity.objects.create(user=target, cvat_user_id=501, cvat_username="victim_cvat")

    with pytest.raises(ApiError) as exc_info:
        assign_employee_identity(
            actor=hacker,
            user=target,
            employee_id="EMP-HACK-STAFF",
            reason="unauthorized attempt",
        )

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "FORBIDDEN"
    from accounts.models import EmployeeIdentity as EI

    assert not EI.objects.filter(employee_id="EMP-HACK-STAFF").exists()


def test_f1_target_without_cvat_identity_rejected_before_employee_created():
    """F-1: Target without CvatIdentity → 422; no orphan EmployeeIdentity created."""
    from accounts.models import EmployeeIdentity as EI
    from accounts.services import assign_employee_identity

    actor = _create_user("actor_with_role_no_cvat")
    RoleAssignment.objects.create(user=actor, role=Role.QC_ADMIN, dataset_id=None)
    target_no_cvat = _create_user("target_no_cvat_identity")

    with pytest.raises(ApiError) as exc_info:
        assign_employee_identity(
            actor=actor,
            user=target_no_cvat,
            employee_id="EMP-ORPHAN-01",
            reason="should fail before creating employee",
        )

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.error_code == "IDENTITY_MAPPING_MISSING"
    assert not EI.objects.filter(employee_id="EMP-ORPHAN-01").exists()


def test_f1_reason_required_not_empty():
    """F-1: assign_employee_identity requires non-empty reason string."""
    from accounts.services import assign_employee_identity

    actor = _create_user("actor_no_reason")
    RoleAssignment.objects.create(user=actor, role=Role.SUPER_ADMIN, dataset_id=None)
    target = _create_user("target_no_reason")
    CvatIdentity.objects.create(user=target, cvat_user_id=502, cvat_username="nr_cvat")

    with pytest.raises(ApiError) as exc_info:
        assign_employee_identity(
            actor=actor,
            user=target,
            employee_id="EMP-NR-01",
            reason="   ",
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.error_code == "INVALID_INPUT"


def test_f1_audit_failure_rolls_back_mapping():
    """F-1: audit write failure causes full transaction rollback."""
    from unittest.mock import patch

    from accounts.services import assign_employee_identity

    actor = _create_user("actor_audit_fail")
    RoleAssignment.objects.create(user=actor, role=Role.SUPER_ADMIN, dataset_id=None)
    target = _create_user("target_audit_fail")
    CvatIdentity.objects.create(
        user=target, cvat_user_id=503, cvat_username="af_cvat", employee=None
    )

    with (
        pytest.raises(Exception),  # noqa: B017
        patch(
            "accounts.services.append_audit_event",
            side_effect=RuntimeError("simulated audit failure"),
        ),
    ):
        assign_employee_identity(
            actor=actor,
            user=target,
            employee_id="EMP-AF-01",
            reason="audit failure test",
        )

    target.refresh_from_db()
    assert target.cvat_identity.employee is None


def test_f1_command_missing_actor_rejected():
    """F-1: set_cvat_identity command rejects --employee-id without --actor."""
    import io

    from django.core.management import CommandError, call_command

    target = _create_user("cmd_no_actor_target")

    out = io.StringIO()
    with pytest.raises(CommandError, match="--actor"):
        call_command(
            "set_cvat_identity",
            target.username,
            "994",
            "--employee-id",
            "EMP-NO-ACTOR",
            "--reason",
            "some reason",
            stdout=out,
        )


def test_f1_command_missing_reason_rejected():
    """F-1: set_cvat_identity command rejects --employee-id without --reason."""
    import io

    from django.core.management import CommandError, call_command

    actor = _create_user("cmd_actor_no_reason")
    RoleAssignment.objects.create(user=actor, role=Role.SUPER_ADMIN, dataset_id=None)
    target = _create_user("cmd_no_reason_target")

    out = io.StringIO()
    with pytest.raises(CommandError, match="--reason"):
        call_command(
            "set_cvat_identity",
            target.username,
            "995",
            "--employee-id",
            "EMP-NO-REASON",
            "--actor",
            actor.username,
            stdout=out,
        )


def test_f1_command_unprivileged_actor_rejected():
    """F-1: set_cvat_identity command rejects actor without SUPER_ADMIN/QC_ADMIN role."""
    import io

    from django.core.management import CommandError, call_command

    unprivileged_actor = _create_user("cmd_unpriv_actor")
    target = _create_user("cmd_unpriv_target")

    out = io.StringIO()
    with pytest.raises(CommandError, match="không có quyền SUPER_ADMIN hoặc QC_ADMIN"):
        call_command(
            "set_cvat_identity",
            target.username,
            "996",
            "--employee-id",
            "EMP-UNPRIV",
            "--actor",
            unprivileged_actor.username,
            "--reason",
            "unauthorized provisioning",
            stdout=out,
        )


def test_f1_admin_cannot_add_employee_identity():
    """F-1: EmployeeIdentityAdmin.has_add_permission returns False."""
    from django.test import RequestFactory

    from accounts.admin import EmployeeIdentityAdmin
    from accounts.models import EmployeeIdentity

    admin_obj = EmployeeIdentityAdmin(EmployeeIdentity, None)
    request = RequestFactory().get("/admin/")
    request.user = _create_user("admin_check_add")
    assert admin_obj.has_add_permission(request) is False


def test_f1_admin_cannot_change_employee_identity():
    """F-1: EmployeeIdentityAdmin.has_change_permission returns False."""
    from django.test import RequestFactory

    from accounts.admin import EmployeeIdentityAdmin
    from accounts.models import EmployeeIdentity

    admin_obj = EmployeeIdentityAdmin(EmployeeIdentity, None)
    request = RequestFactory().get("/admin/")
    request.user = _create_user("admin_check_change")
    assert admin_obj.has_change_permission(request) is False
    assert admin_obj.has_change_permission(request, obj=None) is False


def test_f1_admin_cannot_delete_employee_identity():
    """F-1: EmployeeIdentityAdmin.has_delete_permission returns False."""
    from django.test import RequestFactory

    from accounts.admin import EmployeeIdentityAdmin
    from accounts.models import EmployeeIdentity

    admin_obj = EmployeeIdentityAdmin(EmployeeIdentity, None)
    request = RequestFactory().get("/admin/")
    request.user = _create_user("admin_check_delete")
    assert admin_obj.has_delete_permission(request) is False


def test_f1_model_constraint_verified_fields_consistent():
    """F-1: DB constraint rejects EmployeeIdentity with only one of verified_at/verified_by."""
    from django.db import IntegrityError as DjIntegrityError
    from django.utils import timezone

    from accounts.models import EmployeeIdentity as EI

    verifier = _create_user("constraint_verifier")

    with pytest.raises(DjIntegrityError), transaction.atomic():
        EI.objects.create(
            employee_id="EMP-CONST-FAIL",
            verified_at=timezone.now(),
            verified_by=None,
        )

    with pytest.raises(DjIntegrityError), transaction.atomic():
        EI.objects.create(
            employee_id="EMP-CONST-FAIL2",
            verified_at=None,
            verified_by=verifier,
        )

    emp_unverified = EI.objects.create(employee_id="EMP-CONST-OK-NULL")
    assert emp_unverified.is_verified is False

    emp_verified = EI.objects.create(
        employee_id="EMP-CONST-OK-BOTH",
        verified_at=timezone.now(),
        verified_by=verifier,
    )
    assert emp_verified.is_verified is True


def test_f1_is_verified_requires_both_fields():
    """F-1: is_verified is True only when both verified_at and verified_by are set."""
    from django.utils import timezone

    from accounts.models import EmployeeIdentity as EI

    verifier = _create_user("is_verified_check_user")

    emp = EI.objects.create(employee_id="EMP-ISVERIFIED-01")
    assert emp.is_verified is False

    emp_ok = EI.objects.create(
        employee_id="EMP-ISVERIFIED-OK",
        verified_at=timezone.now(),
        verified_by=verifier,
    )
    assert emp_ok.is_verified is True


# ==============================================================================
# F-1 MANDATORY FIX TESTS: INPUT CHECK BEFORE MUTATION, ROLLBACK, SELF-MOD,
# CASE-INSENSITIVE UNIQUE, AND PROTECTED DELETION
# ==============================================================================


def test_f1_command_missing_actor_does_not_create_or_modify_cvat_identity():
    """F-1: Missing --actor rejects before mutation, does NOT create or modify CvatIdentity."""
    import io

    from django.core.management import CommandError, call_command

    # Case 1: Target has no prior CvatIdentity -> must NOT create CvatIdentity
    target_new = _create_user("cmd_no_actor_target_new")
    out = io.StringIO()
    with pytest.raises(CommandError, match="--actor là bắt buộc"):
        call_command(
            "set_cvat_identity",
            target_new.username,
            "9801",
            "--employee-id",
            "EMP-NO-ACT-1",
            "--reason",
            "valid reason",
            stdout=out,
        )
    assert not CvatIdentity.objects.filter(user=target_new).exists()

    # Case 2: Target has existing CvatIdentity (cvat_user_id=100) -> must NOT change to 9802
    target_existing = _create_user("cmd_no_actor_target_existing")
    CvatIdentity.objects.create(user=target_existing, cvat_user_id=100, cvat_username="old_cvat")
    with pytest.raises(CommandError, match="--actor là bắt buộc"):
        call_command(
            "set_cvat_identity",
            target_existing.username,
            "9802",
            "--employee-id",
            "EMP-NO-ACT-2",
            "--reason",
            "valid reason",
            stdout=out,
        )
    target_existing.refresh_from_db()
    assert target_existing.cvat_identity.cvat_user_id == 100


def test_f1_command_missing_reason_does_not_create_or_modify_cvat_identity():
    """F-1: Missing --reason rejects before mutation, does NOT create or modify CvatIdentity."""
    import io

    from django.core.management import CommandError, call_command

    actor = _create_user("cmd_valid_actor_reason_test")
    RoleAssignment.objects.create(user=actor, role=Role.SUPER_ADMIN, dataset_id=None)

    # Case 1: Target has no prior CvatIdentity -> must NOT create CvatIdentity
    target_new = _create_user("cmd_no_reason_target_new")
    out = io.StringIO()
    with pytest.raises(CommandError, match="--reason là bắt buộc"):
        call_command(
            "set_cvat_identity",
            target_new.username,
            "9803",
            "--employee-id",
            "EMP-NO-RSN-1",
            "--actor",
            actor.username,
            stdout=out,
        )
    assert not CvatIdentity.objects.filter(user=target_new).exists()

    # Case 2: Target has existing CvatIdentity (cvat_user_id=101) -> must NOT change to 9804
    target_existing = _create_user("cmd_no_reason_target_existing")
    CvatIdentity.objects.create(user=target_existing, cvat_user_id=101, cvat_username="old_cvat_2")
    with pytest.raises(CommandError, match="--reason là bắt buộc"):
        call_command(
            "set_cvat_identity",
            target_existing.username,
            "9804",
            "--employee-id",
            "EMP-NO-RSN-2",
            "--actor",
            actor.username,
            stdout=out,
        )
    target_existing.refresh_from_db()
    assert target_existing.cvat_identity.cvat_user_id == 101


def test_f1_command_unprivileged_actor_does_not_create_or_modify_cvat_identity():
    """F-1: Unprivileged actor rejects before mutation, does NOT create or modify CvatIdentity."""
    import io

    from django.core.management import CommandError, call_command

    unpriv_actor = _create_user("cmd_unprivileged_actor_2")
    # Staff / superuser flags alone do NOT grant business authority
    unpriv_actor.is_staff = True
    unpriv_actor.is_superuser = True
    unpriv_actor.save()

    # Case 1: Target has no prior CvatIdentity -> must NOT create CvatIdentity
    target_new = _create_user("cmd_unpriv_target_new")
    out = io.StringIO()
    with pytest.raises(CommandError, match="không có quyền SUPER_ADMIN hoặc QC_ADMIN"):
        call_command(
            "set_cvat_identity",
            target_new.username,
            "9805",
            "--employee-id",
            "EMP-UNPRIV-1",
            "--actor",
            unpriv_actor.username,
            "--reason",
            "attempt unpriv",
            stdout=out,
        )
    assert not CvatIdentity.objects.filter(user=target_new).exists()

    # Case 2: Target has existing CvatIdentity (cvat_user_id=102) -> must NOT change to 9806
    target_existing = _create_user("cmd_unpriv_target_existing")
    CvatIdentity.objects.create(user=target_existing, cvat_user_id=102, cvat_username="old_cvat_3")
    with pytest.raises(CommandError, match="không có quyền SUPER_ADMIN hoặc QC_ADMIN"):
        call_command(
            "set_cvat_identity",
            target_existing.username,
            "9806",
            "--employee-id",
            "EMP-UNPRIV-2",
            "--actor",
            unpriv_actor.username,
            "--reason",
            "attempt unpriv",
            stdout=out,
        )
    target_existing.refresh_from_db()
    assert target_existing.cvat_identity.cvat_user_id == 102


def test_f1_command_audit_failure_rolls_back_both_cvat_and_employee_mapping():
    """F-1: Audit failure during command rolls back BOTH CVAT and employee mapping."""
    import io
    from unittest.mock import patch

    from django.core.management import CommandError, call_command

    actor = _create_user("cmd_audit_fail_actor")
    RoleAssignment.objects.create(user=actor, role=Role.SUPER_ADMIN, dataset_id=None)

    # Case 1: Target had NO CvatIdentity before
    target_new = _create_user("cmd_audit_fail_target_new")
    out = io.StringIO()
    with (
        pytest.raises(CommandError, match="Lỗi khi thực thi gán identity"),
        patch(
            "accounts.services.append_audit_event",
            side_effect=RuntimeError("Disk full audit error"),
        ),
    ):
        call_command(
            "set_cvat_identity",
            target_new.username,
            "9810",
            "--employee-id",
            "EMP-ROLLBACK-NEW",
            "--actor",
            actor.username,
            "--reason",
            "audit fail test new",
            stdout=out,
        )
    # Outer transaction rollback -> CvatIdentity was NOT created!
    assert not CvatIdentity.objects.filter(user=target_new).exists()

    # Case 2: Target had existing CvatIdentity (cvat_user_id=200, employee=None)
    target_existing = _create_user("cmd_audit_fail_target_existing")
    CvatIdentity.objects.create(
        user=target_existing, cvat_user_id=200, cvat_username="existing_cvat", employee=None
    )
    with (
        pytest.raises(CommandError, match="Lỗi khi thực thi gán identity"),
        patch(
            "accounts.services.append_audit_event",
            side_effect=RuntimeError("Disk full audit error"),
        ),
    ):
        call_command(
            "set_cvat_identity",
            target_existing.username,
            "9811",
            "--employee-id",
            "EMP-ROLLBACK-EXISTING",
            "--actor",
            actor.username,
            "--reason",
            "audit fail test existing",
            stdout=out,
        )
    # Outer transaction rollback -> cvat_user_id unchanged, employee unchanged!
    target_existing.refresh_from_db()
    assert target_existing.cvat_identity.cvat_user_id == 200
    assert target_existing.cvat_identity.employee is None


def test_f1_self_modification_forbidden_for_super_admin_and_qc_admin():
    """F-1: Actor cannot assign or modify EmployeeIdentity for themselves."""
    from accounts.services import assign_employee_identity

    # 1. SUPER_ADMIN attempting self-modification
    super_admin = _create_user("super_admin_self_mod")
    RoleAssignment.objects.create(user=super_admin, role=Role.SUPER_ADMIN, dataset_id=None)
    CvatIdentity.objects.create(user=super_admin, cvat_user_id=601, cvat_username="sa_self")

    with pytest.raises(ApiError) as exc_info_sa:
        assign_employee_identity(
            actor=super_admin,
            user=super_admin,
            employee_id="EMP-SELF-SA",
            reason="trying to verify myself",
        )
    assert exc_info_sa.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info_sa.value.error_code == "SELF_MODIFICATION_FORBIDDEN"

    # 2. QC_ADMIN attempting self-modification
    qc_admin = _create_user("qc_admin_self_mod")
    RoleAssignment.objects.create(user=qc_admin, role=Role.QC_ADMIN, dataset_id=None)
    CvatIdentity.objects.create(user=qc_admin, cvat_user_id=602, cvat_username="qc_self")

    with pytest.raises(ApiError) as exc_info_qc:
        assign_employee_identity(
            actor=qc_admin,
            user=qc_admin,
            employee_id="EMP-SELF-QC",
            reason="trying to verify myself as qc",
        )
    assert exc_info_qc.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info_qc.value.error_code == "SELF_MODIFICATION_FORBIDDEN"

    # 3. Via set_cvat_identity command: self-modification rejected
    import io

    from django.core.management import CommandError, call_command

    out = io.StringIO()
    with pytest.raises(
        CommandError, match="không được phép tự gán hoặc tự thay đổi EmployeeIdentity"
    ):
        call_command(
            "set_cvat_identity",
            super_admin.username,
            "601",
            "--employee-id",
            "EMP-SELF-CMD",
            "--actor",
            super_admin.username,
            "--reason",
            "cmd self mod",
            stdout=out,
        )


def test_f1_employee_id_case_insensitive_normalization_and_uniqueness():
    """F-1: EMP-001 and emp-001 are same identity, protected by constraint & normalization."""
    from django.db import IntegrityError as DjIntegrityError

    from accounts.models import EmployeeIdentity as EI
    from accounts.services import assign_employee_identity

    actor = _create_user("case_actor_admin")
    RoleAssignment.objects.create(user=actor, role=Role.SUPER_ADMIN, dataset_id=None)

    target_a = _create_user("case_user_a")
    CvatIdentity.objects.create(user=target_a, cvat_user_id=701, cvat_username="case_a")

    target_b = _create_user("case_user_b")
    CvatIdentity.objects.create(user=target_b, cvat_user_id=702, cvat_username="case_b")

    # Step 1: Assign EMP-CASE-01 to target_a
    emp_a, _ = assign_employee_identity(
        actor=actor,
        user=target_a,
        employee_id="EMP-CASE-01",
        reason="assign upper case",
    )

    # Step 2: Assign emp-case-01 (lowercase) to target_b
    emp_b, _ = assign_employee_identity(
        actor=actor,
        user=target_b,
        employee_id="emp-case-01",
        reason="assign lower case",
    )

    # They must resolve to the exact SAME EmployeeIdentity record!
    assert emp_a.pk == emp_b.pk
    target_a.refresh_from_db()
    target_b.refresh_from_db()
    assert target_a.cvat_identity.employee == target_b.cvat_identity.employee

    # Step 3: Database-level adversarial test: attempting to create lowercase when uppercase exists
    with pytest.raises(DjIntegrityError), transaction.atomic():
        EI.objects.create(employee_id="Emp-Case-01")

    # Step 4: Separation of duties verifies they are the same person and rejects cross-review
    from accounts.permissions import check_separation_of_duties

    factory = APIRequestFactory()
    request_b = factory.post("/api/dummy/adjudicate/", {}, format="json")
    request_b.user = target_b

    with pytest.raises(ApiError) as exc_info:
        check_separation_of_duties(
            request=request_b,
            requester_user_id=target_a.pk,
            requester_cvat_user_id=701,
            action="adjudicate",
        )
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.error_code == "SAME_REQUESTER_APPROVER"


def test_f1_employee_identity_protected_from_deletion_while_linked():
    """F-1: EmployeeIdentity linked to CvatIdentity cannot be deleted (PROTECT)."""
    from django.db.models import ProtectedError

    from accounts.models import EmployeeIdentity as EI

    emp = EI.objects.create(employee_id="EMP-PROTECT-TEST")
    user = _create_user("protect_user")
    cvat_id = CvatIdentity.objects.create(user=user, cvat_user_id=801, employee=emp)

    # Attempting to delete emp while cvat_id points to it must raise ProtectedError
    with pytest.raises(ProtectedError):
        emp.delete()

    # EmployeeIdentity still exists in DB
    assert EI.objects.filter(pk=emp.pk).exists()

    # After clearing or deleting CvatIdentity, unlinked EmployeeIdentity can be deleted
    cvat_id.delete()
    emp.delete()
    assert not EI.objects.filter(pk=emp.pk).exists()
