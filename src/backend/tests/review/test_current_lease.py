from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import CvatIdentity, RoleAssignment
from review.models import Lease
from tests.review.test_queue_lease import client, next_url, world  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def test_current_lease_reads_own_grant_without_claim_or_renew(world):  # noqa: F811
    api = client(world["reviewer"])
    assert api.get("/api/leases/current/?dataset_id=42").status_code == 204
    first = api.post(next_url(), {"run_id": world["run"].pk}, format="json").data
    lease = Lease.objects.get(pk=first["lease"]["id"])
    response = api.get("/api/leases/current/?dataset_id=42")
    assert response.status_code == 200, response.data
    assert response.data["lease"] == first["lease"]
    assert response.data["queue"] == "risk"
    assert response.data["frame"]["id"] == first["frame"]["id"]
    lease.refresh_from_db()
    assert lease.renewed_at is None
    assert Lease.objects.count() == 1
    assert client(world["other"]).get("/api/leases/current/?dataset_id=42").status_code == 204


def test_expired_lease_is_not_restored_or_mutated(world):  # noqa: F811
    api = client(world["reviewer"])
    first = api.post(next_url(), {"run_id": world["run"].pk}, format="json").data
    Lease.objects.filter(pk=first["lease"]["id"]).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )
    assert api.get("/api/leases/current/?dataset_id=42").status_code == 204
    assert Lease.objects.get(pk=first["lease"]["id"]).closed_at is None


def test_current_lease_enforces_dataset_scope_and_authentication(world):  # noqa: F811
    api = client(world["reviewer"])
    assert api.get("/api/leases/current/?dataset_id=999999").status_code == 403
    assert api.get("/api/leases/current/").status_code == 400
    assert APIClient().get("/api/leases/current/?dataset_id=42").status_code == 403


@pytest.mark.parametrize("revoke", ["identity", "dataset"])
def test_current_lease_rechecks_access_before_restoring(world, revoke):  # noqa: F811
    api = client(world["reviewer"])
    first = api.post(next_url(), {"run_id": world["run"].pk}, format="json").data
    if revoke == "identity":
        CvatIdentity.objects.filter(user=world["reviewer"]).delete()
    else:
        RoleAssignment.objects.filter(user=world["reviewer"]).delete()
    assert api.get("/api/leases/current/?dataset_id=42").status_code == 403
    lease = Lease.objects.get(pk=first["lease"]["id"])
    assert lease.closed_at is None
    assert lease.renewed_at is None
