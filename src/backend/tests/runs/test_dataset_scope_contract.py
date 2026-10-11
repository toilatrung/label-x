"""R-3: mã lỗi thật của endpoint có dataset scope khớp contract và schema sinh ra."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from django.contrib.auth.models import User
from drf_spectacular.generators import SchemaGenerator
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from tests.orchestration.helpers import make_run

pytestmark = pytest.mark.django_db(transaction=True)

CONTRACT = Path(__file__).resolve().parents[4] / "docs/04-api/openapi.yaml"

# (method, path mẫu, operationId) — mọi endpoint requires_dataset=True của runs/snapshots theo {id}.
SCOPED = [
    ("get", "/api/runs/{run}/", "/api/runs/{id}/"),
    ("post", "/api/runs/{run}/cancel/", "/api/runs/{id}/cancel/"),
    ("post", "/api/runs/{run}/retry-failed/", "/api/runs/{id}/retry-failed/"),
    ("get", "/api/runs/{run}/ledger/", "/api/runs/{id}/ledger/"),
    ("get", "/api/runs/{run}/shards/", "/api/runs/{id}/shards/"),
    ("get", "/api/runs/{run}/candidates/", "/api/runs/{id}/candidates/"),
    ("get", "/api/runs/{run}/ranking/", "/api/runs/{id}/ranking/"),
]


@pytest.fixture(scope="module")
def spec() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


@pytest.mark.parametrize(("method", "url", "contract_path"), SCOPED)
def test_dataset_mismatch_returns_documented_400(spec, method, url, contract_path):
    run = make_run()
    user = User.objects.create_user(username=f"scope-{contract_path}".replace("/", "_"))
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=run.dataset_id)
    client = APIClient()
    client.force_authenticate(user)
    path = url.format(run=run.pk) + f"?dataset_id={run.dataset_id + 1}"
    response = getattr(client, method)(path)
    assert response.status_code == 400, response.content
    assert response.json()["code"] == "VALIDATION_ERROR"
    documented = spec["paths"][contract_path][method]["responses"]
    assert "400" in documented, (
        f"{method.upper()} {contract_path} trả 400 nhưng contract không khai"
    )


@pytest.mark.parametrize(("method", "_url", "contract_path"), SCOPED)
def test_generated_schema_declares_same_codes_as_contract(spec, method, _url, contract_path):
    generated = SchemaGenerator().get_schema(request=None, public=True)["paths"][contract_path]
    assert set(generated[method]["responses"]) == set(
        spec["paths"][contract_path][method]["responses"]
    )
