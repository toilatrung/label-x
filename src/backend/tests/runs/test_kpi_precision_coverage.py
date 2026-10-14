"""BLOCKER-034 B-5 (DEC-023): P-1 Precision của candidate và C-1 Benchmark coverage."""

import pytest

from calibration.models import Benchmark, BenchmarkFrame, BenchmarkStatus
from review.models import Issue
from runs.kpi import benchmark_coverage, candidate_precision, compute_metrics
from tests.runs.test_summary_api import (  # noqa: F401  (fixture world tái sử dụng)
    add_reviews,
    candidate,
    snapshot,
    world,
)

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
    _issue(other, geo, "rejected")
    _issue(other, geo2, "escalated")  # chưa có quyết định
    _issue(other, geo2, "pending_review")
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
