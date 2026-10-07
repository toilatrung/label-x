"""Contract M13 v1 (docs/04-api/openapi.yaml, T-001).

Tệp YAML là nguồn sự thật cho frontend sinh type tới khi backend có view; test giữ cho nó
hợp lệ OpenAPI 3.0 và truy được tới SRS (mỗi operation trích FR/BR/UC và vai trò).
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from drf_spectacular.validation import validate_schema

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "docs/04-api/openapi.yaml"
STATE_MACHINES = ROOT / "docs/04-api/state-machines.html"
SRS_SECTIONS = ROOT / "docs/label-x_system-requirement-specification/sections"

METHODS = {"get", "post", "put", "patch", "delete"}
TRACE_ID = re.compile(r"^(FR-[A-Z]{3}-\d{2}|BR-\d{2}|UC-\d{2}|NFR-\d{2})$")
PSEUDO_ROLES = {"anonymous", "authenticated", "lease_holder"}

# Endpoint SRS tab:api thuộc phạm vi T-001 (auth/phiên, snapshot, QC Run, guideline, hàng đợi).
REQUIRED_PATHS = {
    "/api/auth/login/": "post",
    "/api/auth/logout/": "post",
    "/api/auth/session/": "get",
    "/api/snapshots/": "post",
    "/api/snapshots/{id}/": "get",
    "/api/runs/": "post",
    "/api/runs/{id}/": "get",
    "/api/runs/{id}/cancel/": "post",
    "/api/runs/{id}/retry-failed/": "post",
    "/api/runs/{id}/ledger/": "get",
    "/api/runs/{id}/ranking/": "get",
    "/api/guidelines/rules/{rule_id}/": "get",
    "/api/queues/{name}/next/": "post",
    "/api/leases/{id}/renew/": "post",
    "/api/frames/{id}/issues/": "get",
    "/api/frames/{id}/complete/": "post",
}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    return [
        (path, method, op)
        for path, item in spec["paths"].items()
        for method, op in item.items()
        if method in METHODS
    ]


def test_contract_is_valid_openapi_3(spec):
    validate_schema(spec)


def test_contract_covers_t001_endpoints(spec):
    for path, method in REQUIRED_PATHS.items():
        assert method in spec["paths"].get(path, {}), f"thiếu {method.upper()} {path}"


def test_every_ref_resolves(spec):
    def walk(node: Any) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str):
                target: Any = spec
                for part in ref.removeprefix("#/").split("/"):
                    assert part in target, f"$ref không trỏ tới đâu: {ref}"
                    target = target[part]
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(spec)


def test_every_operation_traces_to_srs(spec):
    srs = "\n".join(p.read_text(encoding="utf-8") for p in SRS_SECTIONS.glob("*.tex"))
    for path, method, op in operations(spec):
        trace = op.get("x-labelx-trace")
        assert trace, f"{method.upper()} {path} thiếu x-labelx-trace"
        for ref in trace:
            assert TRACE_ID.match(ref), f"{path}: mã truy vết sai dạng {ref}"
            assert ref in srs, f"{path}: {ref} không có trong SRS"


def test_every_operation_declares_known_roles(spec):
    roles = set(spec["components"]["schemas"]["Role"]["enum"]) | PSEUDO_ROLES
    for path, method, op in operations(spec):
        declared = op.get("x-labelx-roles")
        assert declared, f"{method.upper()} {path} thiếu x-labelx-roles"
        assert set(declared) <= roles, f"{path}: vai trò lạ {set(declared) - roles}"


def test_operation_ids_are_unique(spec):
    ids = [op["operationId"] for _, _, op in operations(spec)]
    assert len(ids) == len(set(ids))


def test_error_responses_use_shared_error_schema(spec):
    shared = spec["components"]["responses"]
    for path, method, op in operations(spec):
        for status, response in op["responses"].items():
            if not status.startswith("4"):
                continue
            ref = response.get("$ref", "")
            assert ref.startswith("#/components/responses/"), f"{method.upper()} {path} {status}"
            schema = shared[ref.rsplit("/", 1)[1]]["content"]["application/json"]["schema"]
            assert schema == {"$ref": "#/components/schemas/Error"}


def test_transitions_exist_in_state_machine_doc(spec):
    doc = STATE_MACHINES.read_text(encoding="utf-8")
    for path, _method, op in operations(spec):
        event = op.get("x-labelx-transition")
        if event:
            assert f"<code>{event}</code>" in doc, f"{path}: {event} không có trong state-machines"


def test_frame_states_include_incomplete(spec):
    # BLOCKER-008 / DEC-002: lease hết hạn khi đã lưu một phần → frame "đang dở".
    assert "incomplete" in spec["components"]["schemas"]["FrameReviewState"]["enum"]
