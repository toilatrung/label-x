"""Unit test cho scripts/development/m03_readiness.py — mock hoàn toàn, không cần dịch vụ thật."""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "m03_readiness", ROOT / "scripts" / "development" / "m03_readiness.py"
)
assert _spec and _spec.loader
m: Any = importlib.util.module_from_spec(_spec)
sys.modules["m03_readiness"] = m  # dataclass cần module có trong sys.modules
_spec.loader.exec_module(m)
NOW = datetime(2026, 10, 12, tzinfo=UTC)
FULL_ENV = {k: "x-real" for k in m.REQUIRED_ENV}


def test_env_reports_only_names_never_values(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text(
        "DJANGO_SECRET_KEY=change-me\nCVAT_SERVICE_TOKEN=\nDATABASE_URL=postgres://u:pw@h/d\n"
    )
    c = m.check_env(m.parse_env_file(f))
    assert c.status == m.FAIL
    assert "DJANGO_SECRET_KEY" in c.data["missing"] and "DATABASE_URL" not in c.data["missing"]
    assert "pw" not in json.dumps(m.asdict(c))


def test_env_only_token_missing_is_blocked_not_fail() -> None:
    env = {**FULL_ENV, "CVAT_SERVICE_TOKEN": ""}
    assert m.check_env(env).status == m.BLOCKED
    assert m.check_env(FULL_ENV).status == m.PASS


def test_migrations_pending_fails() -> None:
    assert m.check_migrations(lambda: ["review.0003_x"]).status == m.FAIL
    assert m.check_migrations(list).status == m.PASS


def test_worker_and_redis() -> None:
    assert m.check_celery_worker(lambda: None).status == m.FAIL
    assert m.check_celery_worker(lambda: {"w@h": {"ok": "pong"}}).status == m.PASS
    assert m.check_redis(lambda: False).status == m.FAIL


def test_beat_is_never_pass_without_recent_run() -> None:
    assert m.check_celery_beat(lambda: [None], NOW).status == m.UNKNOWN
    assert m.check_celery_beat(lambda: [NOW - timedelta(days=2)], NOW).status == m.UNKNOWN
    assert m.check_celery_beat(lambda: [NOW - timedelta(minutes=5)], NOW).status == m.PASS


def test_object_storage_lists_failing_buckets() -> None:
    c = m.check_object_storage(lambda b: b != "bad", ["ok", "bad"])
    assert c.status == m.FAIL and "bad" in c.detail
    assert m.check_object_storage(lambda _b: True, ["ok"]).status == m.PASS


def test_cvat_token_not_configured_is_blocked_and_never_calls_server() -> None:
    def boom() -> int:
        raise AssertionError("must not call")

    c = m.check_cvat_token(False, boom)
    assert c.status == m.BLOCKED and c.data == {"configured": False}
    assert m.check_cvat_token(True, lambda: 401).status == m.FAIL
    assert m.check_cvat_token(True, lambda: 200).status == m.PASS


def test_cvat_job_states() -> None:
    assert m.check_cvat_job(False, lambda: None, lambda _i: {}).status == m.BLOCKED
    assert m.check_cvat_job(True, lambda: None, lambda _i: {}).status == m.BLOCKED
    info = {"has_assignee": True, "has_revision": True, "frame_count": 3}
    c = m.check_cvat_job(True, lambda: {"id": 7}, lambda _i: info)
    assert c.status == m.PASS and c.data["has_assignee"] is True


def test_policy_must_match_pilot() -> None:
    ok = dict(m.PILOT_POLICY)
    assert m.check_review_policy(lambda: ok).status == m.PASS
    bad = {**ok, "lease_ttl_seconds": 60}
    c = m.check_review_policy(lambda: bad)
    assert c.status == m.FAIL and c.data["mismatch"] == {"lease_ttl_seconds": 60}


def test_guideline_and_taxonomy() -> None:
    assert m.check_guideline(lambda: None).status == m.BLOCKED
    assert m.check_guideline(lambda: ("v1", 0)).status == m.FAIL
    assert m.check_guideline(lambda: ("v1", 12)).status == m.PASS
    assert m.check_taxonomy(lambda: []).status == m.BLOCKED
    assert m.check_taxonomy(lambda: ["", "bdd100k-v1"]).data["versions"] == ["bdd100k-v1"]


def test_guard_hides_exception_message() -> None:
    def raiser() -> Any:
        raise RuntimeError("password=hunter2")

    c = m._guard("x", raiser)
    assert c.status == m.FAIL and "hunter2" not in c.detail


def test_exit_codes() -> None:
    P, F, B = m.Check("a", m.PASS, ""), m.Check("b", m.FAIL, ""), m.Check("c", m.BLOCKED, "")
    assert m.summarize([P])[1] == 0
    assert m.summarize([P, B])[1] == 2
    report, code = m.summarize([P, B, F])
    assert code == 1 and report["overall"] == "NOT_READY" and report["counts"]["BLOCKED"] == 1
