"""Contract guard for the shared M-03 review/rework fixture (T-032)."""

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = ROOT / "docs/04-api/openapi.yaml"
MATRIX_PATH = ROOT / "docs/04-api/m03-contract-model-fixture-matrix.html"
FIXTURE_PATH = ROOT / "src/backend/fixtures/m03-review-workflow-v1.json"


@pytest.fixture(scope="module")
def contract() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _enum(contract: dict[str, Any], schema: str) -> set[str]:
    return set(contract["components"]["schemas"][schema]["enum"])


def test_fixture_declares_reviewed_baseline_and_sources(fixture: dict[str, Any]) -> None:
    assert fixture["schema_version"] == "labelx.m03.contract-fixture.v1"
    assert fixture["fixture_id"] == "m03-review-workflow-v1"
    baseline = fixture["baseline"]
    assert len(baseline["git_sha"]) == 40
    assert baseline["unapproved_contract_deltas_implemented"] is False

    for key in ("openapi", "state_machines", "rbac_matrix", "contract_matrix"):
        assert (ROOT / baseline[key]).is_file(), key


def test_fixture_uses_contract_enums(fixture: dict[str, Any], contract: dict[str, Any]) -> None:
    queue_names = _enum(contract, "QueueName")
    frame_states = _enum(contract, "FrameReviewState")
    issue_states = _enum(contract, "IssueState")
    issue_families = _enum(contract, "IssueFamily")
    engines = _enum(contract, "EngineName")
    roles = _enum(contract, "Role")

    assert {frame["queue"] for frame in fixture["frames"]} <= queue_names
    assert {frame["review_state"] for frame in fixture["frames"]} <= frame_states
    assert {issue["state"] for issue in fixture["issues"]} <= issue_states
    assert {issue["family"] for issue in fixture["issues"]} <= issue_families
    assert {result["engine"] for result in fixture["engine_statuses"]} <= engines
    assert {identity["role"] for identity in fixture["identities"]} <= roles


def test_fixture_relationships_are_stable_and_complete(fixture: dict[str, Any]) -> None:
    identity_ids = {identity["user_id"] for identity in fixture["identities"]}
    frame_ids = {frame["id"] for frame in fixture["frames"]}
    issue_ids = {issue["id"] for issue in fixture["issues"]}

    assert len(identity_ids) == len(fixture["identities"])
    assert len(frame_ids) == len(fixture["frames"])
    assert len(issue_ids) == len(fixture["issues"])
    assert all(frame["run_id"] == fixture["run"]["id"] for frame in fixture["frames"])
    assert all(lease["frame_id"] in frame_ids for lease in fixture["leases"])
    assert all(lease["holder_user_id"] in identity_ids for lease in fixture["leases"])
    assert all(issue["frame_id"] in frame_ids for issue in fixture["issues"])
    assert all(item["issue_id"] in issue_ids for item in fixture["rework_requests"])

    aliases = [
        identity
        for identity in fixture["identities"]
        if identity["person_key"] == "person-reviewer-a"
    ]
    assert {identity["user_id"] for identity in aliases} == {701, 703}


def test_fixture_covers_required_m03_failure_and_resume_cases(fixture: dict[str, Any]) -> None:
    scenarios = fixture["scenarios"]
    categories = {scenario["category"] for scenario in scenarios}
    assert {"allowed", "denial", "expiry", "resume", "revision", "engine_failure"} <= categories

    scenario_ids = {scenario["id"] for scenario in scenarios}
    assert {
        "queue-self-review-skipped",
        "queue-missing-identity",
        "lease-second-tab-resume",
        "lease-expired-renew",
        "frame-engine-failure-visible",
        "rework-revision-unchanged",
        "rework-same-person-verifier",
    } <= scenario_ids


def test_fixture_scenarios_only_use_current_contract_operations(
    fixture: dict[str, Any], contract: dict[str, Any]
) -> None:
    for scenario in fixture["scenarios"]:
        operation = scenario["operation"]
        path_item = contract["paths"].get(operation["path"])
        assert path_item is not None, scenario["id"]
        assert operation["method"] in path_item, scenario["id"]


def test_unapproved_read_deltas_are_explicit_and_not_in_openapi(
    fixture: dict[str, Any], contract: dict[str, Any]
) -> None:
    gaps = fixture["contract_gaps"]
    assert {gap["id"] for gap in gaps} == {f"M03-D{index:02d}" for index in range(1, 7)}

    for gap in gaps:
        assert gap["approved"] is False
        assert gap["decision_status"].startswith("requires_")
        for key in ("proposed_operation", "additional_proposed_operation"):
            operation = gap.get(key)
            if operation is None:
                continue
            implemented_methods = contract["paths"].get(operation["path"], {})
            assert operation["method"] not in implemented_methods, gap["id"]


def test_unresolved_policy_values_are_not_promoted_to_defaults(fixture: dict[str, Any]) -> None:
    lease = fixture["policy_proposals"]["lease"]
    effort = fixture["policy_proposals"]["effort_idle"]

    assert lease["decision_status"] == "requires_product_owner_decision"
    assert lease["ttl_seconds"] is None
    assert lease["incomplete_reservation_seconds"] is None
    assert {"TBD-09", "DEC-002", "BLOCKER-008", "FR-REV-04"} <= set(lease["source"])

    assert effort["decision_status"] == "requires_product_owner_decision"
    assert effort["t_idle_seconds"] is None
    assert {"TBD-11", "FR-EVL-06"} <= set(effort["source"])


def test_candidate_and_issue_have_one_declared_evidence_source(fixture: dict[str, Any]) -> None:
    ownership = fixture["domain_ownership"]
    assert ownership["candidate_record"] == "orchestration.models.CandidateRecord"
    assert ownership["candidate_evidence"] == "orchestration.models.CandidateRecord.evidence"
    assert "not implemented by T-032" in ownership["review_issue"]
    assert "must not create a second candidate table" in ownership["rule"]

    engine_issues = [issue for issue in fixture["issues"] if issue["origin"] == "engine"]
    assert engine_issues
    assert all(issue["candidate_record_id"] for issue in engine_issues)
    assert all(issue["evidence"] for issue in engine_issues)


def test_matrix_contains_every_delta_and_handoff_guard(fixture: dict[str, Any]) -> None:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    for gap in fixture["contract_gaps"]:
        assert gap["id"] in matrix

    assert "không sửa OpenAPI" in matrix
    assert "không tự phê duyệt CR-108" in matrix
    assert "CandidateRecord" in matrix
    assert "CHỜ REVIEW" in matrix
