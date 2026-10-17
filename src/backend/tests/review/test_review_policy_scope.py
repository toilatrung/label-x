"""CR-113: GET /api/review-policy/?dataset_id={id} is scope-checked; without it nothing changes."""

from __future__ import annotations

import pytest
from django.contrib.auth.models import User

from accounts.models import Role, RoleAssignment
from audit.models import AuditEvent
from tests.review.test_queue_lease import client

pytest_plugins = ["tests.review.test_queue_lease"]
URL = "/api/review-policy/"


def _user(name, role=None, dataset_id=42):
    user = User.objects.create_user(name)
    if role is not None:
        RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    return user


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.ANNOTATOR, Role.REVIEWER, Role.QA_LEAD, Role.QC_ADMIN])
def test_dataset_scope_allows_in_scope_and_denies_other_dataset(role):
    api = client(_user(f"u-{role}", role, dataset_id=42))
    own = api.get(URL, {"dataset_id": 42})
    assert own.status_code == 200, own.data
    foreign = api.get(URL, {"dataset_id": 43})
    assert foreign.status_code == 403
    assert foreign.data["code"] == "OUT_OF_SCOPE"


@pytest.mark.django_db
def test_same_policy_with_or_without_dataset_id():
    api = client(_user("reader", Role.REVIEWER))
    plain = api.get(URL)
    scoped = api.get(URL, {"dataset_id": 42})
    assert plain.status_code == scoped.status_code == 200
    assert plain.data == scoped.data


@pytest.mark.django_db
def test_without_dataset_id_behaviour_is_unchanged_for_any_allowed_role():
    for role in (Role.ANNOTATOR, Role.REVIEWER, Role.QA_LEAD, Role.QC_ADMIN):
        assert client(_user(f"c-{role}", role)).get(URL).status_code == 200
    # Role still required: a user without assignment, or with a role outside the list, is denied.
    assert client(_user("nobody")).get(URL).status_code == 403
    assert client(_user("po", Role.PRODUCT_OWNER)).get(URL).status_code == 403
    assert client(_user("po2", Role.PRODUCT_OWNER)).get(URL, {"dataset_id": 42}).status_code == 403


@pytest.mark.django_db
def test_super_admin_global_scope_reads_any_dataset():
    admin = _user("root", Role.SUPER_ADMIN, dataset_id=None)
    assert client(admin).get(URL, {"dataset_id": 999}).status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("bad", ["abc", "0", "-1", "4.2", ""])
def test_invalid_dataset_id_is_400_not_silently_ignored(bad):
    response = client(_user("v", Role.REVIEWER)).get(URL, {"dataset_id": bad})
    assert response.status_code == 400, response.data
    assert response.data["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_denied_scope_is_audited_and_unauthenticated_is_rejected():
    user = _user("audited", Role.REVIEWER)
    before = AuditEvent.objects.count()
    assert client(user).get(URL, {"dataset_id": 7}).status_code == 403
    assert AuditEvent.objects.count() == before + 1
    assert AuditEvent.objects.filter(action="review_policy.retrieve.rejected").exists()
    from rest_framework.test import APIClient

    assert APIClient().get(URL, {"dataset_id": 42}).status_code in (401, 403)
