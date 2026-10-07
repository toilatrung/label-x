"""Tests cho vai trò theo scope và identity mapping LabelX ↔ CVAT (T-011, FR-SEC-02)."""

from __future__ import annotations

import io

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction

from accounts.models import CvatIdentity, RoleAssignment

pytestmark = pytest.mark.django_db


@pytest.fixture
def user() -> User:
    return User.objects.create_user("an", password="Mat-khau-dai-123")


def test_dataset_scoped_role_requires_dataset(user: User) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RoleAssignment.objects.create(user=user, role="reviewer", dataset_id=None)


@pytest.mark.parametrize("role", ["super_admin", "qc_admin"])
def test_system_wide_roles_allow_null_dataset(user: User, role: str) -> None:
    RoleAssignment.objects.create(user=user, role=role, dataset_id=None)


def test_duplicate_assignment_rejected_including_null_dataset(user: User) -> None:
    RoleAssignment.objects.create(user=user, role="qc_admin", dataset_id=None)
    with pytest.raises(IntegrityError), transaction.atomic():
        RoleAssignment.objects.create(user=user, role="qc_admin", dataset_id=None)


def test_assign_role_command(user: User) -> None:
    out = io.StringIO()
    call_command("assign_role", "an", "reviewer", "--dataset-id", "3", stdout=out)
    call_command("assign_role", "an", "reviewer", "--dataset-id", "3", stdout=out)
    assert RoleAssignment.objects.filter(user=user, role="reviewer", dataset_id=3).count() == 1
    assert "Đã có sẵn" in out.getvalue()


def test_assign_role_command_rejects_unscoped_dataset_role(user: User) -> None:
    with pytest.raises(CommandError, match="--dataset-id"):
        call_command("assign_role", "an", "reviewer")


def test_assign_role_command_unknown_user() -> None:
    with pytest.raises(CommandError, match="Không có người dùng"):
        call_command("assign_role", "khong-co", "super_admin")


def test_set_cvat_identity_command_stores_and_updates(user: User) -> None:
    call_command(
        "set_cvat_identity", "an", "11", "--cvat-username", "an_cvat", stdout=io.StringIO()
    )
    call_command("set_cvat_identity", "an", "12", stdout=io.StringIO())
    identity = CvatIdentity.objects.get(user=user)
    assert identity.cvat_user_id == 12


def test_cvat_user_maps_to_single_labelx_account(user: User) -> None:
    User.objects.create_user("binh", password="Mat-khau-dai-123")
    call_command("set_cvat_identity", "an", "11", stdout=io.StringIO())
    with pytest.raises(CommandError, match="đã gắn"):
        call_command("set_cvat_identity", "binh", "11", stdout=io.StringIO())
