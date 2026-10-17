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
        "model": "qwen3-vl-plus-gw",
        "choices": [{"message": {"content": json.dumps({"label": label})}}],
    }
    return httpx.Response(200, json=body, headers={"x-request-id": "req-123"})


@pytest.fixture(autouse=True)
def _key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VLM_API_KEY", SECRET)
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
    assert result.attempts == 1 and result.request_id == "…req-123"
    assert seen["url"].endswith("/compatible-mode/v1/chat/completions")
    body = seen["body"]
    assert body["model"] == "qwen3-vl-plus" and "response_format" not in body
    content = body["messages"][0]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "car: Car" in content[1]["text"]
    assert SECRET not in json.dumps(body) and SECRET not in repr(result)


@pytest.mark.parametrize(
    ("model", "effort"),
    [("gemini-3.8-flash", "low"), ("gemini-2.5-flash", "none"), ("gemini-2.5-pro", "low")],
)
@pytest.mark.parametrize("gateway", [False, True])
def test_gemini_request_uses_selected_model_key_image_and_records_provenance(
    monkeypatch: pytest.MonkeyPatch, model: str, effort: str, gateway: bool
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "google-only-secret")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": model,
                "choices": [{"message": {"content": '{"label":"bus","rationale":"Bus"}'}}],
            },
        )

    result = run_vlm_unit(
        _req(
            provider="openai_compatible" if gateway else "gemini",
            model=model,
            base_url=(
                "https://api.shopaikey.com/v1"
                if gateway
                else "https://generativelanguage.googleapis.com/v1beta/openai"
            ),
        ),
        _client(handler),
        CounterBudget(2),
    )
    assert result.status is VlmStatus.CHECKED and result.label == "bus"
    assert result.model == result.response_model == model
    assert result.provider == ("openai_compatible" if gateway else "gemini")
    assert result.provider_host == (
        "api.shopaikey.com" if gateway else "generativelanguage.googleapis.com"
    )
    (sent,) = seen
    expected_base = (
        "https://api.shopaikey.com/v1"
        if gateway
        else "https://generativelanguage.googleapis.com/v1beta/openai"
    )
    assert str(sent.url) == expected_base + "/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {SECRET if gateway else 'google-only-secret'}"
    body = json.loads(sent.content)
    assert body["model"] == model and body["reasoning_effort"] == effort
    assert body["max_tokens"] >= 2048 and "temperature" not in body
    image = body["messages"][0]["content"][0]["image_url"]["url"]
    assert base64.b64decode(image.split(",", 1)[1]) == PNG
    assert "google-only-secret" not in repr(result) and SECRET not in repr(result)


def test_gemini_missing_key_does_not_fall_back_to_gateway_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    seen: list[httpx.Request] = []
    result = run_vlm_unit(
        _req(
            provider="gemini",
            model="gemini-3.8-flash",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        ),
        _client(lambda request: seen.append(request) or _ok()),
        CounterBudget(2),
    )
    assert result.status is VlmStatus.FAILED and result.attempts == 0
    assert seen == []


def test_google_error_status_is_sanitized_without_echoing_message() -> None:
    error = classify_http_error(
        httpx.Response(
            429,
            json={
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "Private credential and crop details must never be echoed",
                }
            },
        )
    )
    assert error.failure is VlmProviderFailure.RATE_LIMITED and error.retryable
    assert "resource_exhausted" in str(error) and "Private" not in str(error)


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


@pytest.mark.parametrize("status", [503, 429, 504])
@pytest.mark.parametrize("recover", [True, False])
def test_three_retries_use_four_calls_with_exponential_backoff(status, recover) -> None:
    responses = iter([httpx.Response(status)] * 3 + [_ok() if recover else httpx.Response(status)])
    sleeps: list[float] = []
    budget = CounterBudget(10)
    result = run_vlm_unit(
        _req(max_attempts=4),
        _client(lambda r: next(responses)),
        budget,
        sleep=sleeps.append,
    )
    assert result.status is (VlmStatus.CHECKED if recover else VlmStatus.FAILED)
    assert result.attempts == 4 and budget.used == 4
    assert sleeps == [2.0, 4.0, 8.0]


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
    monkeypatch.delenv("VLM_API_KEY")
    monkeypatch.delenv("DASHSCOPE_API_KEY")
    calls = []
    result = run_vlm_unit(_req(), _client(lambda r: calls.append(1) or _ok()), CounterBudget(3))
    assert result.reason_code is VlmReasonCode.PROVIDER_ERROR and not calls


def test_unexpected_exception_is_contained() -> None:
    class Boom:
        def preflight(self, request: VlmRequest) -> None:
            return None

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
    assert redact_request_id("req 123/\n$$") == "…req123"
    assert redact_request_id("prefix-123456789") == "…23456789"
    assert redact_request_id("…23456789") == "…23456789"  # idempotent
    assert redact_request_id("x" * 200 + "last-123") == "…last-123"
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


def test_client_never_reads_env_outside_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    import dataclasses

    monkeypatch.setenv("DJANGO_SECRET_KEY", "super-secret-django")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return _ok()

    req = _req()
    evil = dataclasses.replace(
        req, config=dataclasses.replace(req.config, api_key_env="DJANGO_SECRET_KEY")
    )
    client = _client(handler)
    with pytest.raises(VlmProviderError):
        client.preflight(evil)
    with pytest.raises(VlmProviderError):
        client.complete(evil)
    assert seen == []


def test_preflight_failure_is_provider_error_without_calling_budget() -> None:
    class NoKey:
        def preflight(self, request: VlmRequest) -> None:
            raise VlmProviderError(VlmProviderFailure.AUTH)

        def complete(self, request: VlmRequest) -> tuple[str, str | None]:
            raise AssertionError("không được gửi")

    budget = CounterBudget(3)
    result = run_vlm_unit(_req(), NoKey(), budget)
    assert result.reason_code is VlmReasonCode.PROVIDER_ERROR and budget.used == 0
    assert result.attempts == 0


def test_attempts_done_caps_total_attempts() -> None:
    calls = []
    budget = CounterBudget(10)
    result = run_vlm_unit(
        _req(max_attempts=2),
        _client(lambda r: calls.append(1) or httpx.Response(500)),
        budget,
        sleep=lambda s: None,
        attempts_done=1,
    )
    assert len(calls) == 1 and result.attempts == 2
    done = run_vlm_unit(_req(max_attempts=2), _client(lambda r: _ok()), budget, attempts_done=2)
    assert done.status is VlmStatus.FAILED and budget.used == 1


SHOPAI = {
    **VALID,
    "provider": "openai_compatible",
    "base_url": "https://api.shopaikey.com/v1",
}


def test_openai_compatible_gateway_provenance_and_request_shape() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["follow"] = request.extensions
        return _ok()

    req = VlmRequest(
        crop=CropInput(PNG, "image/png"),
        taxonomy=TAXONOMY,
        context=CandidateContext("c1", "r1"),
        config=parse_vlm_config(SHOPAI),
    )
    result = run_vlm_unit(req, _client(handler), CounterBudget(3))
    assert seen["url"] == "https://api.shopaikey.com/v1/chat/completions"
    assert result.provider == "openai_compatible" and result.provider_host == "api.shopaikey.com"
    assert result.response_model == "qwen3-vl-plus-gw" and result.model == "qwen3-vl-plus"
    assert SECRET not in repr(result)


def test_default_key_env_follows_host(monkeypatch: pytest.MonkeyPatch) -> None:
    assert parse_vlm_config(SHOPAI).api_key_env == "VLM_API_KEY"
    assert parse_vlm_config(VALID).api_key_env == "DASHSCOPE_API_KEY"
    monkeypatch.delenv("VLM_API_KEY")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dash-key")
    requests: list[httpx.Request] = []
    req = VlmRequest(
        CropInput(PNG, "image/png"), TAXONOMY, CandidateContext("c", "r"), parse_vlm_config(SHOPAI)
    )
    result = run_vlm_unit(req, _client(lambda r: requests.append(r) or _ok()), CounterBudget(2))
    assert result.status is VlmStatus.FAILED and requests == []  # cổng chỉ dùng VLM_API_KEY


def test_client_refuses_key_to_wrong_host_both_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dataclasses

    monkeypatch.setenv("VLM_API_KEY", "gw-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dash-key")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["authorization"])
        return _ok()

    client = _client(handler)
    gw = parse_vlm_config(SHOPAI)
    dash = parse_vlm_config(VALID)
    gemini = parse_vlm_config(
        {
            **VALID,
            "provider": "gemini",
            "model": "gemini-3.8-flash",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        }
    )
    crop = CropInput(PNG, "image/png")
    ctx = CandidateContext("c", "r")
    cases = [
        dataclasses.replace(gw, api_key_env="DASHSCOPE_API_KEY"),  # key DashScope → cổng
        dataclasses.replace(dash, api_key_env="VLM_API_KEY"),  # key cổng → DashScope
        dataclasses.replace(gw, provider="dashscope"),  # provider không khớp host
        dataclasses.replace(dash, provider="openai_compatible"),
        dataclasses.replace(gemini, api_key_env="VLM_API_KEY"),
        dataclasses.replace(gemini, api_key_env="DASHSCOPE_API_KEY"),
        dataclasses.replace(gw, api_key_env="GEMINI_API_KEY"),
        dataclasses.replace(gemini, model="qwen3-vl-plus"),
        dataclasses.replace(dash, model="gemini-3.8-flash"),
    ]
    for bad in cases:
        request = VlmRequest(crop, TAXONOMY, ctx, bad)
        with pytest.raises(VlmProviderError):
            client.preflight(request)
        with pytest.raises(VlmProviderError):
            client.complete(request)
    assert seen == []
    ok = run_vlm_unit(VlmRequest(crop, TAXONOMY, ctx, gw), client, CounterBudget(2))
    assert ok.status is VlmStatus.CHECKED and seen == ["Bearer gw-key"]
    seen.clear()
    ok2 = run_vlm_unit(VlmRequest(crop, TAXONOMY, ctx, dash), client, CounterBudget(2))
    assert ok2.status is VlmStatus.CHECKED and seen == ["Bearer dash-key"]


def test_redirects_are_not_followed() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "evil.example.com":
            return _ok()  # nếu bị theo, kết quả sẽ thành checked
        return httpx.Response(302, headers={"location": "https://evil.example.com/x"})

    result = run_vlm_unit(_req(max_attempts=1), _client(handler), CounterBudget(2))
    assert result.status is VlmStatus.FAILED
    assert result.reason_code is VlmReasonCode.PROVIDER_ERROR
    assert all("evil.example.com" not in u for u in seen) and len(seen) == 1


@pytest.mark.parametrize(
    ("host", "good_env", "bad_env", "provider"),
    [
        ("dashscope.aliyuncs.com", "DASHSCOPE_API_KEY", "VLM_API_KEY", "dashscope"),
        ("dashscope-intl.aliyuncs.com", "DASHSCOPE_API_KEY", "VLM_API_KEY", "dashscope"),
        ("dashscope-us.aliyuncs.com", "DASHSCOPE_API_KEY", "VLM_API_KEY", "dashscope"),
        ("api.shopaikey.com", "VLM_API_KEY", "DASHSCOPE_API_KEY", "openai_compatible"),
    ],
)
def test_env_binding_for_every_host(host: str, good_env: str, bad_env: str, provider: str) -> None:
    from vlm.config import validate_vlm_config

    path = "/v1" if host == "api.shopaikey.com" else "/compatible-mode/v1"
    base = {**VALID, "provider": provider, "base_url": f"https://{host}{path}"}
    assert validate_vlm_config({**base, "api_key_env": good_env}) == []
    assert parse_vlm_config(base).api_key_env == good_env  # mặc định theo host
    errors = validate_vlm_config({**base, "api_key_env": bad_env})
    assert errors and "api_key_env" in errors[0]


def test_wrong_provider_for_host_reports_provider_not_env() -> None:
    from vlm.config import validate_vlm_config

    errors = validate_vlm_config(
        {
            **VALID,
            "provider": "dashscope",
            "base_url": "https://api.shopaikey.com/v1",
            "api_key_env": "VLM_API_KEY",
        }  # env khớp host nhưng provider sai
    )
    assert len(errors) == 1 and "provider" in errors[0] and "api_key_env" not in errors[0]


def test_failed_result_keeps_provider_host_and_reported_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"model": "gw-model", "choices": [{"message": {"content": "không phải json"}}]}
        return httpx.Response(200, json=body)

    result = run_vlm_unit(_req(), _client(handler), CounterBudget(2))
    assert result.reason_code is VlmReasonCode.PARSE_FAILURE
    assert (
        result.response_model == "gw-model"
        and result.provider_host == "dashscope-intl.aliyuncs.com"
    )
