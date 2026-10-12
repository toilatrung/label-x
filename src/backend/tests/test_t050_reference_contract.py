"""T-050: validate wire fixtures against OpenAPI; runtime enforcement belongs to T-054."""

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft4Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = yaml.safe_load((ROOT / "docs/04-api/openapi.yaml").read_text(encoding="utf-8"))
FIXTURE = json.loads(
    (ROOT / "src/backend/fixtures/m04_reference_contract_v1.json").read_text(encoding="utf-8")
)


def _json_schema(value: Any) -> Any:
    """OpenAPI 3.0 nullable is not understood by JSON Schema draft 4."""
    if isinstance(value, list):
        return [_json_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _json_schema(item) for key, item in value.items() if key != "nullable"}
    if value.get("nullable"):
        result["type"] = [result["type"], "null"]
    return result


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        value = CONTRACT
        for part in schema["$ref"].removeprefix("#/").split("/"):
            value = value[part]
        return _resolve(value)
    result = copy.deepcopy(schema)
    for key, value in result.items():
        if isinstance(value, dict):
            result[key] = _resolve(value)
        elif isinstance(value, list):
            result[key] = [_resolve(item) if isinstance(item, dict) else item for item in value]
    return result


def _validator(schema: dict[str, Any]) -> Draft4Validator:
    return Draft4Validator(_json_schema(_resolve(schema)), format_checker=FormatChecker())


@pytest.mark.parametrize("case", FIXTURE["requests"], ids=lambda case: case["id"])
def test_wire_examples_match_declared_request_and_response(case: dict[str, Any]) -> None:
    request = case["request"]
    operation = CONTRACT["paths"][request["path"]][request["method"]]
    response = case["response"]
    if "{id}" in request["path"]:
        assert request["path_parameters"]["id"] > 0
    response_spec = _resolve(operation["responses"][str(response["status"])])
    _validator(response_spec["content"]["application/json"]["schema"]).validate(response["body"])
    if "body" in request:
        validator = _validator(operation["requestBody"]["content"]["application/json"]["schema"])
        errors = list(validator.iter_errors(request["body"]))
        if case["id"] == "missing-required-version":
            assert errors, "The negative wire example must fail request validation"
        else:
            assert not errors, errors
        assert request["headers"]["Idempotency-Key"]


@pytest.mark.parametrize(
    ("schema", "field"),
    [
        ("ReferenceCreate", "ground_truth"),
        ("ReferenceCreate", "preparer_user_ids"),
        ("ReferenceDeriveRequest", "reason"),
        ("ReferenceApprovalRequest", "version"),
        ("ReferenceLockRequest", "version"),
        ("ReferenceEvidence", "split_manifest_checksum"),
        ("ReferenceVersion", "error_set_checksum"),
    ],
)
def test_missing_provenance_is_rejected_by_schema(schema: str, field: str) -> None:
    cases = {case["id"]: case for case in FIXTURE["requests"]}
    samples = {
        "ReferenceCreate": cases["create-draft"]["request"]["body"],
        "ReferenceDeriveRequest": cases["derive-version"]["request"]["body"],
        "ReferenceApprovalRequest": cases["approve-mapping"]["request"]["body"],
        "ReferenceLockRequest": cases["lock-reference"]["request"]["body"],
        "ReferenceEvidence": cases["lock-reference"]["response"]["body"]["evidence"],
        "ReferenceVersion": cases["lock-reference"]["response"]["body"]["versions"][0],
    }
    value = copy.deepcopy(samples[schema])
    del value[field]
    assert list(_validator(CONTRACT["components"]["schemas"][schema]).iter_errors(value))


@pytest.mark.parametrize("mutation", ["format", "checksum", "learner_independent", "source_groups"])
def test_gt_manifest_refuses_invalid_or_learner_source(mutation: str) -> None:
    gt = copy.deepcopy(FIXTURE["requests"][0]["request"]["body"]["ground_truth"])
    gt[mutation] = {
        "format": "labelx_json",
        "checksum": "sha256:not-a-real-digest",
        "learner_independent": False,
        "source_groups": [],
    }[mutation]
    assert list(
        _validator(CONTRACT["components"]["schemas"]["GroundTruthManifest"]).iter_errors(gt)
    )


def test_roles_transitions_and_error_inventory_are_consistent() -> None:
    rbac = (ROOT / "docs/04-api/rbac-matrix.html").read_text(encoding="utf-8")
    states = (ROOT / "docs/04-api/state-machines.html").read_text(encoding="utf-8")
    for path, item in CONTRACT["paths"].items():
        if not path.startswith("/api/references/"):
            continue
        for method, operation in item.items():
            assert operation["operationId"] in rbac
            if method == "post":
                assert operation["x-labelx-transition"] in states
                assert {"400", "403", "404", "409", "422"} <= set(operation["responses"])
                assert (
                    "data_model_owner" in operation["x-labelx-roles"]
                    if (path.endswith("/derive/") or path == "/api/references/")
                    else "data_model_owner" not in operation["x-labelx-roles"]
                )
    ids = [case["id"] for case in FIXTURE["requests"]]
    assert len(ids) == len(set(ids))
    assert {
        "wrong-dataset",
        "same-person-approval",
        "same-person-lock",
        "alias-person-lock",
        "lock-before-review",
        "lock-unverified-split",
        "lock-training-overlap",
        "lock-unresolved-cases",
        "lock-missing-policy-qa",
        "heldout-group-overlap",
        "stale-approval",
        "locked-version-write",
        "checksum-mismatch",
        "invalid-policy-order",
        "idempotency-conflict",
        "read-outside-dataset",
        "wrong-role-create",
        "wrong-role-approve",
        "wrong-role-lock",
        "identity-missing-lock",
        "training-check-not-run",
    } <= set(ids)


def test_locked_provenance_and_correction_preserve_prior_version() -> None:
    cases = {case["id"]: case for case in FIXTURE["requests"]}
    locked = cases["lock-reference"]["response"]["body"]
    version = locked["versions"][0]
    assert version["locked_by"] == version["approved_by"]
    assert version["created_by"] != version["locked_by"]
    assert version["locked_by"] not in locked["preparer_user_ids"]
    assert version["policy"] == locked["policy"]
    assert version["evidence"] == locked["evidence"]
    assert version["mapping"] == locked["mapping"]
    assert version["evidence"]["split_verified"]
    assert version["evidence"]["training_overlap_status"] == "passed"
    assert version["evidence"]["unresolved_case_count"] == 0
    assert cases["replay-lock"]["response"] == cases["lock-reference"]["response"]
    corrected = cases["correct-locked-parent"]["response"]["body"]
    assert corrected["versions"][0] == version
    assert corrected["versions"][1]["parent_version"] == version["version"]
    assert corrected["versions"][1]["mapping_checksum"] != version["mapping_checksum"]
    assert corrected["locked_version"] == "v1" and corrected["active_version"] == "v2"
    for body in (locked, corrected):
        assert not {"ranking", "risk_score", "candidates", "detector_output"} & body.keys()
    for error in version["mapping"]["errors"]:
        assert error["family"] in {"E1", "E2", "E3"}
        assert error["gt_object_id"] is not None
        if error["family"] == "E3":
            assert error["annotation_id"] is not None
    for key in (
        "ground_truth_checksum",
        "mapping_checksum",
        "policy_checksum",
        "evidence_checksum",
        "error_set_checksum",
    ):
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", version[key])


def test_boundary_handoff_is_explicit_and_not_an_approved_default() -> None:
    boundaries = {case["name"]: case for case in FIXTURE["boundaries"]}
    assert boundaries["matching-equality"] == {
        "name": "matching-equality",
        "iou": 0.5,
        "expected": "matched",
    }
    assert boundaries["ambiguous-equality"]["expected"] == "ambiguous"
    assert boundaries["matching-below"]["expected"] == "ambiguous"
    assert boundaries["area-equality"]["expected"] == "eligible"
    assert boundaries["area-below"]["expected"] == "ignored"
    assert FIXTURE["baseline"]["pending_gates"]
    assert "Synthetic" in FIXTURE["baseline"]["purpose"]
