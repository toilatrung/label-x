"""M04C-02: guard idempotency/revision và serializer request (không DB)."""

from __future__ import annotations

import pytest

from orchestration.evaluation_guard import (
    EvaluationKeyReusedError,
    EvaluationRequest,
    IdempotencyOutcome,
    InvalidIdempotencyKeyError,
    StaleRevisionError,
    check_revision,
    resolve_idempotency,
    validate_idempotency_key,
)
from orchestration.evaluation_serializers import EvaluationCreateSerializer

REQ = EvaluationRequest(candidate_id=7, reason="nghi ngờ nhãn", expected_revision="abc")


def test_stale_revision_raises_and_equal_passes():
    check_revision(expected_revision="abc", current_revision="abc")
    with pytest.raises(StaleRevisionError):
        check_revision(expected_revision="abc", current_revision="abd")


def test_new_key_creates():
    out = resolve_idempotency(
        existing_digest=None, existing_actor_id=None, request_digest=REQ.digest(), actor_id=1
    )
    assert out is IdempotencyOutcome.CREATE


def test_same_key_same_payload_same_actor_replays():
    out = resolve_idempotency(
        existing_digest=REQ.digest(),
        existing_actor_id=1,
        request_digest=REQ.digest(),
        actor_id=1,
    )
    assert out is IdempotencyOutcome.REPLAY


@pytest.mark.parametrize(
    "other",
    [
        EvaluationRequest(7, "khác", "abc"),
        EvaluationRequest(7, "nghi ngờ nhãn", "xyz"),
        EvaluationRequest(8, "nghi ngờ nhãn", "abc"),
    ],
)
def test_same_key_different_payload_conflicts(other):
    with pytest.raises(EvaluationKeyReusedError):
        resolve_idempotency(
            existing_digest=REQ.digest(),
            existing_actor_id=1,
            request_digest=other.digest(),
            actor_id=1,
        )


def test_same_key_different_actor_conflicts():
    with pytest.raises(EvaluationKeyReusedError):
        resolve_idempotency(
            existing_digest=REQ.digest(),
            existing_actor_id=1,
            request_digest=REQ.digest(),
            actor_id=2,
        )


def test_digest_is_stable():
    assert REQ.digest() == EvaluationRequest(7, "nghi ngờ nhãn", "abc").digest()


@pytest.mark.parametrize("key", [None, "", "   ", "x" * 129])
def test_invalid_key(key):
    with pytest.raises(InvalidIdempotencyKeyError):
        validate_idempotency_key(key)


def test_valid_key_is_trimmed():
    assert validate_idempotency_key("  k-1 ") == "k-1"


def test_serializer_accepts_reason_and_revision_only():
    s = EvaluationCreateSerializer(data={"reason": " x ", "expected_revision": "abc"})
    assert s.is_valid(), s.errors
    assert s.validated_data == {"reason": "x", "expected_revision": "abc"}


@pytest.mark.parametrize("extra", ["prompt", "model_id", "api_key", "image"])
def test_serializer_rejects_forbidden_fields(extra):
    s = EvaluationCreateSerializer(data={"reason": "x", "expected_revision": "abc", extra: "y"})
    assert not s.is_valid()
    assert extra in s.errors


@pytest.mark.parametrize(
    "data",
    [{}, {"reason": "x"}, {"expected_revision": "a"}, {"reason": "", "expected_revision": "a"}],
)
def test_serializer_requires_fields(data):
    assert not EvaluationCreateSerializer(data=data).is_valid()
