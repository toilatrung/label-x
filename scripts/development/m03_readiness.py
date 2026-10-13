#!/usr/bin/env python3
"""M-03 R11: kiểm tra sẵn sàng môi trường E2E — CHỈ ĐỌC, không ghi DB/CVAT/storage.

Chạy: uv run --project src/backend python scripts/development/m03_readiness.py --out readiness.json

Trạng thái mỗi kiểm tra: PASS | FAIL | BLOCKED | UNKNOWN.
- BLOCKED: thiếu đầu vào do PO/Hà cung cấp (vd. chưa cấu hình token) — không phải lỗi mã nguồn.
- UNKNOWN: không xác định được từ phía client (vd. Celery beat) — không tính là PASS.
Mã thoát: 0 = mọi kiểm tra PASS; 1 = có FAIL; 2 = không FAIL nhưng có BLOCKED/UNKNOWN.
Không in token/mật khẩu/giá trị biến: chỉ có/không và tên biến thiếu.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PASS, FAIL, BLOCKED, UNKNOWN = "PASS", "FAIL", "BLOCKED", "UNKNOWN"
REQUIRED_ENV = (
    "DJANGO_SECRET_KEY",
    "DATABASE_URL",
    "CELERY_BROKER_URL",
    "OBJECT_STORAGE_ENDPOINT_URL",
    "OBJECT_STORAGE_ACCESS_KEY",
    "OBJECT_STORAGE_SECRET_KEY",
    "OBJECT_STORAGE_BUCKET_SNAPSHOTS",
    "OBJECT_STORAGE_BUCKET_EVIDENCE",
    "OBJECT_STORAGE_BUCKET_REPORTS",
    "CVAT_BASE_URL",
    "CVAT_SERVICE_TOKEN",
)
# Giá trị placeholder trong .env.example: coi như chưa cấu hình thật.
PLACEHOLDER_VALUES = {"change-me", ""}
PILOT_POLICY = {
    "lease_ttl_seconds": 900,
    "resume_reservation_seconds": 300,
    "idle_threshold_seconds": 120,
    "policy_version": "pilot-1",
}
BEAT_STALE_AFTER = timedelta(hours=1)


@dataclass
class Check:
    name: str
    status: str
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


def _guard(name: str, fn: Callable[[], Check]) -> Check:
    """Một kiểm tra lỗi không được làm hỏng cả báo cáo; chỉ báo tên lỗi, không in thông điệp."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - mọi lỗi hạ tầng đều thành FAIL có kiểm soát
        return Check(name, FAIL, f"{type(exc).__name__} (chi tiết bị ẩn để không lộ bí mật)")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def check_env(env: dict[str, str]) -> Check:
    missing = sorted(k for k in REQUIRED_ENV if env.get(k, "").strip() in PLACEHOLDER_VALUES)
    if missing:
        blocked = "CVAT_SERVICE_TOKEN" in missing and len(missing) == 1
        return Check(
            "env_vars",
            BLOCKED if blocked else FAIL,
            "thiếu/rỗng: " + ", ".join(missing),
            {"missing": missing},
        )
    return Check("env_vars", PASS, f"đủ {len(REQUIRED_ENV)} biến bắt buộc", {"missing": []})


def check_postgres(connect: Callable[[], Any]) -> Check:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1")
        ok = cur.fetchone() == (1,)
    return Check("postgres", PASS if ok else FAIL, "SELECT 1")


def check_migrations(pending: Callable[[], list[str]]) -> Check:
    todo = pending()
    if todo:
        return Check("migrations", FAIL, f"{len(todo)} migration chưa áp dụng", {"pending": todo})
    return Check("migrations", PASS, "không còn migration chờ", {"pending": []})


def check_redis(ping: Callable[[], bool]) -> Check:
    return Check("redis", PASS if ping() else FAIL, "PING")


def check_celery_worker(inspect_ping: Callable[[], dict[str, Any] | None]) -> Check:
    replies = inspect_ping() or {}
    if not replies:
        return Check("celery_worker", FAIL, "không worker nào trả lời ping")
    return Check("celery_worker", PASS, f"{len(replies)} worker trả lời", {"workers": len(replies)})


def check_celery_beat(last_runs: Callable[[], list[datetime | None]], now: datetime) -> Check:
    """Beat không có API ping; suy ra từ last_run_at của PeriodicTask đang bật (heuristic)."""
    runs = [r for r in last_runs() if r is not None]
    if runs and now - max(runs) <= BEAT_STALE_AFTER:
        return Check("celery_beat", PASS, "có periodic task chạy trong 1 giờ qua (heuristic)")
    return Check(
        "celery_beat",
        UNKNOWN,
        "không có dấu hiệu beat chạy gần đây; cần xác nhận thủ công tiến trình celery beat",
    )


def check_object_storage(head: Callable[[str], bool], buckets: list[str]) -> Check:
    results = {b: head(b) for b in buckets}
    bad = sorted(b for b, ok in results.items() if not ok)
    if bad:
        return Check("object_storage", FAIL, "bucket không đọc được: " + ", ".join(bad), results)
    return Check("object_storage", PASS, f"đọc được {len(buckets)} bucket", results)


def check_cvat_reachable(get_about: Callable[[], int]) -> Check:
    code = get_about()
    return Check(
        "cvat_reachable", PASS if code == 200 else FAIL, f"GET /api/server/about -> HTTP {code}"
    )


def check_cvat_token(configured: bool, get_self: Callable[[], int]) -> Check:
    if not configured:
        return Check(
            "cvat_token",
            BLOCKED,
            "CVAT_SERVICE_TOKEN chưa cấu hình (chờ PO/Hà cấp)",
            {"configured": False},
        )
    code = get_self()
    status = PASS if code == 200 else FAIL
    return Check(
        "cvat_token",
        status,
        f"token đã cấu hình; GET /api/users/self -> HTTP {code}",
        {"configured": True},
    )


def check_cvat_job(
    configured: bool,
    first_job: Callable[[], dict[str, Any] | None],
    read_job: Callable[[int], dict[str, Any]],
) -> Check:
    if not configured:
        return Check("cvat_job_readable", BLOCKED, "không có token CVAT nên không đọc được job")
    job = first_job()
    if job is None:
        return Check(
            "cvat_job_readable", BLOCKED, "CVAT không có job nào (chờ PO/Hà cung cấp job thật)"
        )
    info = read_job(int(job["id"]))
    return Check(
        "cvat_job_readable",
        PASS,
        "đọc được job, meta và annotations (GET)",
        {k: info.get(k) for k in ("has_assignee", "has_revision", "frame_count")},
    )


def check_review_policy(policy: Callable[[], dict[str, Any]]) -> Check:
    got = policy()
    diff = {k: got.get(k) for k, v in PILOT_POLICY.items() if got.get(k) != v}
    if diff:
        return Check("review_policy", FAIL, "lệch pilot 900/300/120/pilot-1", {"mismatch": diff})
    return Check(
        "review_policy", PASS, "900/300/120/pilot-1", {k: got.get(k) for k in PILOT_POLICY}
    )


def check_guideline(latest: Callable[[], tuple[str, int] | None]) -> Check:
    got = latest()
    if got is None:
        return Check(
            "guideline", BLOCKED, "chưa nạp guideline (load_guideline cần file chính thức)"
        )
    tag, rules = got
    return Check(
        "guideline", PASS if rules > 0 else FAIL, f"{tag}: {rules} rule", {"version_tag": tag}
    )


def check_taxonomy(versions: Callable[[], list[str]]) -> Check:
    vs = sorted(v for v in versions() if v)
    if not vs:
        return Check(
            "taxonomy_version",
            BLOCKED,
            "chưa có snapshot mang taxonomy_version (chờ taxonomy chính thức)",
        )
    return Check("taxonomy_version", PASS, f"{len(vs)} taxonomy_version", {"versions": vs})


def summarize(checks: list[Check]) -> tuple[dict[str, Any], int]:
    counts = {s: sum(c.status == s for c in checks) for s in (PASS, FAIL, BLOCKED, UNKNOWN)}
    code = 1 if counts[FAIL] else (2 if counts[BLOCKED] or counts[UNKNOWN] else 0)
    overall = {0: "READY", 1: "NOT_READY", 2: "BLOCKED"}[code]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "overall": overall,
        "exit_code": code,
        "counts": counts,
        "checks": [asdict(c) for c in checks],
    }
    return report, code


# ---- nối với hạ tầng thật (chỉ đọc) ---------------------------------------------------------
def _setup_django(root: Path) -> None:
    sys.path.insert(0, str(root / "src" / "backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def run_live(root: Path, timeout: float) -> list[Check]:
    env = {**parse_env_file(root / "src" / "backend" / ".env"), **os.environ}
    checks = [check_env(env)]
    # Django cần DJANGO_SECRET_KEY/DATABASE_URL; thiếu thì các kiểm tra phụ thuộc không chạy được.
    try:
        _setup_django(root)
    except Exception as exc:  # noqa: BLE001
        checks.append(Check("django_setup", FAIL, f"{type(exc).__name__}: không nạp được settings"))
        return checks

    import boto3
    import httpx
    import psycopg
    import redis
    from botocore.config import Config
    from django.conf import settings as _settings
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from cvat_adapter.client import CvatReadClient

    settings: Any = _settings
    now = datetime.now(UTC)
    db_url = settings.DATABASES["default"]
    checks.append(
        _guard(
            "postgres",
            lambda: check_postgres(
                lambda: psycopg.connect(
                    host=db_url["HOST"],
                    port=db_url["PORT"] or 5432,
                    dbname=db_url["NAME"],
                    user=db_url["USER"],
                    password=db_url["PASSWORD"],
                    connect_timeout=int(timeout),
                )
            ),
        )
    )

    def pending() -> list[str]:
        ex = MigrationExecutor(connection)
        plan = ex.migration_plan(ex.loader.graph.leaf_nodes())
        return [f"{m.app_label}.{m.name}" for m, _ in plan]

    checks.append(_guard("migrations", lambda: check_migrations(pending)))
    checks.append(
        _guard(
            "redis",
            lambda: check_redis(
                lambda: bool(
                    redis.Redis.from_url(
                        settings.CELERY_BROKER_URL, socket_connect_timeout=timeout
                    ).ping()
                )
            ),
        )
    )

    def worker_ping() -> dict[str, Any] | None:
        from config.celery import app

        return app.control.inspect(timeout=timeout).ping()

    checks.append(_guard("celery_worker", lambda: check_celery_worker(worker_ping)))

    def beat_runs() -> list[datetime | None]:
        from django_celery_beat.models import PeriodicTask

        return list(PeriodicTask.objects.filter(enabled=True).values_list("last_run_at", flat=True))

    checks.append(_guard("celery_beat", lambda: check_celery_beat(beat_runs, now)))

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.STORAGES["snapshots"]["OPTIONS"].get("endpoint_url"),
        aws_access_key_id=settings.STORAGES["snapshots"]["OPTIONS"].get("access_key"),
        aws_secret_access_key=settings.STORAGES["snapshots"]["OPTIONS"].get("secret_key"),
        region_name=settings.STORAGES["snapshots"]["OPTIONS"].get("region_name"),
        config=Config(connect_timeout=timeout, retries={"max_attempts": 1}),
    )
    buckets = sorted(
        {
            settings.STORAGES[k]["OPTIONS"]["bucket_name"]
            for k in settings.STORAGES
            if "bucket_name" in settings.STORAGES[k].get("OPTIONS", {})
        }
    )

    def head(bucket: str) -> bool:
        s3.list_objects_v2(Bucket=bucket, MaxKeys=1)  # GET/LIST, không ghi
        return True

    def head_all(bucket: str) -> bool:
        try:
            return head(bucket)
        except Exception:  # noqa: BLE001
            return False

    checks.append(_guard("object_storage", lambda: check_object_storage(head_all, buckets)))

    base = settings.CVAT_BASE_URL.strip()
    token = settings.CVAT_SERVICE_TOKEN.strip()
    configured = bool(token)

    def cvat_status(path: str, auth: bool) -> int:
        headers = {"Authorization": f"Bearer {token}"} if auth else {}
        return httpx.get(base.rstrip("/") + path, headers=headers, timeout=timeout).status_code

    if base:
        checks.append(
            _guard(
                "cvat_reachable",
                lambda: check_cvat_reachable(lambda: cvat_status("/api/server/about", False)),
            )
        )
    else:
        checks.append(Check("cvat_reachable", BLOCKED, "CVAT_BASE_URL chưa cấu hình"))
    checks.append(
        _guard(
            "cvat_token",
            lambda: check_cvat_token(configured, lambda: cvat_status("/api/users/self", True)),
        )
    )

    def first_job() -> dict[str, Any] | None:
        with CvatReadClient(base, token, timeout_seconds=timeout) as c:
            jobs = c.list_jobs(page_size=1, max_pages=1)
        return dict(jobs[0]) if jobs else None

    def read_job(job_id: int) -> dict[str, Any]:
        with CvatReadClient(base, token, timeout_seconds=timeout) as c:
            job = c.get_job(job_id)
            meta = c.get_job_data_meta(job_id)
            ann = c.get_job_annotations(job_id)
        return {
            "has_assignee": bool(job.get("assignee")),
            "has_revision": "version" in ann,
            "frame_count": meta.get("size"),
        }

    checks.append(
        _guard(
            "cvat_job_readable",
            lambda: check_cvat_job(configured and bool(base), first_job, read_job),
        )
    )

    def policy() -> dict[str, Any]:
        from review.policy import current_review_policy

        return current_review_policy()

    checks.append(_guard("review_policy", lambda: check_review_policy(policy)))

    def latest_guideline() -> tuple[str, int] | None:
        from guideline.models import get_latest_guideline_version

        v = get_latest_guideline_version()
        return None if v is None else (v.version_tag, v.rules.count())

    checks.append(_guard("guideline", lambda: check_guideline(latest_guideline)))

    def taxonomy_versions() -> list[str]:
        from snapshots.models import Snapshot

        return list(Snapshot.objects.values_list("taxonomy_version", flat=True).distinct())

    checks.append(_guard("taxonomy_version", lambda: check_taxonomy(taxonomy_versions)))
    return checks


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--out", type=Path, help="ghi báo cáo JSON ra tệp (mặc định: stdout)")
    p.add_argument("--timeout", type=float, default=5.0)
    a = p.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    report, code = summarize(run_live(root, a.timeout))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if a.out:
        a.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
