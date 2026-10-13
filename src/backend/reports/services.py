from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from typing import cast

from django.db import IntegrityError, transaction
from django.db.models import Count

from engines.interface import EngineStatus, public_status
from orchestration.services import ledger_counts
from reports.models import ReportExport
from review.lineage import operational_source
from review.models import FrameReview, Issue
from runs.models import QCRun
from snapshots.models import SnapshotFrame


class ExportIdempotencyConflict(RuntimeError):
    pass


def _engine_coverage(run: QCRun) -> list[dict[str, object]]:
    finished = run.status not in (QCRun.Status.QUEUED, QCRun.Status.RUNNING)
    rows: list[dict[str, object]] = []
    for result in run.engine_results.all().order_by("engine"):
        counts = ledger_counts(run.pk, result.engine)
        displayed_status = result.status
        if counts.total:
            displayed_status = public_status(counts, finished=finished).value
        elif finished and displayed_status == EngineStatus.RUNNING:
            displayed_status = EngineStatus.NOT_CHECKED
        rows.append(
            {
                "engine": result.engine,
                "status": displayed_status,
                "required": result.required,
                "unit": result.unit,
                "total": counts.total,
                "eligible": counts.eligible,
                "excluded": counts.excluded,
                "applicability_version": result.applicability_version,
                "completed": counts.completed,
                "failed": counts.failed,
                "pending": counts.pending,
                "not_checked": counts.not_checked,
                "not_checked_reasons": {
                    key.value: value for key, value in counts.not_checked_reasons.items()
                },
                "coverage": counts.coverage,
            }
        )
    return rows


def _run_metrics(run: QCRun) -> dict[str, object]:
    frames_total = SnapshotFrame.objects.filter(snapshot_job__snapshot_id=run.snapshot_id).count()
    reviews = FrameReview.objects.filter(run=run)
    frames_reviewed = reviews.filter(
        state__in=[FrameReview.State.REVIEWED, FrameReview.State.COMPLETED]
    ).count()
    issues = Issue.objects.filter(frame_review__run=run)
    family_counts = Counter(
        dict(issues.values("family").annotate(total=Count("id")).values_list("family", "total"))
    )
    state_counts = Counter(
        dict(issues.values("state").annotate(total=Count("id")).values_list("state", "total"))
    )
    return {
        "run_id": run.pk,
        "status": run.status,
        "frames_total": frames_total,
        "frames_reviewed": frames_reviewed,
        "issues_total": issues.count(),
        "issues_by_family": dict(family_counts),
        "issues_by_state": dict(state_counts),
        "reviewed_ratio": frames_reviewed / frames_total if frames_total else None,
    }


def build_run_report(run: QCRun) -> dict[str, object]:
    source_info = operational_source(run)
    source_id = cast(int, source_info["run_id"])
    source = QCRun.objects.prefetch_related("engine_results").get(pk=source_id)

    # Imported lazily so reports remains usable while release migrations are being applied.
    from releases.models import Release

    release = Release.objects.filter(run=source).order_by("-created_at", "-pk").first()
    return {
        "run_id": run.pk,
        "snapshot_id": run.snapshot_id,
        "source_run_id": source.pk,
        "source_reason": source_info["reason"],
        "score_version": source.score_version or None,
        "generated_at": source.finished_at or source.created_at,
        "metrics": _run_metrics(source),
        "gate": release.gate if release is not None else None,
        "engine_coverage": _engine_coverage(source),
        "release_id": release.pk if release is not None else None,
        "exports": list(run.report_exports.all().order_by("created_at", "pk")),
    }


def _request_hash(run_id: int, export_format: str) -> str:
    raw = json.dumps(
        {"format": export_format, "run_id": run_id}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def create_report_export(
    *, run: QCRun, export_format: str, idempotency_key: str
) -> tuple[ReportExport, bool]:
    request_hash = _request_hash(run.pk, export_format)
    try:
        with transaction.atomic():
            by_key = (
                ReportExport.objects.select_for_update()
                .filter(idempotency_key=idempotency_key)
                .first()
            )
            if by_key is not None:
                if by_key.request_sha256 != request_hash:
                    raise ExportIdempotencyConflict(
                        "Idempotency-Key đã được dùng với yêu cầu export khác."
                    )
                return by_key, False
            existing = (
                ReportExport.objects.select_for_update()
                .filter(run=run, format=export_format)
                .first()
            )
            if existing is not None:
                return existing, False
            export = ReportExport.objects.create(
                run=run,
                format=export_format,
                idempotency_key=idempotency_key,
                request_sha256=request_hash,
            )
            return export, True
    except IntegrityError:
        by_key = ReportExport.objects.filter(idempotency_key=idempotency_key).first()
        if by_key is not None:
            if by_key.request_sha256 != request_hash:
                raise ExportIdempotencyConflict(
                    "Idempotency-Key đã được dùng với yêu cầu export khác."
                ) from None
            return by_key, False
        existing = ReportExport.objects.filter(run=run, format=export_format).first()
        if existing is not None:
            return existing, False
        raise


def _flat_rows(report: dict[str, object]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key in ("run_id", "snapshot_id", "source_run_id", "source_reason", "score_version"):
        rows.append((key, "" if report[key] is None else str(report[key])))
    metrics = report["metrics"]
    if isinstance(metrics, dict):
        for key in sorted(metrics):
            value = metrics[key]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, sort_keys=True, separators=(",", ":"))
            rows.append((f"metrics.{key}", "" if value is None else str(value)))
    return rows


def _minimal_pdf(lines: list[str]) -> bytes:
    def escape(value: str) -> str:
        return (
            value.encode("ascii", "replace")
            .decode()
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )

    commands = ["BT", "/F1 10 Tf", "50 790 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -14 Td")
        commands.append(f"({escape(line)}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(output)


def render_report(report: dict[str, object], export_format: str) -> tuple[bytes, str]:
    serializable = dict(report)
    exports = cast(list[object], report.get("exports", []))
    serializable["exports"] = [
        {
            "id": item.pk,
            "run_id": item.run_id,
            "format": item.format,
            "status": item.status,
            "created_at": item.created_at.isoformat(),
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        }
        for item in exports
        if isinstance(item, ReportExport)
    ]
    generated_at = serializable.get("generated_at")
    if hasattr(generated_at, "isoformat"):
        serializable["generated_at"] = generated_at.isoformat()
    if export_format == ReportExport.Format.JSON:
        return (
            json.dumps(
                serializable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode(),
            "application/json",
        )
    rows = _flat_rows(serializable)
    if export_format == ReportExport.Format.CSV:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["field", "value"])
        writer.writerows(rows)
        return buffer.getvalue().encode("utf-8"), "text/csv"
    if export_format == ReportExport.Format.PDF:
        return _minimal_pdf([f"{key}: {value}" for key, value in rows]), "application/pdf"
    raise ValueError(f"unsupported report format: {export_format}")
