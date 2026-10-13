"""M04A-02: client DashScope (MockTransport), runner retry/budget, payload task. Không mạng."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest

from tests.vlm.test_contract import PNG, TAXONOMY, VALID
from vlm.client import DashScopeClient, classify_http_error, redact_request_id
from vlm.config import parse_vlm_config
from vlm.contract import CandidateContext, CropInput, VlmRequest, VlmStatus
from vlm.errors import VlmProviderError, VlmProviderFailure, VlmReasonCode
from vlm.runner import CounterBudget, run_vlm_unit
from vlm.tasks import evaluate_payload

SECRET = "sk-test-SECRET-value"


def _req(**cfg: Any) -> VlmRequest:
    return VlmRequest(
        crop=CropInput(PNG, "image/png"),
        taxonomy=TAXONOMY,
        context=CandidateContext("c1", "r1", "car"),
        config=parse_vlm_config({**VALID, **cfg}),
    )


def _ok(label: str = "bus") -> httpx.Response:
    body = {
        "id": "chatcmpl-abc",
        "choices": [{"message": {"content": json.dumps({"label": label})}}],
    }
    return httpx.Response(200, json=body, headers={"x-request-id": "req-123"})


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DASHSCOPE_API_KEY", SECRET)


def _client(handler: Any) -> DashScopeClient:
    return DashScopeClient(transport=httpx.MockTransport(handler))


def test_success_builds_openai_request_and_redacts() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return _ok()

    result = run_vlm_unit(_req(), _client(handler), CounterBudget(5), sleep=lambda s: None)
    assert result.status is VlmStatus.CHECKED and result.label == "bus"
    assert result.attempts == 1 and result.request_id == "req-123"
    assert seen["url"].endswith("/compatible-mode/v1/chat/completions")
    body = seen["body"]
    assert body["model"] == "qwen3-vl-plus" and "response_format" not in body
    content = body["messages"][0]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "car: Car" in content[1]["text"]
    assert SECRET not in json.dumps(body) and SECRET not in repr(result)


def test_uncertain_label() -> None:
    result = run_vlm_unit(_req(), _client(lambda r: _ok("uncertain")), CounterBudget(5))
    assert result.status is VlmStatus.UNCERTAIN and result.label is None


def test_parse_failure_not_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        body = {"choices": [{"message": {"content": "xin chào"}}]}
        return httpx.Response(200, json=body)

    result = run_vlm_unit(_req(), _client(handler), CounterBudget(5))
    assert result.status is VlmStatus.FAILED and result.reason_code is VlmReasonCode.PARSE_FAILURE
    assert len(calls) == 1 and result.attempts == 1


def test_label_outside_taxonomy_is_parse_failure() -> None:
    result = run_vlm_unit(_req(), _client(lambda r: _ok("truck")), CounterBudget(5))
    assert result.reason_code is VlmReasonCode.PARSE_FAILURE


def test_retry_on_server_error_then_success_counts_every_attempt() -> None:
    responses = iter([httpx.Response(503), httpx.Response(429), _ok()])
    sleeps: list[float] = []
    budget = CounterBudget(10)
    result = run_vlm_unit(_req(), _client(lambda r: next(responses)), budget, sleep=sleeps.append)
    assert result.status is VlmStatus.CHECKED and result.attempts == 3
    assert budget.used == 3 and sleeps == [2.0, 4.0]


def test_max_attempts_exhausted_is_provider_error() -> None:
    budget = CounterBudget(10)
    result = run_vlm_unit(
        _req(max_attempts=2), _client(lambda r: httpx.Response(500)), budget, sleep=lambda s: None
    )
    assert result.reason_code is VlmReasonCode.PROVIDER_ERROR
    assert result.attempts == 2 and budget.used == 2


def test_quota_and_auth_not_retried() -> None:
    quota = httpx.Response(429, json={"error": {"code": "insufficient_quota", "message": "x"}})
    for resp in (quota, httpx.Response(401), httpx.Response(400)):
        budget = CounterBudget(10)
        result = run_vlm_unit(_req(), _client(lambda r, resp=resp: resp), budget)
        assert result.status is VlmStatus.FAILED and result.attempts == 1 and budget.used == 1


def test_classification_table() -> None:
    quota = httpx.Response(429, json={"error": {"code": "Arrearage"}})
    assert classify_http_error(quota).failure is VlmProviderFailure.QUOTA
    assert classify_http_error(httpx.Response(429)).failure is VlmProviderFailure.RATE_LIMITED
    assert classify_http_error(httpx.Response(504)).failure is VlmProviderFailure.TIMEOUT
    assert classify_http_error(httpx.Response(402)).failure is VlmProviderFailure.QUOTA
    assert classify_http_error(httpx.Response(403)).failure is VlmProviderFailure.AUTH
    assert classify_http_error(httpx.Response(422)).failure is VlmProviderFailure.BAD_REQUEST


def test_timeout_and_network_errors_map_without_raw_exception() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("boom", request=request)

    def network(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(VlmProviderError) as exc:
        _client(timeout).complete(_req())
    assert exc.value.failure is VlmProviderFailure.TIMEOUT
    with pytest.raises(VlmProviderError) as exc2:
        _client(network).complete(_req())
    assert exc2.value.failure is VlmProviderFailure.NETWORK
    result = run_vlm_unit(_req(max_attempts=1), _client(timeout), CounterBudget(3))
    assert result.reason_code is VlmReasonCode.PROVIDER_ERROR


def test_budget_exhausted_blocks_provider_call() -> None:
    calls = []
    result = run_vlm_unit(_req(), _client(lambda r: calls.append(1) or _ok()), CounterBudget(0))
    assert result.status is VlmStatus.FAILED
    assert result.reason_code is VlmReasonCode.BUDGET_EXHAUSTED and not calls


def test_budget_runs_out_mid_retry() -> None:
    result = run_vlm_unit(
        _req(), _client(lambda r: httpx.Response(500)), CounterBudget(1), sleep=lambda s: None
    )
    assert result.reason_code is VlmReasonCode.BUDGET_EXHAUSTED and result.attempts == 1


def test_invalid_crop_never_calls_provider() -> None:
    calls = []
    bad = VlmRequest(
        crop=CropInput(b"nope", "image/png"),
        taxonomy=TAXONOMY,
        context=CandidateContext("c1", "r1"),
        config=parse_vlm_config(VALID),
    )
    result = run_vlm_unit(bad, _client(lambda r: calls.append(1) or _ok()), CounterBudget(3))
    assert result.reason_code is VlmReasonCode.INVALID_CROP and not calls and result.attempts == 0


def test_missing_api_key_is_auth_failure_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    calls = []
    result = run_vlm_unit(_req(), _client(lambda r: calls.append(1) or _ok()), CounterBudget(3))
    assert result.reason_code is VlmReasonCode.PROVIDER_ERROR and not calls


def test_unexpected_exception_is_contained() -> None:
    class Boom:
        def complete(self, request: VlmRequest) -> tuple[str, str | None]:
            raise RuntimeError(f"internal {SECRET}")

    result = run_vlm_unit(_req(), Boom(), CounterBudget(3))
    assert result.reason_code is VlmReasonCode.PROVIDER_ERROR
    assert SECRET not in repr(result)


def test_malformed_200_body_is_server_error() -> None:
    result = run_vlm_unit(
        _req(max_attempts=1),
        _client(lambda r: httpx.Response(200, text="<html>")),
        CounterBudget(3),
    )
    assert result.reason_code is VlmReasonCode.PROVIDER_ERROR


def test_redact_request_id() -> None:
    assert redact_request_id("req 123/\n$$") == "req123"[:0] + "req123"
    assert redact_request_id("x" * 200) == "x" * 64
    assert redact_request_id(None) is None and redact_request_id("") is None


def _payload(**over: Any) -> dict[str, Any]:
    base = {
        "config": VALID,
        "crop_b64": base64.b64encode(PNG).decode(),
        "mime_type": "image/png",
        "taxonomy": [{"class_id": "car", "class_name": "Car"}],
        "context": {"candidate_id": "c1", "snapshot_revision": "r1"},
    }
    base.update(over)
    return base


def test_task_payload_success_and_public_shape() -> None:
    out = evaluate_payload(_payload(), client=_client(lambda r: _ok("car")))
    assert out["status"] == "checked" and out["label"] == "car"
    assert "crop_b64" not in json.dumps(out) and SECRET not in json.dumps(out)


@pytest.mark.parametrize(
    "over",
    [
        {"crop_b64": "!!!"},
        {"taxonomy": [{"class_id": "car"}]},
        {"context": {}},
        {"config": {**VALID, "model": "x"}},
        {"mime_type": "image/gif"},
    ],
)
def test_task_bad_payload_is_failed_with_reason_not_exception(over: dict[str, Any]) -> None:
    out = evaluate_payload(_payload(**over), client=_client(lambda r: _ok()))
    assert out["status"] == "failed" and out["reason_code"] in {
        "invalid_crop",
        "provider_error",
    }


def test_task_missing_key_in_payload() -> None:
    payload = _payload()
    del payload["config"]
    assert evaluate_payload(payload)["status"] == "failed"
