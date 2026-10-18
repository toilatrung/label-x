"""Issue #392: exact deterministic boundaries and honest aggregation evidence.

Cases whose infrastructure or contract behavior is missing (ENG-02, AGG-04, ENG-04) stay planned;
supplemental checks must not be substituted for those matrix bindings.
"""

import os
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.db import connection
from django.utils import timezone

from engines.duplicate_overlap import Annotation, run_duplicate_overlap_engine
from engines.geometry import (
    GEOMETRY_NOT_CHECKED_RULE_IDS,
    generate_geometry_candidates,
    run_geometry_engine,
)
from engines.interface import (
    Anchor,
    Candidate,
    EngineConfig,
    EngineInput,
    EngineOutput,
    EngineUnitRef,
    EngineUnitResult,
    FrameKey,
    NotCheckedEngineUnitResult,
    ObjectRef,
    public_status,
)
from engines.schema_taxonomy import (
    RequiredAttribute,
    Taxonomy,
    TaxonomyLabel,
    generate_schema_taxonomy_candidates,
)
from engines.structural import AnnotationAttribute, StructuralAnnotation, StructuralFrame
from orchestration import services
from orchestration.dispatch import build_engine_input, run_work_unit
from orchestration.models import CandidateRecord, LedgerUnit, ShardCommit
from orchestration.services import commit_shard_output, ledger_counts, seed_ledger
from review.models import Issue, ReviewDecision
from runs.models import EngineResult, RunRankingEntry, WorkUnit
from tests.orchestration.helpers import make_run
from tests.review.test_issues_decisions import claim, decide
from tests.review.test_queue_lease import world  # noqa: F401 - shared locked-snapshot fixture

FRAME = FrameKey(9, 0)


def annotation(**changes):
    return replace(StructuralAnnotation("a", 4, (), 10, 10, 20, 20, 100, 100), **changes)


def engine_input(engine="geometry", *, run_id=7, frames=(FRAME,), shard=0):
    return EngineInput(
        f"p1-{run_id}-{engine}-{shard}",
        run_id,
        11,
        engine,
        "1.0.0",
        EngineConfig(engine, "guideline-v1", True, {}),
        1,
        shard,
        tuple(EngineUnitRef("frame", frame) for frame in frames),
    )


def test_eng_01_taxonomy_version_valid_unknown_and_missing_attribute():
    taxonomy = Taxonomy(
        "taxonomy-v1",
        (
            TaxonomyLabel(
                4,
                "car",
                (RequiredAttribute(8, "motion_state", "A-007", ("moving",)),),
            ),
        ),
    )
    valid = annotation(attributes=(AnnotationAttribute(8, "moving"),))
    assert (
        generate_schema_taxonomy_candidates(
            frame=FRAME,
            annotation=valid,
            taxonomy=taxonomy,
        )
        == ()
    )
    for bad, rule, expected, actual in (
        (annotation(label_id=999), "S-001", "label_id in taxonomy", "label_id=999"),
        (annotation(), "A-007", "required motion_state in [moving]", "<missing>"),
    ):
        (candidate,) = generate_schema_taxonomy_candidates(
            frame=FRAME,
            annotation=bad,
            taxonomy=taxonomy,
        )
        assert candidate.anchor.rule_id == candidate.evidence.rule_id == rule
        assert candidate.anchor.objects == (ObjectRef("cvat_shape", "a"),)
        assert candidate.evidence.taxonomy_version == "taxonomy-v1"
        assert (candidate.evidence.expected, candidate.evidence.actual) == (expected, actual)
        assert candidate.evidence.structural_warning is True
        assert candidate.evidence.is_kpi_error is False
        assert not hasattr(candidate, "state")  # Suspicion, no confirmed defect state.
        with pytest.raises(FrozenInstanceError):
            candidate.family = "confirmed"


def test_eng_02_bounds_area_inverted_and_unchecked_tightness():
    for axis in ("left", "top", "right", "bottom"):
        for distance in (1.999, 2, 2.001):
            changes = {
                "left": {"x1": -distance},
                "top": {"y1": -distance},
                "right": {"x2": 100 + distance},
                "bottom": {"y2": 100 + distance},
            }[axis]
            result = generate_geometry_candidates(frame=FRAME, annotation=annotation(**changes))
            assert bool(result) is (distance > 2), (axis, distance)
            if result:
                assert result[0].evidence.violations == ("outside_image_bounds",)
    for area in (23.999, 24, 24.001):
        result = generate_geometry_candidates(
            frame=FRAME,
            annotation=annotation(x1=0, y1=0, x2=area / 4, y2=4),
        )
        assert bool(result) is (area < 24)
        if result:
            assert result[0].evidence.violations == ("area_below_minimum",)
    for changes, violation in (
        ({"x1": 21}, "x1_not_less_than_x2"),
        ({"y1": 21}, "y1_not_less_than_y2"),
    ):
        (candidate,) = generate_geometry_candidates(frame=FRAME, annotation=annotation(**changes))
        assert violation in candidate.evidence.violations
    output = run_geometry_engine(
        engine_input(),
        {
            FRAME: StructuralFrame(100, 100, (annotation(x1=0, y1=0, x2=100, y2=100),)),
        },
    )
    assert output.candidates == ()
    assert "G-009" in GEOMETRY_NOT_CHECKED_RULE_IDS


def test_eng_03_real_box_iou_boundary_preserves_pair_classes_and_review():
    for iou in (0.849999, 0.85, 0.850001):
        boxes = (Annotation("a", "car", 0, 0, 10, 10), Annotation("b", "truck", 0, 0, iou * 10, 10))
        output = run_duplicate_overlap_engine(engine_input("duplicate"), {FRAME: boxes})
        assert len(output.candidates) == int(iou >= 0.85)
        if output.candidates:
            (candidate,) = output.candidates
            assert candidate.evidence.annotation_ids == ("a", "b")
            assert candidate.evidence.labels == ("car", "truck")
            assert candidate.evidence.iou == pytest.approx(iou)
            assert candidate.evidence.same_label is False
            assert candidate.evidence.structural_warning is True
            assert candidate.evidence.is_kpi_error is False
            assert not hasattr(candidate, "state")


@pytest.mark.django_db(transaction=True)
def test_agg_03_persisted_failed_disabled_unsupported_partial_ledger():
    assert connection.vendor == "postgresql", "AGG integration requires PostgreSQL"
    run = make_run()
    frames = tuple(FrameKey(9, i) for i in range(5))
    inp = engine_input("fake", run_id=run.pk, frames=frames)
    seed_ledger(run.pk, inp.engine, inp.units)
    output = EngineOutput(
        inp.idempotency_key,
        inp.engine,
        inp.engine_version,
        (),
        (
            EngineUnitResult(inp.units[0], "completed", 1),
            EngineUnitResult(inp.units[1], "failed", 3),  # Decode failure remains eligible.
            NotCheckedEngineUnitResult(inp.units[2], "not_checked", 1, "not_applicable"),
            NotCheckedEngineUnitResult(inp.units[3], "not_checked", 1, "disabled"),
            EngineUnitResult(inp.units[4], "failed", 1),
        ),
    )
    assert commit_shard_output(inp, output)
    counts = ledger_counts(run.pk, inp.engine)
    assert (counts.total, counts.eligible, counts.completed, counts.failed) == (5, 4, 1, 2)
    assert (counts.not_checked, counts.excluded, counts.blocked) == (2, 1, 1)
    assert counts.coverage == 0.25
    assert counts.needs_exclusion_warning
    assert str(public_status(counts, finished=True)) == "partial"
    assert CandidateRecord.objects.filter(run=run).count() == 0


@pytest.mark.django_db(transaction=True)
def test_supplemental_transaction_rollback_and_replay_are_immutable():
    """Metadata fault only; does not claim real worker death or S3 fault coverage."""
    assert connection.vendor == "postgresql"
    run = make_run()
    inp = engine_input("fake", run_id=run.pk)
    seed_ledger(run.pk, inp.engine, inp.units)
    candidate = Candidate(
        "fake",
        "1.0.0",
        "E3",
        FRAME,
        Anchor("pair", (ObjectRef("cvat_shape", "a"),), "v1", "DUP-01"),
        {"source": "worker", "iou": 0.9},
    )
    output = EngineOutput(
        inp.idempotency_key,
        "fake",
        "1.0.0",
        (candidate,),
        (EngineUnitResult(inp.units[0], "completed", 1),),
    )
    with patch.object(services, "_apply_unit_results", side_effect=RuntimeError("metadata fault")):
        with pytest.raises(RuntimeError, match="metadata fault"):
            commit_shard_output(inp, output)
    assert not ShardCommit.objects.filter(run=run).exists()
    assert not CandidateRecord.objects.filter(run=run).exists()
    assert ledger_counts(run.pk, "fake").pending == 1
    assert commit_shard_output(inp, output)
    before = list(CandidateRecord.objects.filter(run=run).values())
    changed = replace(output, candidates=(replace(candidate, evidence={"changed": True}),))
    assert commit_shard_output(inp, changed) is False
    assert list(CandidateRecord.objects.filter(run=run).values()) == before
    assert ledger_counts(run.pk, "fake").completed == 1


KILL_WORKER = """
import os, signal, sys
import django
django.setup()
from unittest import mock
from orchestration.dispatch import build_engine_input, run_work_unit

def die(*args, **kwargs):
    os.kill(os.getpid(), signal.SIGKILL)  # no cleanup, no ack: a real worker death

with mock.patch("orchestration.services._apply_unit_results", side_effect=die):
    run_work_unit.run(int(sys.argv[1]))
"""
SHAPES = [
    {"id": i, "type": "rectangle", "frame": 0, "label_id": 4, "points": [0, 0, 10, 10]}
    for i in (1, 2)
]


def _provenance(run):
    return (
        list(ShardCommit.objects.filter(run=run).values()),
        list(CandidateRecord.objects.filter(run=run).order_by("pk").values()),
        list(LedgerUnit.objects.filter(run=run).order_by("pk").values()),
    )


@pytest.mark.django_db(transaction=True)
def test_agg_01_real_worker_sigkill_then_redelivery_and_replay_keep_candidates_immutable():
    """A separate worker process is SIGKILLed inside the commit transaction (PostgreSQL)."""
    assert connection.vendor == "postgresql", "AGG integration requires PostgreSQL"
    run = make_run(engine="duplicate", shapes=SHAPES)
    unit = run.work_units.order_by("shard_index").first()
    db = connection.settings_dict
    env = {
        **os.environ,
        "DATABASE_URL": (
            f"postgres://{db['USER']}:{db['PASSWORD']}@{db['HOST']}:{db['PORT']}/{db['NAME']}"
        ),
    }
    dead = subprocess.run(
        [sys.executable, "-c", KILL_WORKER, str(unit.pk)],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert dead.returncode == -9, dead.stderr.decode()[-500:]  # SIGKILL, not a handled error
    unit.refresh_from_db()
    assert unit.status == WorkUnit.Status.RUNNING  # never acked; broker will redeliver
    assert not ShardCommit.objects.filter(run=run).exists()
    assert not CandidateRecord.objects.filter(run=run).exists()

    # Redelivery while the dead worker's lease is live is skipped; after expiry it completes once.
    assert run_work_unit.apply(args=[unit.pk]).get() == "running"
    WorkUnit.objects.filter(pk=unit.pk).update(started_at=timezone.now() - timedelta(hours=2))
    assert run_work_unit.apply(args=[unit.pk]).get() == WorkUnit.Status.COMPLETED
    (commit,) = ShardCommit.objects.filter(run=run)
    (candidate,) = CandidateRecord.objects.filter(run=run)
    assert candidate.shard_id == commit.pk  # provenance: shard, engine, versions, evidence hash
    assert (candidate.engine, candidate.engine_version) == (commit.engine, commit.engine_version)
    assert candidate.evidence_sha256 and commit.output_sha256
    before = _provenance(run)

    # Replays (duplicate message, and a replay carrying different evidence) change nothing.
    assert run_work_unit.apply(args=[unit.pk]).get() == WorkUnit.Status.COMPLETED
    engine_in = build_engine_input(unit)
    original = Candidate(
        candidate.engine,
        candidate.engine_version,
        candidate.family,
        FRAME,
        Anchor("pair", (ObjectRef("cvat_shape", "1"),), candidate.policy_version, "DUP-01"),
        {"changed": True},
    )
    changed = EngineOutput(
        engine_in.idempotency_key,
        engine_in.engine,
        engine_in.engine_version,
        (original,),
        tuple(EngineUnitResult(u, "completed", 1) for u in engine_in.units),
    )
    assert commit_shard_output(engine_in, changed) is False
    assert _provenance(run) == before


@pytest.mark.django_db
def test_agg_02_multi_source_candidates_keep_sources_versions_and_independent_decisions(world):  # noqa: F811
    assert connection.vendor == "postgresql", "AGG integration requires PostgreSQL"
    run = world["run"]
    frame = FrameKey(200, 0)
    shape = (ObjectRef("cvat_shape", "91"),)

    def cand(engine, family, rule, policy="v1", evidence=None):
        return Candidate(
            engine,
            "1.0.0",
            family,
            frame,
            Anchor("pair", shape, policy, rule),
            evidence or {"source": engine, "rule_id": rule},
        )

    def commit(engine, shard, *candidates):
        inp = engine_input(engine, run_id=run.pk, frames=(frame,), shard=shard)
        inp = replace(inp, snapshot_id=run.snapshot_id)
        seed_ledger(run.pk, engine, inp.units)
        out = EngineOutput(
            inp.idempotency_key,
            engine,
            "1.0.0",
            candidates,
            tuple(EngineUnitResult(u, "completed", 1) for u in inp.units),
        )
        assert commit_shard_output(inp, out)

    # Same object seen by two engines of different defect families; one engine repeats the same
    # finding in a second shard (same dedup key) and again under a new policy version.
    commit("geometry", 0, cand("geometry", "structural", "G-014"))
    commit("duplicate_overlap", 0, cand("duplicate_overlap", "E3", "DUP-01"))
    commit(
        "duplicate_overlap",
        1,
        cand("duplicate_overlap", "E3", "DUP-01"),
        cand("duplicate_overlap", "E3", "DUP-01", policy="v2"),
    )
    records = list(CandidateRecord.objects.filter(run=run).order_by("pk"))
    assert [(r.engine, r.family, r.policy_version) for r in records] == [
        ("geometry", "structural", "v1"),
        ("duplicate_overlap", "E3", "v1"),
        ("duplicate_overlap", "E3", "v2"),
    ]
    assert len({r.dedup_key for r in records}) == 3  # merged only on identical key/version
    assert records[0].shard.engine == "geometry"  # source of each finding stays attributable
    assert {r.shard.engine for r in records[1:]} == {"duplicate_overlap"}
    before = [(r.pk, r.evidence, r.evidence_sha256) for r in records]

    for engine in ("geometry", "duplicate_overlap"):
        EngineResult.objects.create(run=run, engine=engine, status="completed")
    RunRankingEntry.objects.filter(ranking__run=run).update(missing_evidence=False)
    lease_id, frame_id = claim(world)
    issues = {i.candidate_id: i for i in Issue.objects.filter(frame_review_id=frame_id)}
    assert set(issues) == {r.pk for r in records}  # one reviewer issue per distinct candidate
    structural, dup_v1, dup_v2 = (issues[r.pk] for r in records)
    assert (structural.family, dup_v1.family) == ("structural", "E3")

    confirm = decide(world, lease_id, structural.pk, family="structural", severity="minor")
    reject = decide(world, lease_id, dup_v1.pk, action="reject", reason="Two real objects")
    assert confirm.status_code == reject.status_code == 201, (confirm.data, reject.data)
    for issue in (structural, dup_v1, dup_v2):
        issue.refresh_from_db()
    assert (structural.state, dup_v1.state) == (Issue.State.CONFIRMED, Issue.State.REJECTED)
    assert dup_v2.state == Issue.State.IN_REVIEW  # sibling on the same object is not decided
    assert ReviewDecision.objects.filter(issue__in=(structural, dup_v1, dup_v2)).count() == 2
    after = [(r.pk, r.evidence, r.evidence_sha256) for r in CandidateRecord.objects.order_by("pk")]
    assert after == before  # decisions never mutate engine candidates
