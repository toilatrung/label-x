"""Personal CVAT credentials never cross account boundaries or leak through APIs."""

import json

import httpx
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import CvatProfile, Role, RoleAssignment
from audit.models import AuditEvent
from cvat_adapter.credentials import credential_cipher, service_token

pytestmark = pytest.mark.django_db
URL = "/api/auth/profile/"
SECRET = "private-cvat-profile-token"


def client_for(user):
    client = APIClient()
    client.force_login(user)
    return client


def test_save_encrypts_and_only_returns_status(settings):
    settings.CVAT_SERVICE_TOKEN = ""
    user = User.objects.create_user("profile-owner")
    client = client_for(user)
    assert client.get(URL).data == {"cvat_token_configured": False, "cvat_token_saved": False}
    response = client.patch(URL, {"cvat_service_token": SECRET}, format="json")
    assert response.status_code == 200, response.data
    assert response.data == {"cvat_token_configured": True, "cvat_token_saved": True}
    assert response["Cache-Control"] == "no-store"
    assert SECRET not in response.content.decode()
    assert SECRET not in client.get(URL).content.decode()
    assert SECRET not in CvatProfile.objects.get().encrypted_token
    assert SECRET not in json.dumps(list(AuditEvent.objects.values()), default=str)
    assert service_token(user) == SECRET
    replacement = client.patch(URL, {"cvat_service_token": "replacement"}, format="json")
    assert replacement.status_code == 200
    assert service_token(user) == "replacement"
    assert CvatProfile.objects.count() == 1


def test_profiles_are_isolated_and_fallback_is_preserved(settings):
    settings.CVAT_SERVICE_TOKEN = "deployment-token"
    owner = User.objects.create_user("owner")
    other = User.objects.create_user("other")
    client_for(owner).patch(URL, {"cvat_service_token": SECRET}, format="json")
    assert service_token(owner) == SECRET
    assert service_token(other) == "deployment-token"
    assert service_token() == "deployment-token"
    settings.CVAT_SERVICE_TOKEN = ""
    assert client_for(other).get(URL).data == {
        "cvat_token_configured": False,
        "cvat_token_saved": False,
    }
    assert service_token(other) == ""


@pytest.mark.parametrize("token", ["", " ", "token\n", "téken", "x" * 4097])
def test_invalid_tokens_do_not_change_profile(token):
    user = User.objects.create_user("invalid-token")
    response = client_for(user).patch(URL, {"cvat_service_token": token}, format="json")
    assert response.status_code == 400
    assert not CvatProfile.objects.exists()


def test_cannot_select_another_user_and_csrf_is_required():
    user = User.objects.create_user("csrf-user")
    other = User.objects.create_user("target-user")
    response = client_for(user).patch(
        URL, {"cvat_service_token": SECRET, "user_id": other.pk}, format="json"
    )
    assert response.status_code == 400
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.patch(URL, {"cvat_service_token": SECRET}, format="json").status_code == 403
    assert APIClient().get(URL).status_code == 403
    assert APIClient().patch(URL, {"cvat_service_token": SECRET}, format="json").status_code == 403
    assert not CvatProfile.objects.exists()


def test_saved_token_drives_dataset_reads_without_restart(monkeypatch, settings):
    settings.CVAT_SERVICE_TOKEN = ""
    settings.CVAT_BASE_URL = "https://cvat.test"
    user = User.objects.create_user("dataset-reader")
    RoleAssignment.objects.create(user=user, role=Role.QC_ADMIN, dataset_id=None)
    client = client_for(user)
    assert client.patch(URL, {"cvat_service_token": SECRET}, format="json").status_code == 200
    requests = []

    def get(http_client, url, **kwargs):
        requests.append(http_client.headers["Authorization"])
        return httpx.Response(
            200,
            json={"results": [{"id": 42, "name": "Urban"}], "next": None},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.Client, "get", get)
    response = client.get("/api/datasets/")
    assert response.status_code == 200, response.data
    assert response.data["results"][0]["id"] == 42
    assert requests == [f"Bearer {SECRET}"]


def test_django_secret_rotation(settings):
    user = User.objects.create_user("rotation")
    client_for(user).patch(URL, {"cvat_service_token": SECRET}, format="json")
    previous = settings.SECRET_KEY
    settings.SECRET_KEY = "replacement-deployment-secret"
    settings.SECRET_KEY_FALLBACKS = [previous]
    assert service_token(user) == SECRET
    assert (
        credential_cipher().decrypt(CvatProfile.objects.get().encrypted_token.encode()).decode()
        == SECRET
    )


def test_delete_removes_only_own_token_and_is_idempotent(settings):
    settings.CVAT_SERVICE_TOKEN = ""
    owner = User.objects.create_user("delete-owner")
    other = User.objects.create_user("delete-other")
    client = client_for(owner)
    client.patch(URL, {"cvat_service_token": SECRET}, format="json")
    client_for(other).patch(URL, {"cvat_service_token": "other-private-token"}, format="json")
    response = client.delete(URL)
    assert response.status_code == 200
    assert response.data == {"cvat_token_configured": False, "cvat_token_saved": False}
    assert response["Cache-Control"] == "no-store"
    assert service_token(owner) == ""
    assert service_token(other) == "other-private-token"
    assert not CvatProfile.objects.filter(user=owner).exists()
    assert AuditEvent.objects.filter(action="profile.cvat_token.delete").count() == 1
    assert client.delete(URL).status_code == 200
    assert AuditEvent.objects.filter(action="profile.cvat_token.delete").count() == 1
    assert APIClient().delete(URL).status_code == 403
    csrf_client = APIClient(enforce_csrf_checks=True)
    csrf_client.force_login(other)
    assert csrf_client.delete(URL).status_code == 403
    assert service_token(other) == "other-private-token"


def test_delete_preserves_deployment_fallback(settings):
    settings.CVAT_SERVICE_TOKEN = "deployment-token"
    user = User.objects.create_user("delete-fallback")
    client = client_for(user)
    client.patch(URL, {"cvat_service_token": SECRET}, format="json")
    response = client.delete(URL)
    assert response.data == {"cvat_token_configured": True, "cvat_token_saved": False}
    assert service_token(user) == "deployment-token"
