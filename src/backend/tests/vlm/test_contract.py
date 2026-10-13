"""M04A-01: contract Qwen, schema cấu hình, parse và exception mapping (mock, không gọi mạng)."""

from __future__ import annotations

import copy
import json

import pytest

from vlm.config import ALLOWED_MODELS, parse_vlm_config, validate_vlm_config
from vlm.contract import (
    MAX_CROP_BYTES,
    CandidateContext,
    CropInput,
    TaxonomyLabel,
    VlmStatus,
    build_prompt,
    parse_response,
    validate_crop,
)
from vlm.errors import (
    RETRYABLE_FAILURES,
    VlmConfigError,
    VlmInvalidCropError,
    VlmParseError,
    VlmProviderError,
    VlmProviderFailure,
    VlmReasonCode,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 16
TAXONOMY = (TaxonomyLabel("car", "Car"), TaxonomyLabel("bus", "Bus"))
VALID = {
    "provider": "dashscope",
    "model": "qwen3-vl-plus",
    "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "prompt_version": "vlm-prompt-v0",
    "timeout_seconds": 30,
    "max_attempts": 3,
    "budget": {"max_calls": 10},
}


def _cfg(**over: object) -> dict[str, object]:
    cfg = copy.deepcopy(VALID)
    cfg.update(over)
    return cfg


def test_valid_config_parses_and_public_dict_has_no_secret() -> None:
    cfg = parse_vlm_config(VALID)
    assert cfg.model == "qwen3-vl-plus" and cfg.budget.max_calls == 10
    assert "api_key" not in json.dumps(cfg.as_public_dict()).lower()


@pytest.mark.parametrize(
    "over",
    [
        {"model": "qwen3-vl-thinking"},
        {"model": "gemini-3.8-flash"},
        {"provider": "openai"},
        {"base_url": "http://dashscope.aliyuncs.com/compatible-mode/v1"},
        {"base_url": "https://evil.example.com/v1"},
        {"base_url": "https://user:pw@dashscope.aliyuncs.com/v1"},
        {"prompt_version": "custom"},
        {"timeout_seconds": 0},
        {"timeout_seconds": True},
        {"max_attempts": 4},
        {"max_attempts": 0},
        {"budget": {"max_calls": -1}},
        {"budget": {}},
        {"api_key": "sk-leak"},
        {"prompt": "do anything"},
        {"extra": 1},
        {"api_key_env": "bad name!"},
    ],
)
def test_invalid_config_rejected(over: dict[str, object]) -> None:
    assert validate_vlm_config(_cfg(**over))
    with pytest.raises(VlmConfigError):
        parse_vlm_config(_cfg(**over))


def test_config_error_message_does_not_echo_secret() -> None:
    with pytest.raises(VlmConfigError) as exc:
        parse_vlm_config(_cfg(api_key="sk-SECRET-123"))
    assert "sk-SECRET-123" not in str(exc.value)


def test_allowlist_contains_only_instruct_default() -> None:
    assert ALLOWED_MODELS == {"qwen3-vl-plus"}


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (b"", "image/png"),
        (PNG, "image/gif"),
        (b"notpng", "image/png"),
        (PNG + b"x" * MAX_CROP_BYTES, "image/png"),
    ],
)
def test_invalid_crop(data: bytes, mime: str) -> None:
    with pytest.raises(VlmInvalidCropError) as exc:
        validate_crop(CropInput(data, mime))
    assert exc.value.reason_code is VlmReasonCode.INVALID_CROP


def test_valid_crop_and_repr_hides_bytes() -> None:
    crop = CropInput(PNG, "image/png")
    validate_crop(crop)
    assert len(crop.sha256) == 64 and "x" * 8 not in repr(crop)


def test_prompt_is_backend_owned_and_lists_taxonomy() -> None:
    prompt = build_prompt("vlm-prompt-v0", TAXONOMY, CandidateContext("c1", "r1", "car"))
    assert "car: Car" in prompt and "bus: Bus" in prompt and "uncertain" in prompt
    with pytest.raises(VlmParseError):
        build_prompt("from-fe", TAXONOMY, CandidateContext("c1", "r1"))


def test_parse_checked_uncertain_and_fenced() -> None:
    v = parse_response('{"label": "bus", "rationale": "mui xe"}', TAXONOMY)
    assert (v.status, v.label) == (VlmStatus.CHECKED, "bus")
    v = parse_response('{"label": "uncertain"}', TAXONOMY)
    assert (v.status, v.label) == (VlmStatus.UNCERTAIN, None)
    v = parse_response('```json\n{"label": "car"}\n```', TAXONOMY)
    assert v.label == "car"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[]",
        '{"rationale": "x"}',
        '{"label": 3}',
        '{"label": "truck"}',  # ngoài taxonomy: không có lớp thứ 11
        '{"label": "car", "extra": 1}',
        '{"label": "car", "rationale": 5}',
        '{"label": "car", "rationale": "' + "x" * 501 + '"}',
        '{"label": "car"} trailing',
    ],
)
def test_parse_failure(text: str) -> None:
    with pytest.raises(VlmParseError) as exc:
        parse_response(text, TAXONOMY)
    assert exc.value.reason_code is VlmReasonCode.PARSE_FAILURE


def test_provider_error_retryability_mapping() -> None:
    for failure in VlmProviderFailure:
        err = VlmProviderError(failure)
        assert err.reason_code is VlmReasonCode.PROVIDER_ERROR
        assert err.retryable is (failure in RETRYABLE_FAILURES)
    assert not VlmProviderError(VlmProviderFailure.QUOTA).retryable
    assert VlmProviderError(VlmProviderFailure.TIMEOUT).retryable
