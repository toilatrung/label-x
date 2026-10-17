"""Stage VLM phụ thuộc candidate (M04A-03, CR-116).

Thứ tự: engine sinh candidate chạy xong (mọi WorkUnit không còn mở) -> `start_vlm_stage` tạo
VlmUnit theo policy `vlm-trigger-v0` -> mỗi VlmUnit chạy qua Celery. VLM không bao giờ chạy
trước
candidate vì VlmUnit chỉ được tạo từ CandidateRecord đã commit.

Budget/retry:
- Budget của run là một dòng VlmBudget; mỗi attempt thực gửi provider tăng `used_calls` bằng
một
  UPDATE có điều kiện (nguyên tử). VlmAttempt unique (unit, attempt_no) nên giao lại cùng
attempt
  không bị tính lần hai.
- Tối đa `max_attempts` (≤ 4: lần đầu + 3 retry) attempt cho mỗi lượt logic; retry/backoff nằm
trong
  `vlm.runner.run_vlm_unit`; production hẹn task sau mỗi lỗi tạm thời và dùng DbBudgetGate.
- VlmUnit unique theo khoá idempotency; tạo lại là no-op. Khoá chuẩn bị bằng `crop_identity`
  (danh tính crop tất định do CropProvider cung cấp), sha256 thật của crop nằm trong kết quả.

VLM chỉ tạo kết quả/đề xuất; không tạo ReviewDecision hay Adjudication.
Lỗi VLM được giữ theo candidate. Retry được lưu và hẹn qua Celery; outage có hạn chờ rõ.
"""

# Historical issue mapping: docs/08-devops/github-issue-migration-2026-10-17.html
# Anchors: issue-289.

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import timedelta
from typing import Any, Protocol

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Exists, F, Max, OuterRef, Q
from django.utils import timezone
from django.utils.module_loading import import_string

from engines.registration import taxonomy_from_params
from orchestration.fail_fast import stop_failed_engines
from orchestration.models import (
    CandidateRecord,
    VlmAttempt,
    VlmBudget,
    VlmEvidence,
    VlmUnit,
)
from orchestration.resources import EndpointLease, ResourceWaiting, retry_delay
from runs.models import QCRun
from vlm.client import DashScopeClient
from vlm.config import VlmConfig, parse_vlm_config, validate_vlm_config
from vlm.contract import (
    CandidateContext,
    CropInput,
    TaxonomyLabel,
    VlmClient,
    VlmRequest,
    VlmStatus,
)
from vlm.errors import VlmDeferred, VlmError, VlmInvalidCropError, VlmReasonCode
from vlm.runner import backoff_seconds, run_vlm_unit
from vlm.tasks import result_to_dict

logger = logging.getLogger("labelx.orchestration")

VLM_ENGINE = "vlm"
TRIGGER_POLICY_VERSION = "classification-routing-v0"  # policy C; pha A dùng vlm-trigger-v0
SKIP_NO_TAXONOMY = "not_applicable"
# Lượt đánh giá logic đầu tiên. Manual recheck/re-evaluate (M04C-02/archive:289) sẽ tăng generation;
# ràng
# buộc unique (run, candidate, generation) và khoá idempotency đã hỗ trợ nhiều generation.
EVALUATION_GENERATION = 1
_OPEN_STATUSES = (VlmUnit.Status.PENDING, VlmUnit.Status.RUNNING)


class CropProvider(Protocol):
    """Nguồn crop của candidate (M04A-04 hiện thực từ snapshot; ở đây là cổng thay thế được)."""

    def identity(self, candidate: CandidateRecord) -> str:
        """Danh tính crop tất định và rẻ (không tải ảnh); chuỗi rỗng nếu không xác định."""
        ...

    def load(self, candidate: CandidateRecord) -> CropInput:
        """Tải crop thật; ném VlmInvalidCropError nếu không lấy được."""
        ...


class NoCropProvider:
    """Nguồn crop rỗng (test/tắt): mọi candidate thành failed/invalid_crop, hiện rõ."""

    def identity(self, candidate: CandidateRecord) -> str:
        return ""

    def load(self, candidate: CandidateRecord) -> CropInput:
        raise VlmInvalidCropError("chưa cấu hình nguồn crop")


def crop_provider() -> CropProvider:
    path = getattr(settings, "VLM_CROP_PROVIDER", "orchestration.vlm_crops.SnapshotCropProvider")
    provider: CropProvider = import_string(path)()
    return provider


def compute_vlm_idempotency_key(
    *,
    evaluation_generation: int,
    candidate_dedup_key: str,
    crop_identity: str,
    snapshot_revision: str,
    policy_version: str,
    model: str,
    prompt_version: str,
) -> str:
    payload = {
        "candidate": candidate_dedup_key,
        "crop_identity": crop_identity,
        "evaluation_generation": evaluation_generation,
        "model": model,
        "policy_version": policy_version,
        "prompt_version": prompt_version,
        "snapshot_revision": snapshot_revision,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def run_vlm_config(run: QCRun) -> dict[str, Any] | None:
    """`models.vlm` của run nếu engine vlm bật và config hợp lệ; ngược lại None."""
    cfg = run.config_version
    engines = cfg.engines or (cfg.payload or {}).get("engines", {})
    vlm_engine = engines.get(VLM_ENGINE) if isinstance(engines, dict) else None
    if not (isinstance(vlm_engine, dict) and vlm_engine.get("enabled")):
        return None
    models_cfg = cfg.models or (cfg.payload or {}).get("models", {})
    raw = models_cfg.get(VLM_ENGINE) if isinstance(models_cfg, dict) else None
    if not isinstance(raw, dict) or validate_vlm_config(raw):
        return None
    return raw


def _taxonomy_for_run(run: QCRun) -> tuple[TaxonomyLabel, ...] | None:
    cfg = run.config_version
    engines = cfg.engines or (cfg.payload or {}).get("engines", {})
    schema = engines.get("schema") if isinstance(engines, dict) else None
    params = schema.get("params") if isinstance(schema, dict) else None
    context = run.snapshot.provenance.get("guideline_context")
    if isinstance(context, dict):
        params = {"taxonomy": context.get("taxonomy")}
    if not isinstance(params, dict):
        return None
    try:
        taxonomy = taxonomy_from_params(params, expected_version=run.snapshot.taxonomy_version)
    except ValueError:
        return None
    return tuple(TaxonomyLabel(str(label.label_id), label.name) for label in taxonomy.labels)


def select_candidates_for_vlm(run: QCRun) -> list[CandidateRecord]:
    """Candidate cần hỏi Qwen theo policy `classification-routing-v0` (M04C-01).

    Chỉ candidate có `call_qwen` (low score, unknown, conflict) được chọn; detector-only,
    invalid_crop và budget_exhausted thì không. Giữ chữ ký của pha A; xem `start_vlm_stage` để ghi
    cả quyết định của candidate không được chọn vào Evaluation.
    """
    from orchestration.evaluation_service import budget_exhausted, route_candidates

    candidates = list(
        CandidateRecord.objects.filter(run_id=run.pk)
        .exclude(engine=VLM_ENGINE)
        .select_related("run")
        .order_by("pk")
    )
    routed = route_candidates(run, candidates, exhausted=budget_exhausted(run.pk))
    return [c for c, decision in routed if decision.call_qwen]


def start_vlm_stage(run_id: int) -> int:
    """Khởi động/bổ sung stage VLM sau khi candidate detector đã sinh xong.

    Idempotent; trả số VlmUnit mới. Mỗi candidate nhận một Evaluation generation 1 ghi quyết định
    định tuyến (kể cả nhánh detector-only, mang reason tương thích FE v0); chỉ candidate cần Qwen
    mới có VlmUnit. Gọi trong
    transaction đã khoá QCRun (refresh_run). Dispatch Celery chạy sau commit.
    """
    from orchestration.evaluation_service import (
        budget_exhausted,
        create_auto_evaluations,
        route_candidates,
    )

    run = QCRun.objects.select_related("config_version", "snapshot").get(pk=run_id)
    if run.retry_engine:
        return 0  # A selected-engine retry must never start another engine/stage.
    if run.cancel_requested_at or run.status not in (QCRun.Status.QUEUED, QCRun.Status.RUNNING):
        return 0
    raw = run_vlm_config(run)
    if raw is None:
        VlmBudget.objects.get_or_create(
            run_id=run_id, defaults={"max_calls": 0, "skipped_reason": "no_model"}
        )
        return 0
    config = parse_vlm_config(raw)
    budget, _ = VlmBudget.objects.get_or_create(
        run_id=run_id, defaults={"max_calls": config.budget.max_calls}
    )
    if _taxonomy_for_run(run) is None:
        # Không có taxonomy của snapshot thì không có gì hợp lệ để hỏi Qwen: không tạo unit.
        if not budget.skipped_reason:
            VlmBudget.objects.filter(pk=budget.pk).update(skipped_reason=SKIP_NO_TAXONOMY)
        return 0
    if budget.used_calls >= budget.max_calls:
        # Settle remaining pending work before refresh_run derives the terminal status.
        # Otherwise the last provider call could leave the run waiting for a sweeper.
        VlmUnit.objects.filter(run_id=run_id, status=VlmUnit.Status.PENDING).update(
            status=VlmUnit.Status.FAILED,
            reason_code="budget_exhausted",
            finished_at=timezone.now(),
            lease_token="",
        )
    from orchestration.models import Evaluation

    evaluated = Evaluation.objects.filter(
        candidate_id=OuterRef("pk"),
        generation=EVALUATION_GENERATION,
    )
    wanted = (
        CandidateRecord.objects.filter(run_id=run_id)
        .exclude(engine=VLM_ENGINE)
        .filter(~Exists(evaluated))
        .select_related("run")
        .order_by("pk")
    )
    created = 0
    if wanted.exists():
        # Keep the candidate selection seam, but invoke it only while preparing new candidates.
        selected = {c.pk for c in select_candidates_for_vlm(run)}
        batch = []
        for candidate in wanted.iterator(chunk_size=500):
            batch.append(candidate)
            if len(batch) == 500:
                routed = route_candidates(run, batch, exhausted=budget_exhausted(run_id))
                created += create_auto_evaluations(run, routed, config, selected_ids=selected)
                batch = []
        if batch:
            routed = route_candidates(run, batch, exhausted=budget_exhausted(run_id))
            created += create_auto_evaluations(run, routed, config, selected_ids=selected)
        logger.info("vlm stage prepared", extra={"qc_run_id": run_id, "vlm_units_created": created})
    if (
        getattr(settings, "ORCHESTRATION_AUTO_DISPATCH", True)
        and VlmUnit.objects.filter(run_id=run_id, status=VlmUnit.Status.PENDING).exists()
    ):
        transaction.on_commit(lambda: dispatch_vlm_units_safely(run_id))
    return created


def dispatch_vlm_units(run_id: int, stale_after: float | None = None) -> int:
    # Serialize dispatchers using the same run lock as claims/cancel. Publish a small window,
    # not one broker message for every candidate on every progress refresh.
    with transaction.atomic():
        run = QCRun.objects.select_for_update().get(pk=run_id)
        if run.cancel_requested_at:
            return 0
        if run.retry_engine and run.retry_engine != VLM_ENGINE:
            return 0
        qs = VlmUnit.objects.filter(run_id=run_id)
        if run.retry_engine == VLM_ENGINE:
            from django.db.models import Subquery

            latest = (
                VlmUnit.objects.filter(run_id=run_id, candidate_id=OuterRef("candidate_id"))
                .order_by("-evaluation_generation")
                .values("pk")[:1]
            )
            qs = qs.filter(pk=Subquery(latest), evaluation_generation__gt=1)
        if run.status not in (QCRun.Status.QUEUED, QCRun.Status.RUNNING):
            qs = qs.filter(evaluation_generation__gt=EVALUATION_GENERATION)
        budget = VlmBudget.objects.filter(run_id=run_id).first()
        if budget is not None and budget.used_calls >= budget.max_calls:
            qs.filter(status=VlmUnit.Status.PENDING).update(
                status=VlmUnit.Status.FAILED,
                reason_code="budget_exhausted",
                finished_at=timezone.now(),
                lease_token="",
            )
            return 0
        wait_limit = timedelta(seconds=getattr(settings, "VLM_STAGE_TIMEOUT_SECONDS", 1800))
        qs.filter(
            status=VlmUnit.Status.PENDING, deadline_at__isnull=True, evaluation_generation=1
        ).update(deadline_at=(budget.started_at if budget else timezone.now()) + wait_limit)
        qs.filter(
            status=VlmUnit.Status.PENDING, deadline_at__isnull=True, evaluation_generation__gt=1
        ).update(deadline_at=timezone.now() + wait_limit)
        _expire_waiting(run_id)
        window = max(1, int(getattr(settings, "VLM_DISPATCH_WINDOW", 1)))
        pending = qs.filter(status=VlmUnit.Status.PENDING)
        eligible = Q(dispatched_at__isnull=True)
        if stale_after is not None:
            cutoff = timezone.now() - timedelta(seconds=stale_after)
            eligible |= Q(dispatched_at__lte=cutoff)
        inflight = (
            qs.filter(status=VlmUnit.Status.RUNNING).count()
            + pending.filter(Q(retry_at__gt=timezone.now()) | ~eligible).count()
        )
        slots = max(0, window - inflight)
        if budget is not None:
            slots = min(slots, max(0, budget.max_calls - budget.used_calls - inflight))
        queued = 0
        due = Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now())
        for unit in pending.filter(eligible).filter(due).order_by("pk")[:slots]:
            previous = unit.dispatched_at
            VlmUnit.objects.filter(pk=unit.pk).update(dispatched_at=timezone.now())
            try:
                run_vlm_unit_task.delay(unit.pk)
            except Exception:
                VlmUnit.objects.filter(pk=unit.pk).update(dispatched_at=previous)
                logger.exception("vlm dispatch failed", extra={"vlm_unit_id": unit.pk})
                break
            queued += 1
        return queued


def dispatch_vlm_units_safely(run_id: int, stale_after: float | None = None) -> int:
    try:
        return dispatch_vlm_units(run_id, stale_after)
    except Exception:
        logger.exception("vlm dispatch failed", extra={"qc_run_id": run_id})
        return 0


def vlm_stage_started(run_id: int) -> bool:
    return VlmBudget.objects.filter(run_id=run_id).exists()


def vlm_units_open(run_id: int) -> bool:
    return VlmUnit.objects.filter(run_id=run_id, status__in=_OPEN_STATUSES).exists()


def _refresh_after_expiry(run_id: int) -> None:
    from orchestration.runsync import refresh_run

    refresh_run(run_id)


def _expire_waiting(run_id: int) -> None:
    """Bound provider outages, including candidates never claimed by a worker."""
    now = timezone.now()
    budget = VlmBudget.objects.filter(run_id=run_id).first()
    overdue = Q(deadline_at__lte=now)
    if (
        budget
        and budget.started_at
        + timedelta(seconds=getattr(settings, "VLM_STAGE_TIMEOUT_SECONDS", 1800))
        <= now
    ):
        overdue |= Q(evaluation_generation=1)
    VlmUnit.objects.filter(run_id=run_id, status=VlmUnit.Status.PENDING).filter(overdue).update(
        status=VlmUnit.Status.SKIPPED,
        reason_code="deadline_exceeded",
        finished_at=now,
        lease_token="",
        retry_at=None,
    )


class DbBudgetGate:
    """Cổng budget nguyên tử theo DB cho một lượt logic (một VlmUnit).

    Mỗi lần gọi `try_consume` là MỘT lần gửi thật: ghi VlmAttempt "đã gửi" (số thứ tự kế tiếp sau
    các attempt đã ghi của unit) rồi tăng budget, cùng một transaction, TRƯỚC khi gọi provider. Nếu
    worker chết sau khi gửi, lần nhận lại tiếp tục đánh số từ attempt kế tiếp và tính budget vì
    đó là lần gửi thật mới; tổng attempt của lượt không vượt max_attempts (xem `attempts_done`).
    Giao lại unit đã settle là no-op ở `_claim_unit`, nên không có lần gửi hay tính phí nào.
    """

    def __init__(self, unit: VlmUnit) -> None:
        self._token = unit.lease_token
        self._unit_id = unit.pk
        self._run_id = unit.run_id
        last = VlmAttempt.objects.filter(unit_id=unit.pk).aggregate(last=Max("attempt_no"))["last"]
        self.attempts_done: int = last or 0
        self._attempt_no = self.attempts_done

    def try_consume(self) -> bool:
        self._attempt_no += 1
        with transaction.atomic():
            run = QCRun.objects.select_for_update().get(pk=self._run_id)
            if (
                run.cancel_requested_at
                or not VlmUnit.objects.filter(
                    pk=self._unit_id,
                    lease_token=self._token,
                    status=VlmUnit.Status.RUNNING,
                ).exists()
            ):
                return False
            _, created = VlmAttempt.objects.get_or_create(
                unit_id=self._unit_id, attempt_no=self._attempt_no
            )
            if not created:
                # Worker khác vừa ghi đúng attempt này (đã tính budget ở đó): không tính hai lần.
                return False
            charged = VlmBudget.objects.filter(
                run_id=self._run_id, used_calls__lt=F("max_calls")
            ).update(used_calls=F("used_calls") + 1)
            if not charged:
                transaction.set_rollback(True)  # bỏ cả dòng attempt vừa tạo
                return False
            return True


def _stale_seconds() -> float:
    return float(getattr(settings, "ORCHESTRATION_RUNNING_STALE_SECONDS", 1800))


def _claim_unit(unit_id: int) -> tuple[VlmUnit | None, str, str]:
    """Nhận lease của VlmUnit; thứ tự khoá QCRun -> VlmUnit (cùng thứ tự với cancel/commit)."""
    run_id = VlmUnit.objects.filter(pk=unit_id).values_list("run_id", flat=True).first()
    if run_id is None:
        return None, "", "missing"
    with transaction.atomic():
        run = QCRun.objects.select_for_update().get(pk=run_id)
        stop_failed_engines(run)
        unit = VlmUnit.objects.select_for_update().get(pk=unit_id)
        if run.retry_engine and run.retry_engine != VLM_ENGINE:
            return None, "", unit.status
        run_active = run.status in (QCRun.Status.QUEUED, QCRun.Status.RUNNING)
        manual_after_end = not run_active and unit.evaluation_generation > EVALUATION_GENERATION
        if (
            run.cancel_requested_at
            or not (run_active or manual_after_end)
            or unit.status
            in (
                VlmUnit.Status.COMPLETED,
                VlmUnit.Status.FAILED,
                VlmUnit.Status.CANCELLED,
                VlmUnit.Status.SKIPPED,
            )
        ):
            return None, "", unit.status
        now = timezone.now()
        if unit.retry_at and unit.retry_at > now:
            return None, "", "waiting_retry"
        if unit.deadline_at is None:
            budget = VlmBudget.objects.filter(run_id=run_id).first()
            origin = budget.started_at if budget and unit.evaluation_generation == 1 else now
            unit.deadline_at = origin + timedelta(
                seconds=getattr(settings, "VLM_STAGE_TIMEOUT_SECONDS", 1800)
            )
        if now >= unit.deadline_at:
            unit.status = VlmUnit.Status.SKIPPED
            unit.reason_code = "deadline_exceeded"
            unit.finished_at = now
            unit.save(update_fields=["status", "reason_code", "finished_at", "deadline_at"])
            transaction.on_commit(lambda: _refresh_after_expiry(run_id))
            return None, "", unit.status
        if unit.status == VlmUnit.Status.RUNNING and unit.started_at is not None:
            if unit.started_at > now - timedelta(seconds=_stale_seconds()):
                return None, "", "running"  # delivery trùng: đã có owner đang chạy
        token = uuid.uuid4().hex
        unit.status = VlmUnit.Status.RUNNING
        unit.retry_at = None
        unit.started_at = now
        unit.lease_token = token
        unit.save(update_fields=["status", "started_at", "lease_token", "deadline_at", "retry_at"])
        return unit, token, VlmUnit.Status.RUNNING


def _settle_unit(
    unit: VlmUnit,
    token: str,
    result: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    revision: str = "",
    class_name: str = "",
    crop_origin: dict[str, Any] | None = None,
) -> bool:
    """Chốt unit và ghi evidence append-only trong cùng một transaction (chỉ chủ lease)."""
    ok = result["status"] in (VlmStatus.CHECKED.value, VlmStatus.UNCERTAIN.value)
    with transaction.atomic():
        QCRun.objects.select_for_update().only("id").get(pk=unit.run_id)
        updated = VlmUnit.objects.filter(
            pk=unit.pk, status=VlmUnit.Status.RUNNING, lease_token=token
        ).update(
            status=VlmUnit.Status.COMPLETED if ok else VlmUnit.Status.FAILED,
            reason_code=result.get("reason_code") or "",
            result=result,
            attempts=result["attempts"],
            finished_at=timezone.now(),
            retry_at=None,
            error_code=result.get("provider_failure") or result.get("reason_code") or "",
        )
        if not updated:
            return False
        VlmEvidence.objects.create(
            unit=unit,
            run_id=unit.run_id,
            candidate_id=unit.candidate_id,
            status=result["status"],
            label_class_id=result.get("label") or "",
            class_name=class_name,
            rationale=result.get("rationale") or "",
            reason_code=result.get("reason_code") or "",
            attempts=result["attempts"],
            provider=result.get("provider") or (config or {}).get("provider", ""),
            provider_host=result.get("provider_host") or (config or {}).get("host", ""),
            response_model=result.get("response_model") or "",
            model=unit.model,
            prompt_version=unit.prompt_version,
            policy_version=unit.policy_version,
            snapshot_revision=revision,
            crop_sha256=result.get("crop_sha256") or "",
            crop_origin=crop_origin,
            request_id=result.get("request_id") or "",
            config=config or {},
        )
        logger.info(
            "vlm unit finished",
            extra={
                "qc_run_id": unit.run_id,
                "vlm_unit_id": unit.pk,
                "vlm_status": result["status"],
                "reason_code": result.get("reason_code") or "",
                "attempts": result["attempts"],
            },
        )
        return True


def _fail(
    unit: VlmUnit,
    token: str,
    reason: VlmReasonCode,
    attempts: int = 0,
    *,
    revision: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "status": VlmStatus.FAILED.value,
        "label": None,
        "rationale": None,
        "reason_code": reason.value,
        "attempts": attempts,
        "request_id": None,
        "model": unit.model,
        "response_model": None,
        "provider": (config or {}).get("provider"),
        "provider_host": (config or {}).get("host"),
        "prompt_version": unit.prompt_version,
        "crop_sha256": None,
    }
    _settle_unit(unit, token, result, config=config, revision=revision)
    return result


def execute_vlm_unit(
    unit_id: int, *, client: VlmClient | None = None, deferred: bool = True
) -> str:
    """Chạy một VlmUnit; idempotent: unit đã xong/huỷ/đang có owner thì bỏ qua."""
    from orchestration.runsync import refresh_run

    unit, token, current = _claim_unit(unit_id)
    if unit is None:
        if current in (VlmUnit.Status.COMPLETED, VlmUnit.Status.FAILED):
            run_id = VlmUnit.objects.filter(pk=unit_id).values_list("run_id", flat=True)[0]
            refresh_run(run_id)  # worker chết sau settle nhưng trước refresh: chốt nốt
        return current
    run = QCRun.objects.select_related("config_version", "snapshot").get(pk=unit.run_id)
    candidate = CandidateRecord.objects.select_related("run").get(pk=unit.candidate_id)
    revision = run.snapshot.revision_sha256 or str(run.snapshot_id)
    raw = run_vlm_config(run)
    taxonomy = _taxonomy_for_run(run)
    if raw is None or taxonomy is None:
        _fail(unit, token, VlmReasonCode.PROVIDER_ERROR, revision=revision)
        refresh_run(unit.run_id)
        return VlmUnit.Status.FAILED
    config: VlmConfig = parse_vlm_config(raw)
    public = config.as_public_dict()
    if (config.model, config.prompt_version) != (unit.model, unit.prompt_version):
        # Config của run không còn khớp lúc unit được tạo: không gọi provider với model/prompt
        # khác với khoá idempotency và evidence.
        _fail(unit, token, VlmReasonCode.PROVIDER_ERROR, revision=revision, config=public)
        refresh_run(unit.run_id)
        return VlmUnit.Status.FAILED
    try:
        crop = crop_provider().load(candidate)
    except VlmError as exc:
        _fail(unit, token, exc.reason_code, revision=revision, config=public)
        refresh_run(unit.run_id)
        return VlmUnit.Status.FAILED
    except Exception:
        logger.exception("vlm crop load failed", extra={"vlm_unit_id": unit.pk})
        _fail(unit, token, VlmReasonCode.INVALID_CROP, revision=revision, config=public)
        refresh_run(unit.run_id)
        return VlmUnit.Status.FAILED
    request = VlmRequest(
        crop=crop,
        taxonomy=taxonomy,
        context=CandidateContext(
            candidate_id=candidate.dedup_key,
            snapshot_revision=revision,
            run_id=unit.run_id,
            unit_id=unit.pk,
        ),
        config=config,
    )
    gate = DbBudgetGate(unit)
    try:
        with EndpointLease("vlm:" + config.base_url, config.timeout_seconds + 60) as lease:
            try:
                result = result_to_dict(
                    run_vlm_unit(
                        request,
                        client or DashScopeClient(),
                        gate,
                        attempts_done=gate.attempts_done,
                        deferred=deferred,
                    )
                )
            except VlmDeferred as exc:
                lease.failed(
                    exc.error.failure.value,
                    retry_after=exc.error.retry_after,
                    uncertain=exc.error.failure.value in ("timeout", "network"),
                )
                raise
            failure = result.get("provider_failure")
            if failure in ("network", "server_error", "rate_limited", "timeout"):
                lease.failed(failure, uncertain=failure in ("timeout", "network"))
    except (ResourceWaiting, VlmDeferred) as exc:
        delay = (
            exc.seconds
            if isinstance(exc, ResourceWaiting)
            else max(backoff_seconds(exc.attempts), exc.error.retry_after)
        )
        delay = retry_delay(delay)
        reason = exc.code if isinstance(exc, ResourceWaiting) else exc.error.failure.value
        retry_at = timezone.now() + timedelta(seconds=delay)
        attempts = gate.attempts_done if isinstance(exc, ResourceWaiting) else exc.attempts
        updated = VlmUnit.objects.filter(
            pk=unit.pk, status=VlmUnit.Status.RUNNING, lease_token=token
        ).update(
            status=VlmUnit.Status.PENDING,
            lease_token="",
            dispatched_at=None,
            retry_at=retry_at,
            attempts=attempts,
            error_code=reason,
        )
        if updated:
            logger.info(
                "vlm retry scheduled",
                extra={
                    "qc_run_id": unit.run_id,
                    "vlm_unit_id": unit.pk,
                    "error_code": reason,
                    "attempts": attempts,
                    "retry_at": retry_at.isoformat(),
                },
            )
            if getattr(settings, "ORCHESTRATION_AUTO_DISPATCH", True):
                try:
                    run_vlm_unit_task.apply_async(args=(unit.pk,), countdown=delay)
                except Exception:
                    logger.exception("vlm retry publish failed", extra={"qc_run_id": unit.run_id})
        refresh_run(unit.run_id)
        return "waiting_retry"
    names = {t.class_id: t.class_name for t in taxonomy}
    _settle_unit(
        unit,
        token,
        result,
        config=public,
        revision=revision,
        class_name=names.get(result.get("label") or "", ""),
        crop_origin=crop.origin,
    )
    if unit.evaluation_generation == 1 and result.get("provider_failure") in ("auth", "quota"):
        # Never label candidates that were not sent as provider request failures.
        VlmUnit.objects.filter(
            run_id=unit.run_id,
            evaluation_generation=unit.evaluation_generation,
            status=VlmUnit.Status.PENDING,
        ).update(
            status=VlmUnit.Status.SKIPPED,
            reason_code="provider_unavailable",
            error_code=result["provider_failure"],
            finished_at=timezone.now(),
            lease_token="",
        )
    refresh_run(unit.run_id)
    unit.refresh_from_db(fields=["status"])
    return str(unit.status)


@shared_task(name="orchestration.run_vlm_unit", acks_late=True, reject_on_worker_lost=True)
def run_vlm_unit_task(unit_id: int) -> str:
    return execute_vlm_unit(unit_id)
