"""Metric queue/shard xuất ra ngoài qua GET /internal/metrics (CR-109, BLOCKER-026)."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from engines.interface import EngineInput, EngineOutput, EngineUnitResult
from orchestration.dispatch import dispatch_run
from orchestration.registry import registry
from runs.models import QCRun, WorkUnit
from runs.services import retry_failed_qc_run
from tests.orchestration.helpers import make_run

pytestmark = pytest.mark.django_db(transaction=True)

ENGINE = "duplicate_overlap"
URL = "/internal/metrics/"


def _client(role: Role | None, dataset_id: int | None = None, name: str = "u") -> APIClient:
    user, created = User.objects.get_or_create(username=f"{name}-{role}-{dataset_id}")
    if role is not None and created:
        RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    client = APIClient()
    client.force_authenticate(user)
    return client


def _scrape() -> str:
    response = _client(Role.SUPER_ADMIN).get(URL)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain; version=0.0.4")
    return str(response.content.decode())


def _value(text: str, series: str) -> float:
    match = re.search(rf"^{re.escape(series)} (\S+)$", text, re.M)
    assert match, f"thiếu series {series}\n{text}"
    return float(match.group(1))


@pytest.fixture
def inline_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    from orchestration.dispatch import run_work_unit

    monkeypatch.setattr(run_work_unit, "delay", lambda pk: run_work_unit.apply(args=(pk,)))


def _runner(state: dict[str, bool]) -> Callable[[EngineInput], EngineOutput]:
    def runner(inp: EngineInput) -> EngineOutput:
        if inp.shard_index == 0 and state["fail"]:
            raise ValueError("lỗi cố định")
        return EngineOutput(
            inp.idempotency_key,
            inp.engine,
            inp.engine_version,
            (),
            tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
        )

    return runner


# --- RBAC: 7 vai trò ---------------------------------------------------------------


@pytest.mark.parametrize("role", [Role.QC_ADMIN, Role.SUPER_ADMIN])
def test_system_wide_ops_roles_allowed(role: Role) -> None:
    assert _client(role, None).get(URL).status_code == 200


@pytest.mark.parametrize(
    "role",
    [
        Role.ANNOTATOR,
        Role.REVIEWER,
        Role.QA_LEAD,
        Role.PRODUCT_OWNER,
        Role.DATA_MODEL_OWNER,
        Role.QC_ADMIN,  # chỉ gán theo dataset: metric gộp mọi dataset nên bị từ chối
    ],
)
def test_other_roles_and_dataset_scoped_admin_denied(role: Role) -> None:
    response = _client(role, 42).get(URL)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


def test_all_seven_roles_covered() -> None:
    assert len(Role.values) == 7


def test_user_without_role_and_anonymous_denied() -> None:
    assert _client(None).get(URL).status_code == 403
    anon = APIClient().get(URL)
    assert anon.status_code == 403
    assert anon.json()["code"] == "NOT_AUTHENTICATED"


def test_write_methods_not_allowed() -> None:
    assert _client(Role.SUPER_ADMIN).post(URL).status_code == 405


# --- Đếm ---------------------------------------------------------------------------


def test_empty_db_exposes_valid_text() -> None:
    text = _scrape()
    assert text.endswith("\n")
    assert "# TYPE labelx_shard_duration_seconds histogram" in text


def test_success_flow_counts_duration_queue_and_zero_error(
    inline_queue: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "runner", lambda n, v: _runner({"fail": False}))
    run = make_run(engine=ENGINE)
    dispatch_run(run.pk)
    text = _scrape()
    assert _value(text, f'labelx_shard_units{{engine="{ENGINE}",status="completed"}}') == 2
    assert _value(text, f'labelx_shard_retries_total{{engine="{ENGINE}"}}') == 0
    assert _value(text, f'labelx_shard_error_ratio{{engine="{ENGINE}"}}') == 0
    assert _value(text, f'labelx_shard_duration_seconds_count{{engine="{ENGINE}"}}') == 2
    assert _value(text, f'labelx_shard_queue_wait_seconds_count{{engine="{ENGINE}"}}') == 2
    assert _value(text, 'labelx_runs{status="completed"}') == 1
    assert _value(text, 'labelx_run_duration_seconds_count{status="completed"}') == 1
    assert _value(text, 'labelx_run_queue_latency_seconds_count{status="completed"}') == 1
    assert _value(text, f'labelx_shard_commits{{engine="{ENGINE}"}}') == 2
    assert "run_id" not in text


def test_failed_then_retry_failed_does_not_double_count(
    inline_queue: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"fail": True}
    monkeypatch.setattr(registry, "runner", lambda n, v: _runner(state))
    run = make_run(engine=ENGINE)
    dispatch_run(run.pk)
    assert QCRun.objects.get(pk=run.pk).status == QCRun.Status.PARTIAL

    text = _scrape()
    assert _value(text, f'labelx_shard_units{{engine="{ENGINE}",status="failed"}}') == 1
    assert _value(text, f'labelx_shard_units{{engine="{ENGINE}",status="completed"}}') == 1
    assert _value(text, f'labelx_shard_error_ratio{{engine="{ENGINE}"}}') == 0.5
    assert _value(text, f'labelx_shard_duration_seconds_count{{engine="{ENGINE}"}}') == 2
    assert _value(text, 'labelx_runs{status="partial"}') == 1

    state["fail"] = False
    retry_failed_qc_run(run_id=run.pk, actor=run.created_by)
    # Ngay sau retry: shard lỗi chuyển pending, không còn trong mẫu số lỗi/thời lượng.
    text = _scrape()
    assert _value(text, f'labelx_shard_units{{engine="{ENGINE}",status="pending"}}') == 1
    assert _value(text, f'labelx_shard_retries_total{{engine="{ENGINE}"}}') == 1
    assert _value(text, f'labelx_shard_error_ratio{{engine="{ENGINE}"}}') == 0
    assert _value(text, f'labelx_shard_duration_seconds_count{{engine="{ENGINE}"}}') == 1

    dispatch_run(run.pk)
    text = _scrape()
    assert _value(text, f'labelx_shard_units{{engine="{ENGINE}",status="completed"}}') == 2
    assert _value(text, f'labelx_shard_retries_total{{engine="{ENGINE}"}}') == 1
    assert _value(text, f'labelx_shard_error_ratio{{engine="{ENGINE}"}}') == 0
    # Mỗi shard đúng một mẫu thời lượng; lần thử lỗi trước không bị cộng dồn.
    assert _value(text, f'labelx_shard_duration_seconds_count{{engine="{ENGINE}"}}') == 2
    # Queue wait chỉ tính lần chạy đầu: shard retry (attempt=2) không vào mẫu.
    assert _value(text, f'labelx_shard_queue_wait_seconds_count{{engine="{ENGINE}"}}') == 1
    assert _value(text, 'labelx_runs{status="completed"}') == 1
    assert 'labelx_runs{status="partial"}' not in text


def test_histogram_buckets_sum_and_values() -> None:
    run = make_run(engine=ENGINE)
    base = run.created_at
    QCRun.objects.filter(pk=run.pk).update(
        status=QCRun.Status.COMPLETED,
        started_at=base + timedelta(seconds=3),
        finished_at=base + timedelta(seconds=13),
    )
    first, second = run.work_units.order_by("shard_index")
    WorkUnit.objects.filter(pk=first.pk).update(
        status=WorkUnit.Status.COMPLETED,
        started_at=base + timedelta(seconds=2),
        finished_at=base + timedelta(seconds=6),  # 4s
    )
    WorkUnit.objects.filter(pk=second.pk).update(
        status=WorkUnit.Status.FAILED,
        started_at=base + timedelta(seconds=4),
        finished_at=base + timedelta(seconds=34),  # 30s
    )
    text = _scrape()
    prefix = f'labelx_shard_duration_seconds_bucket{{engine="{ENGINE}",le='
    assert _value(text, prefix + '"1"}') == 0
    assert _value(text, prefix + '"5"}') == 1
    assert _value(text, prefix + '"30"}') == 2
    assert _value(text, prefix + '"+Inf"}') == 2
    assert _value(text, f'labelx_shard_duration_seconds_sum{{engine="{ENGINE}"}}') == 34
    assert _value(text, f'labelx_shard_queue_wait_seconds_sum{{engine="{ENGINE}"}}') == 6
    assert _value(text, f'labelx_shard_error_ratio{{engine="{ENGINE}"}}') == 0.5
    assert _value(text, 'labelx_run_queue_latency_seconds_sum{status="completed"}') == 3
    assert _value(text, 'labelx_run_duration_seconds_sum{status="completed"}') == 10


def test_non_terminal_units_not_in_error_ratio() -> None:
    run = make_run(engine=ENGINE)
    WorkUnit.objects.filter(run=run).update(
        status=WorkUnit.Status.CANCELLED, finished_at=timezone.now()
    )
    text = _scrape()
    assert f'labelx_shard_error_ratio{{engine="{ENGINE}"}}' not in text
    assert _value(text, f'labelx_shard_units{{engine="{ENGINE}",status="cancelled"}}') == 2
