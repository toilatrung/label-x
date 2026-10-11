"""Metric vận hành queue/shard của QC Run (NFR-12, BLOCKER-026, CR-109).

Tính từ trạng thái DB hiện có (QCRun, WorkUnit, ShardCommit, LedgerUnit, CandidateRecord),
không cần migration, xuất theo Prometheus text exposition format 0.0.4.

Quy tắc đếm (khớp CR-109):
- Mỗi WorkUnit là một shard; chỉ đếm trạng thái hiện tại của nó, nên retry-failed không làm
  một shard bị đếm hai lần (failed -> pending -> completed chỉ còn là một shard completed).
- shard_duration = finished_at - started_at của WorkUnit ở trạng thái cuối (completed/failed)
  có đủ hai mốc, tức là của lần thử gần nhất. retry-failed xoá started_at/finished_at nên
  thời gian của lần thử lỗi trước không bị cộng dồn.
- shard_error_ratio = failed / (completed + failed); cancelled/pending/running không vào mẫu số.
- shard_retries = sum(attempt - 1); tách riêng khỏi số shard.
- shard_queue_wait = started_at - run.created_at, chỉ cho WorkUnit attempt = 1 (lần chạy đầu);
  lần thử lại không tính vì started_at đã bị đặt lại.
- run_queue_latency = run.started_at - run.created_at (started_at chỉ đặt một lần).
- Label chỉ gồm engine, status, outcome (số giá trị nhỏ); không có run_id.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from django.db.models import Count, DurationField, ExpressionWrapper, F, Q, QuerySet, Sum

from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from runs.models import QCRun, WorkUnit

BUCKETS: tuple[float, ...] = (0.1, 0.5, 1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600)
_TERMINAL_SHARD = (WorkUnit.Status.COMPLETED, WorkUnit.Status.FAILED)
_TERMINAL_RUN = (QCRun.Status.COMPLETED, QCRun.Status.PARTIAL, QCRun.Status.FAILED)

Labels = tuple[tuple[str, str], ...]


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _fmt(value: float) -> str:
    return repr(float(value)) if value != int(value) else str(int(value))


def _series(name: str, labels: Labels, value: float) -> str:
    if not labels:
        return f"{name} {_fmt(value)}"
    body = ",".join(f'{k}="{_esc(v)}"' for k, v in labels)
    return f"{name}{{{body}}} {_fmt(value)}"


class _Out:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def header(self, name: str, kind: str, help_text: str) -> None:
        self.lines.append(f"# HELP {name} {help_text}")
        self.lines.append(f"# TYPE {name} {kind}")

    def sample(self, name: str, labels: Labels, value: float) -> None:
        self.lines.append(_series(name, labels, value))

    def histogram(
        self,
        name: str,
        help_text: str,
        rows: Iterable[tuple[Labels, dict[str, Any]]],
    ) -> None:
        self.header(name, "histogram", help_text)
        for labels, agg in rows:
            for bound in BUCKETS:
                self.sample(f"{name}_bucket", (*labels, ("le", _fmt(bound))), agg[f"b{bound}"])
            self.sample(f"{name}_bucket", (*labels, ("le", "+Inf")), agg["count"])
            self.sample(f"{name}_sum", labels, agg["sum"])
            self.sample(f"{name}_count", labels, agg["count"])


def _seconds(td: timedelta | None) -> float:
    return td.total_seconds() if td is not None else 0.0


def _hist_rows(qs: QuerySet[Any], expr: Any, group: str) -> list[tuple[Labels, dict[str, Any]]]:
    """Gom histogram theo một label (group) bằng aggregate DB; expr là DurationField."""
    aggregates: dict[str, Any] = {"count": Count("pk"), "sum_td": Sum("_dur")}
    for bound in BUCKETS:
        aggregates[f"b{bound}"] = Count("pk", filter=Q(_dur__lte=timedelta(seconds=bound)))
    rows = (
        qs.annotate(_dur=ExpressionWrapper(expr, output_field=DurationField()))
        .filter(_dur__gte=timedelta(0))
        .values(group)
        .annotate(**aggregates)
        .order_by(group)
    )
    out: list[tuple[Labels, dict[str, Any]]] = []
    for row in rows:
        agg = {k: row[k] for k in aggregates if k != "sum_td"}
        agg["sum"] = _seconds(row["sum_td"])
        out.append((((group_label(group), str(row[group])),), agg))
    return out


def group_label(group: str) -> str:
    return "engine" if group == "engine" else "status"


def render_metrics() -> str:
    """Trả về toàn bộ metric ở dạng Prometheus text (kết thúc bằng newline)."""
    out = _Out()
    units = WorkUnit.objects.all()

    out.header("labelx_shard_units", "gauge", "Số shard (WorkUnit) theo engine và trạng thái.")
    for row in (
        units.values("engine", "status").annotate(n=Count("pk")).order_by("engine", "status")
    ):
        out.sample(
            "labelx_shard_units", (("engine", row["engine"]), ("status", row["status"])), row["n"]
        )

    out.header(
        "labelx_shard_retries_total",
        "counter",
        "Tổng số lần thử lại shard (sum(attempt - 1)), tách khỏi số shard.",
    )
    for row in units.values("engine").annotate(n=Sum(F("attempt") - 1)).order_by("engine"):
        out.sample("labelx_shard_retries_total", (("engine", row["engine"]),), row["n"] or 0)

    out.header(
        "labelx_shard_error_ratio",
        "gauge",
        "Tỉ lệ shard lỗi = failed / (completed + failed) theo engine; 0 khi chưa có shard cuối.",
    )
    for row in (
        units.filter(status__in=_TERMINAL_SHARD)
        .values("engine")
        .annotate(failed=Count("pk", filter=Q(status=WorkUnit.Status.FAILED)), total=Count("pk"))
        .order_by("engine")
    ):
        out.sample(
            "labelx_shard_error_ratio", (("engine", row["engine"]),), row["failed"] / row["total"]
        )

    terminal = units.filter(
        status__in=_TERMINAL_SHARD, started_at__isnull=False, finished_at__isnull=False
    )
    out.histogram(
        "labelx_shard_duration_seconds",
        "Thời gian xử lý shard ở trạng thái cuối, của lần thử gần nhất.",
        _hist_rows(terminal, F("finished_at") - F("started_at"), "engine"),
    )
    first_attempt = units.filter(attempt=1, started_at__isnull=False)
    out.histogram(
        "labelx_shard_queue_wait_seconds",
        "Độ trễ từ lúc tạo run đến lúc shard chạy lần đầu (attempt = 1).",
        _hist_rows(first_attempt, F("started_at") - F("run__created_at"), "engine"),
    )

    runs = QCRun.objects.all()
    out.header("labelx_runs", "gauge", "Số QC Run theo trạng thái.")
    for row in runs.values("status").annotate(n=Count("pk")).order_by("status"):
        out.sample("labelx_runs", (("status", row["status"]),), row["n"])
    out.histogram(
        "labelx_run_queue_latency_seconds",
        "Độ trễ từ lúc tạo run đến lúc run bắt đầu chạy.",
        _hist_rows(
            runs.filter(started_at__isnull=False),
            F("started_at") - F("created_at"),
            "status",
        ),
    )
    out.histogram(
        "labelx_run_duration_seconds",
        "Thời gian chạy run đã kết thúc (finished_at - started_at) theo trạng thái cuối.",
        _hist_rows(
            runs.filter(
                status__in=_TERMINAL_RUN, started_at__isnull=False, finished_at__isnull=False
            ),
            F("finished_at") - F("started_at"),
            "status",
        ),
    )

    out.header("labelx_shard_commits", "gauge", "Số ShardCommit đã ghi theo engine.")
    for row in ShardCommit.objects.values("engine").annotate(n=Count("pk")).order_by("engine"):
        out.sample("labelx_shard_commits", (("engine", row["engine"]),), row["n"])
    out.header("labelx_candidates", "gauge", "Số candidate đã ghi theo engine.")
    for row in CandidateRecord.objects.values("engine").annotate(n=Count("pk")).order_by("engine"):
        out.sample("labelx_candidates", (("engine", row["engine"]),), row["n"])
    out.header("labelx_ledger_units", "gauge", "Số đơn vị ledger theo engine và outcome.")
    for row in (
        LedgerUnit.objects.values("engine", "outcome")
        .annotate(n=Count("pk"))
        .order_by("engine", "outcome")
    ):
        out.sample(
            "labelx_ledger_units",
            (("engine", row["engine"]), ("outcome", row["outcome"])),
            row["n"],
        )

    return "\n".join(out.lines) + "\n"
