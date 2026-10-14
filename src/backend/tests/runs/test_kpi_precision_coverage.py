"""BLOCKER-034 B-5 (DEC-023): P-1 Precision của candidate và C-1 Benchmark coverage."""

import pytest

from calibration.models import Benchmark, BenchmarkFrame, BenchmarkStatus
from review.models import Issue
from runs.kpi import benchmark_coverage, candidate_precision, compute_metrics
from snapshots.models import Snapshot
from tests.runs.test_summary_api import add_reviews, candidate, snapshot

pytest_plugins = ["tests.runs.test_summary_api"]

pytestmark = pytest.mark.django_db


def _issue(frame, cand, state):
    return Issue.objects.create(
        frame_review=frame, candidate=cand, family="E1", origin="engine", state=state, anchor={}
    )


def test_precision_counts_only_decided_candidate_issues(world):
    frame, other, _manual = add_reviews(world)  # Issue thủ công không có candidate: không tính
    geo = candidate(world)
    geo2 = candidate(world, index=2)
    _issue(frame, geo, "confirmed")
    _issue(frame, geo2, "resolved")
    _issue(other, candidate(world, index=3), "rejected")
    _issue(other, candidate(world, index=4), "escalated")  # chưa có quyết định
    _issue(other, candidate(world, index=5), "pending_review")
    value, decided, by_engine = candidate_precision([world["run"].pk])
    assert decided == 3 and value == pytest.approx(2 / 3)
    assert by_engine == {"geometry": {"confirmed": 2, "decided": 3, "value": pytest.approx(2 / 3)}}


def test_precision_metric_needs_e_min_decisions(world):
    frame, _, _ = add_reviews(world)
    _issue(frame, candidate(world), "confirmed")
    metrics, _ = compute_metrics(world["run"], e_min=30)
    p1 = metrics["P-1"]
    assert p1["status"] == "insufficient_sample" and p1["value"] is None and p1["sample_size"] == 1
    assert p1["method"] == "confirmed_over_decided_candidate_issues"
    assert p1["details"]["by_engine"]["geometry"]["decided"] == 1
    metrics, _ = compute_metrics(world["run"], e_min=1)
    assert metrics["P-1"]["status"] == "computed" and metrics["P-1"]["value"] == 1.0


def test_no_candidate_issue_means_not_checked(world):
    metrics, _ = compute_metrics(world["run"], e_min=1)
    assert metrics["P-1"]["status"] == "not_checked" and metrics["P-1"]["value"] is None


def _benchmark(world, frames, *, status=BenchmarkStatus.READY):
    bench = Benchmark.objects.create(
        name="b", dataset_id=42, status=status, frame_count=len(frames), created_by=world["user"]
    )
    BenchmarkFrame.objects.bulk_create(
        BenchmarkFrame(benchmark=bench, snapshot_frame=f, frame_id=f.pk) for f in frames
    )
    return bench


def test_benchmark_coverage_matches_task_and_frame_of_latest_ready_benchmark(world):
    assert benchmark_coverage(world["run"]) == (None, 0, 2, None)
    metrics, _ = compute_metrics(world["run"], e_min=1)
    assert metrics["C-1"]["status"] == "not_checked"
    assert metrics["C-1"]["method"] == "no_ready_benchmark"
    # Benchmark dựng trên Snapshot khác: so theo (task, frame), không theo id SnapshotFrame.
    other = snapshot(world["user"], frames=3, offset=700)
    other_frames = list(other.jobs.first().frames.order_by("frame_index"))
    _benchmark(world, other_frames[:1])
    newest = _benchmark(world, other_frames[1:3])
    _benchmark(world, other_frames, status=BenchmarkStatus.PENDING)  # chưa ready: bỏ qua
    # Snapshot của run có frame 0 và 1; Benchmark ready mới nhất có frame 1 và 2.
    assert benchmark_coverage(world["run"]) == (0.5, 1, 2, newest.pk)
    c1 = compute_metrics(world["run"], e_min=1)[0]["C-1"]
    assert c1["status"] == "computed" and c1["value"] == 0.5
    assert (c1["sample_size"], c1["denominator"]) == (1, 2)
    assert c1["details"] == {"benchmark_id": newest.pk}


def test_precision_includes_confirmed_lifecycle_and_separates_engines(world):
    frame, other, _ = add_reviews(world)
    states = ("confirmed", "fix_pending", "recheck_pending", "resolved", "reopened")
    for index, state in enumerate(states, start=1):
        _issue(frame, candidate(world, index=index), state)
    rejected = candidate(world, index=6)
    rejected.engine = "vlm"
    rejected.save(update_fields=["engine"])
    _issue(other, rejected, "rejected")
    # Candidate chưa sinh Issue không phải quyết định review.
    candidate(world, index=7)
    value, count, engines = candidate_precision([world["run"].pk])
    assert (value, count) == (5 / 6, 6)
    assert engines == {
        "geometry": {"confirmed": 5, "decided": 5, "value": 1.0},
        "vlm": {"confirmed": 0, "decided": 1, "value": 0.0},
    }
    assert candidate_precision([]) == (None, 0, {})


def test_coverage_scopes_dataset_task_and_deduplicates_overlapping_jobs(world):
    overlapping = snapshot(world["user"], tasks=(9, 9), offset=800)
    world["run"].snapshot = overlapping
    world["run"].save(update_fields=["snapshot"])
    frames = list(overlapping.jobs.first().frames.order_by("frame_index"))
    bench = _benchmark(world, frames[:1])
    # Một Dataset khác có Benchmark mới hơn cũng không được chọn.
    foreign = _benchmark(world, frames)
    foreign.dataset_id = 99
    foreign.save(update_fields=["dataset_id"])
    assert benchmark_coverage(world["run"]) == (0.5, 1, 2, bench.pk)
    # Cùng frame_index nhưng khác Task không khớp.
    wrong_task = snapshot(world["user"], tasks=(10,), offset=900)
    newest = _benchmark(world, list(wrong_task.jobs.first().frames.all()))
    assert benchmark_coverage(world["run"]) == (0.0, 0, 2, newest.pk)


def test_empty_snapshot_coverage_does_not_divide_by_zero(world):
    frame = world["snap"].jobs.first().frames.first()
    bench = _benchmark(world, [frame])
    empty = Snapshot.objects.create(
        dataset_id=42,
        created_by=world["user"],
        taxonomy_version="t",
        guideline_version="g",
        schema_version="test",
        status="pending",
    )
    world["run"].snapshot = empty
    world["run"].save(update_fields=["snapshot"])
    assert benchmark_coverage(world["run"]) == (None, 0, 0, bench.pk)
    coverage = compute_metrics(world["run"], e_min=1)[0]["C-1"]
    assert coverage["status"] == "not_checked"
    assert coverage["value"] is None
