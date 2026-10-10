"""Contract guard for the shared M-03 review/rework fixture (T-032)."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from fixtures.m03_review_workflow import materialize_scenario
from orchestration.dedup import sha256_hex
from orchestration.models import CandidateRecord
from ranking.score_v0 import FrameInput, rank_frames

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


def _by_id(items: list[dict[str, Any]], item_id: int) -> dict[str, Any]:
    return next(item for item in items if item["id"] == item_id)


def _scenario(fixture: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    return next(item for item in fixture["scenarios"] if item["id"] == scenario_id)


def _as_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _claim_result(fixture: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the fixture's claim/resume rules at the scenario clock."""
    fixture = materialize_scenario(fixture, scenario)
    actor_id = scenario["actor_user_id"]
    identities = {item["user_id"]: item for item in fixture["identities"]}
    actor = identities[actor_id]
    if not actor["mapped"]:
        return {"status": 403, "error_code": "IDENTITY_MAPPING_MISSING"}
    as_of = _as_datetime(scenario["as_of"])
    queue = scenario["request"]["path_params"]["name"]
    run_id = scenario["request"]["body"]["run_id"]

    active_leases = [
        lease for lease in fixture["leases"] if _as_datetime(lease["expires_at"]) > as_of
    ]
    held = next((lease for lease in active_leases if lease["holder_user_id"] == actor_id), None)
    if held is not None:
        return {
            "status": 200,
            "lease_id": held["id"],
            "frame_id": held["frame_id"],
            "resumed": True,
        }

    leased_frame_ids = {lease["frame_id"] for lease in active_leases}
    candidates = sorted(fixture["frames"], key=lambda frame: frame["rank"])
    for frame in candidates:
        assignee = identities[frame["snapshot_assignee_user_id"]]
        if (
            frame["run_id"] == run_id
            and frame["queue"] == queue
            and frame["review_state"] in {"unreviewed", "incomplete"}
            and frame["id"] in scenario.get("fixture_scope_frame_ids", [frame["id"]])
            and frame["id"] not in leased_frame_ids
            and assignee["person_key"] != actor["person_key"]
        ):
            return {"status": 200, "frame_id": frame["id"], "resumed": False}
    return {"status": 204}


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
    annotator_aliases = [
        identity
        for identity in fixture["identities"]
        if identity["person_key"] == "person-annotator-a"
    ]
    assert {identity["user_id"] for identity in annotator_aliases} == {702, 706}


def test_claim_and_resume_scenarios_are_distinguished_by_clock(
    fixture: dict[str, Any],
) -> None:
    fresh_claim = _scenario(fixture, "queue-allowed-risk-claim")
    second_tab = _scenario(fixture, "lease-second-tab-resume")

    assert _as_datetime(second_tab["as_of"]) < _as_datetime(
        _by_id(fixture["leases"], 350)["expires_at"]
    )
    assert _as_datetime(fresh_claim["as_of"]) > _as_datetime(
        _by_id(fixture["leases"], 350)["expires_at"]
    )
    assert _claim_result(fixture, second_tab) == second_tab["expected"]
    assert _claim_result(fixture, fresh_claim) == fresh_claim["expected"]


def test_same_person_verifier_reaches_separation_guard_after_recheck(
    fixture: dict[str, Any],
) -> None:
    scenario = _scenario(fixture, "rework-same-person-verifier")
    rework = _by_id(fixture["rework_requests"], scenario["request"]["path_params"]["id"])
    recheck = _by_id(fixture["recheck_runs"], rework["recheck_run_id"])
    identities = {item["user_id"]: item for item in fixture["identities"]}

    assert rework["status"] == "recheck_pending"
    assert rework["submitted_revision"] != rework["original_revision"]
    assert recheck["status"] == "completed"
    assert recheck["snapshot_revision"] == rework["submitted_revision"]
    assert scenario["request"]["body"]["revision"] == rework["submitted_revision"]

    verifier = identities[scenario["actor_user_id"]]
    annotator = identities[rework["annotator_user_id"]]
    error_code = (
        "SAME_REQUESTER_APPROVER" if verifier["person_key"] == annotator["person_key"] else None
    )
    assert error_code == scenario["expected"]["error_code"]


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
    candidates = {item["id"]: item for item in fixture["candidate_records"]}
    frames = {item["id"]: item for item in fixture["frames"]}
    assert engine_issues
    assert len(candidates) == len(fixture["candidate_records"])
    assert all(issue["candidate_record_id"] in candidates for issue in engine_issues)
    assert all(issue["evidence"] for issue in engine_issues)
    for issue in engine_issues:
        candidate = candidates[issue["candidate_record_id"]]
        frame = frames[issue["frame_id"]]
        assert candidate["run_id"] == fixture["run"]["id"]
        assert candidate["family"] == issue["family"]
        assert candidate["cvat_task_id"] == frame["frame_key"]["cvat_task_id"]
        assert candidate["frame_number"] == frame["frame_key"]["frame_number"]
        assert candidate["evidence"]
        assert candidate["evidence_sha256"] == sha256_hex(candidate["evidence"])
        assert issue["evidence"] == [candidate["evidence"]]
        assert issue["anchor"] == candidate["anchor"]


def test_candidate_seeds_support_existing_model_and_ranking(fixture: dict[str, Any]) -> None:
    shards = {item["id"]: item for item in fixture["shard_commits"]}
    required_fields = {
        field.attname
        for field in CandidateRecord._meta.fields
        if not field.primary_key and not field.null and not field.has_default()
    }
    for candidate in fixture["candidate_records"]:
        assert required_fields <= candidate.keys()
        shard = shards[candidate["shard_id"]]
        assert shard["run_id"] == candidate["run_id"]
        assert shard["snapshot_id"] == fixture["snapshot"]["id"]
        assert shard["engine"] == candidate["engine"]
        assert shard["engine_version"] == candidate["engine_version"]
        assert candidate["policy_version"] == candidate["anchor"]["policy_version"]
        shaped = {
            **candidate,
            "frame": {
                "cvat_task_id": candidate["cvat_task_id"],
                "frame_number": candidate["frame_number"],
            },
        }
        ranked, _ = rank_frames(
            [FrameInput(candidate["cvat_task_id"], candidate["frame_number"])],
            [shaped],
            seed=1,
        )
        assert len(ranked[0].contributions) == 1


def test_scenario_clocks_materialize_coherent_frame_and_issue_states(
    fixture: dict[str, Any],
) -> None:
    original = json.dumps(fixture, sort_keys=True)
    for scenario in fixture["scenarios"]:
        state = materialize_scenario(fixture, scenario)
        active_frame_ids = {
            lease["frame_id"]
            for lease in state["leases"]
            if _as_datetime(lease["expires_at"]) > _as_datetime(scenario["as_of"])
        }
        for frame in state["frames"]:
            assert (frame["review_state"] == "in_review") == (frame["id"] in active_frame_ids)
        for issue in state["issues"]:
            if issue["state"] == "in_review":
                assert issue["frame_id"] in active_frame_ids

    resume = materialize_scenario(fixture, _scenario(fixture, "lease-second-tab-resume"))
    fresh = materialize_scenario(fixture, _scenario(fixture, "queue-allowed-risk-claim"))
    assert _by_id(resume["frames"], 340)["review_state"] == "in_review"
    assert _by_id(fresh["frames"], 340)["review_state"] == "unreviewed"
    assert _by_id(fresh["issues"], 360)["state"] == "pending_review"
    assert _by_id(fresh["frames"], 342)["review_state"] == "incomplete"
    assert (
        _by_id(fresh["issues"], 361)["review_decisions"]
        == _by_id(fixture["issues"], 361)["review_decisions"]
    )
    assert json.dumps(fixture, sort_keys=True) == original


def test_queue_denial_scenarios_reach_their_expected_guards(fixture: dict[str, Any]) -> None:
    self_review = _scenario(fixture, "queue-self-review-skipped")
    assert _claim_result(fixture, self_review)["status"] == self_review["expected"]["status"]
    missing_identity = _scenario(fixture, "queue-missing-identity")
    assert _claim_result(fixture, missing_identity) == missing_identity["expected"]


@pytest.mark.parametrize(
    ("as_of", "frame_state", "issue_state"),
    [
        ("2026-10-10T06:29:59Z", "in_review", "in_review"),
        ("2026-10-10T06:30:00Z", "unreviewed", "pending_review"),
        ("2026-10-10T06:30:01Z", "unreviewed", "pending_review"),
    ],
)
def test_materializer_observes_exact_lease_expiry_boundary(
    fixture: dict[str, Any], as_of: str, frame_state: str, issue_state: str
) -> None:
    scenario = {"as_of": as_of}
    state = materialize_scenario(fixture, scenario)
    assert _by_id(state["frames"], 340)["review_state"] == frame_state
    assert _by_id(state["issues"], 360)["state"] == issue_state
    assert materialize_scenario(state, scenario) == state


def test_matrix_lists_every_contract_decision_action(contract: dict[str, Any]) -> None:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    actions = _enum(contract, "IssueDecisionAction")
    assert actions == {"confirm", "reject", "uncertain", "escalate", "request_fix"}
    assert all(f"<code>{action}</code>" in matrix for action in actions)


def test_matrix_contains_every_delta_and_handoff_guard(fixture: dict[str, Any]) -> None:
    matrix = MATRIX_PATH.read_text(encoding="utf-8")
    for gap in fixture["contract_gaps"]:
        assert gap["id"] in matrix

    assert "không sửa OpenAPI" in matrix
    assert "không tự phê duyệt CR-108" in matrix
    assert "CandidateRecord" in matrix
    assert "CHỜ REVIEW" in matrix
