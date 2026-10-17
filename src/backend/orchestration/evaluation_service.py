"""Evaluation: nối detector Faster R-CNN với policy/VLM (M04C-02, CR-117).

- `route_candidates(run)`: quyết định định tuyến trực tiếp từ evidence của candidate detector.
- `create_auto_evaluations(run, ...)`: lượt logic đầu (generation 1) do stage VLM tạo.
- `create_manual_evaluation(...)`: re-evaluate theo yêu cầu, luôn là generation mới.

Ranh giới: output AI chỉ là đề xuất; không tạo ReviewDecision/Adjudication. `note` của người dùng
chỉ để audit, không bao giờ vào prompt. Guard idempotency/revision ở `evaluation_guard`.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Max

from audit.services import append_audit_event
from orchestration.evaluation_guard import (
    EvaluationGuardError,
    EvaluationKeyReusedError,
    EvaluationRequest,
    IdempotencyOutcome,
    check_revision,
    resolve_idempotency,
    validate_idempotency_key,
)
from orchestration.models import (
    CandidateRecord,
    Evaluation,
    VlmBudget,
    VlmUnit,
)
from orchestration.routing_policy import (
    POLICY_NAME,
    RoutingDecision,
    RoutingPolicy,
    route,
    routing_input_from_candidate,
)
from orchestration.vlm_stage import (
    EVALUATION_GENERATION,
    _taxonomy_for_run,
    compute_vlm_idempotency_key,
    crop_provider,
    dispatch_vlm_units_safely,
    run_vlm_config,
)
from runs.models import QCRun
from vlm.config import parse_vlm_config

THRESHOLDS_KEY = "classification_routing"


class EvaluationNotAllowedError(EvaluationGuardError):
    """Run/candidate không cho phép đánh giá (huỷ, VLM tắt, không có taxonomy)."""


def run_revision(run: QCRun) -> str:
    """Revision hiện tại của snapshot, cùng định nghĩa với evidence VLM của A."""
    return run.snapshot.revision_sha256 or str(run.snapshot_id)


def policy_for_run(run: QCRun) -> RoutingPolicy:
    cfg = run.config_version
    thresholds = cfg.thresholds or (cfg.payload or {}).get("thresholds", {})
    raw = thresholds.get(THRESHOLDS_KEY) if isinstance(thresholds, dict) else None
    return RoutingPolicy.from_config(raw)


def candidate_payload(candidate: CandidateRecord) -> dict[str, Any]:
    """Phần CandidateRecord mà adapter routing cần; không tạo model trung gian."""
    return {
        "engine": candidate.engine,
        "evidence": candidate.evidence,
    }


def budget_exhausted(run_id: int, config_budget: int | None = None) -> bool:
    """Hết budget VLM của run; chưa có dòng budget thì dùng budget trong config."""
    budget = VlmBudget.objects.filter(run_id=run_id).first()
    if budget is not None:
        return budget.used_calls >= budget.max_calls
    return config_budget is not None and config_budget <= 0


def _decide(
    policy: RoutingPolicy,
    candidate: CandidateRecord,
    *,
    manual_recheck: bool,
    exhausted: bool,
) -> RoutingDecision:
    data = routing_input_from_candidate(
        candidate_payload(candidate), manual_recheck=manual_recheck, budget_exhausted=exhausted
    )
    return route(policy, data)


def route_candidates(
    run: QCRun, candidates: list[CandidateRecord], *, exhausted: bool
) -> list[tuple[CandidateRecord, RoutingDecision]]:
    """Định tuyến tự động (không manual) trực tiếp từ evidence detector đã persist."""
    policy = policy_for_run(run)
    return [(c, _decide(policy, c, manual_recheck=False, exhausted=exhausted)) for c in candidates]


def _vlm_unit_for(
    candidate: CandidateRecord, run: QCRun, config: Any, generation: int, *, provider: Any = None
) -> VlmUnit:
    identity = (provider or crop_provider()).identity(candidate)
    return VlmUnit(
        run_id=run.pk,
        candidate=candidate,
        evaluation_generation=generation,
        policy_version=POLICY_NAME,
        model=config.model,
        prompt_version=config.prompt_version,
        crop_identity=identity,
        idempotency_key=compute_vlm_idempotency_key(
            evaluation_generation=generation,
            candidate_dedup_key=candidate.dedup_key,
            crop_identity=identity,
            snapshot_revision=run_revision(run),
            policy_version=POLICY_NAME,
            model=config.model,
            prompt_version=config.prompt_version,
        ),
    )


def _evaluation_fields(decision: RoutingDecision, revision: str) -> dict[str, Any]:
    return {
        "snapshot_revision": revision,
        "primary_reason": decision.primary.value,
        "reasons": [r.value for r in decision.reasons],
        "call_qwen": decision.call_qwen,
        "human_review_required": decision.human_review_required,
        "policy": dict(decision.policy),
        "checkpoint_status": decision.checkpoint_status,
    }


def create_auto_evaluations(
    run: QCRun,
    routed: list[tuple[CandidateRecord, RoutingDecision]],
    config: Any,
    *,
    selected_ids: set[int],
) -> int:
    """Tạo Evaluation generation 1 (và VlmUnit nếu cần Qwen); idempotent theo (candidate, gen).

    Gọi trong transaction đã khoá QCRun (refresh_run). Trả số VlmUnit mới tạo.
    """
    revision = run_revision(run)
    done = set(
        Evaluation.objects.filter(
            run_id=run.pk,
            generation=EVALUATION_GENERATION,
            candidate_id__in=[c.pk for c, _ in routed],
        ).values_list("candidate_id", flat=True)
    )
    provider = crop_provider()
    prepare = getattr(provider, "prepare", None)
    selected = [
        c
        for c, decision in routed
        if c.pk not in done and decision.call_qwen and c.pk in selected_ids
    ]
    if prepare is not None:
        prepare(selected)
    existing = {
        unit.candidate_id: unit
        for unit in VlmUnit.objects.filter(
            run_id=run.pk,
            evaluation_generation=EVALUATION_GENERATION,
            candidate_id__in=[c.pk for c in selected],
        )
    }
    units = [
        _vlm_unit_for(c, run, config, EVALUATION_GENERATION, provider=provider)
        for c in selected
        if c.pk not in existing
    ]
    VlmUnit.objects.bulk_create(units, batch_size=500)
    existing.update({unit.candidate_id: unit for unit in units})
    evaluations = []
    for candidate, decision in routed:
        if candidate.pk in done:
            continue
        evaluations.append(
            Evaluation(
                run_id=run.pk,
                candidate=candidate,
                generation=EVALUATION_GENERATION,
                source=Evaluation.Source.AUTO,
                vlm_unit=existing.get(candidate.pk),
                **_evaluation_fields(decision, revision),
            )
        )
    Evaluation.objects.bulk_create(evaluations, batch_size=500)
    return len(units)


def _get_or_create_unit(unit: VlmUnit) -> tuple[VlmUnit, bool]:
    existing = VlmUnit.objects.filter(
        run_id=unit.run_id,
        candidate_id=unit.candidate_id,
        evaluation_generation=unit.evaluation_generation,
    ).first()
    if existing is not None:
        return existing, False
    unit.save()
    return unit, True


def create_manual_evaluation(
    *,
    candidate_id: int,
    actor: User,
    request: EvaluationRequest,
    idempotency_key: str | None,
) -> tuple[Evaluation, bool]:
    """Re-evaluate: trả (evaluation, created). Replay cùng key + payload + người → created=False.

    Thứ tự kiểm: key hợp lệ → replay → run cho phép → revision còn mới → route → ghi. Stale
    revision và key reuse khác payload đều 409 và không ghi gì. Evidence/decision cũ không bị đụng:
    luôn là generation mới (A giữ khoá unique (run, candidate, generation)).
    """
    key = validate_idempotency_key(idempotency_key)
    digest = request.digest()
    try:
        with transaction.atomic():
            candidate = (
                CandidateRecord.objects.select_for_update(of=("self",))
                .select_related("run__snapshot", "run__config_version")
                .get(pk=candidate_id)
            )
            run = candidate.run
            existing = Evaluation.objects.filter(idempotency_key=key).first()
            outcome = resolve_idempotency(
                existing_digest=existing.request_sha256 if existing else None,
                existing_actor_id=existing.requested_by_id if existing else None,
                request_digest=digest,
                actor_id=actor.pk,
            )
            if outcome is IdempotencyOutcome.REPLAY and existing is not None:
                return existing, False
            if run.cancel_requested_at:
                raise EvaluationNotAllowedError("Run đã bị huỷ; không thể đánh giá lại.")
            raw = run_vlm_config(run)
            if raw is None or _taxonomy_for_run(run) is None:
                raise EvaluationNotAllowedError(
                    "Run không bật VLM hoặc thiếu cấu hình/taxonomy; không thể đánh giá lại."
                )
            revision = run_revision(run)
            check_revision(expected_revision=request.expected_revision, current_revision=revision)
            config = parse_vlm_config(raw)
            if not VlmBudget.objects.filter(run_id=run.pk).exists():
                VlmBudget.objects.create(run_id=run.pk, max_calls=config.budget.max_calls)
            decision = _decide(
                policy_for_run(run),
                candidate,
                manual_recheck=True,
                exhausted=budget_exhausted(run.pk, config.budget.max_calls),
            )
            last = Evaluation.objects.filter(candidate=candidate).aggregate(m=Max("generation"))
            generation = (last["m"] or 0) + 1
            unit: VlmUnit | None = None
            if decision.call_qwen:
                unit = _vlm_unit_for(candidate, run, config, generation)
                unit.save()
            evaluation = Evaluation.objects.create(
                run_id=run.pk,
                candidate=candidate,
                generation=generation,
                source=Evaluation.Source.MANUAL,
                idempotency_key=key,
                request_sha256=digest,
                requested_by=actor,
                note=request.reason,
                expected_revision=request.expected_revision,
                vlm_unit=unit,
                **_evaluation_fields(decision, revision),
            )
            append_audit_event(
                actor=actor,
                action="evaluation.create",
                object_type="evaluation",
                object_id=evaluation.pk,
                before=None,
                after={
                    "candidate_id": candidate.pk,
                    "generation": generation,
                    "primary_reason": evaluation.primary_reason,
                    "call_qwen": evaluation.call_qwen,
                },
                revision=revision,
            )
            if unit is not None:
                run_id = run.pk
                transaction.on_commit(lambda: dispatch_vlm_units_safely(run_id))
            return evaluation, True
    except IntegrityError:
        # Hai yêu cầu cùng key đua nhau: đọc lại và áp dụng đúng luật replay/409.
        existing = Evaluation.objects.filter(idempotency_key=key).first()
        if existing is None:
            raise
        outcome = resolve_idempotency(
            existing_digest=existing.request_sha256,
            existing_actor_id=existing.requested_by_id,
            request_digest=digest,
            actor_id=actor.pk,
        )
        if outcome is IdempotencyOutcome.REPLAY:
            return existing, False
        raise EvaluationKeyReusedError("Idempotency-Key đã được dùng với yêu cầu khác.") from None
