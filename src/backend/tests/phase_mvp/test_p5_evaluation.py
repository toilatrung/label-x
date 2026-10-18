"""Issue #396 supplemental evidence; no fabricated evaluation approval/bindings."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import connection

from accounts.models import Role
from effort.models import EffortEvent
from engines.interface import EngineConfig, EngineInput, EngineUnitRef, FrameKey
from engines.metric import count_detections, run_metric_engine
from ranking import recall_at_k
from tests.effort.test_effort_events import _client, _frame, _payload, _user


def test_missing_reference_is_not_checked_and_empty_truth_is_not_perfect():
    inp = EngineInput(
        "missing-ref",
        1,
        2,
        "metric",
        "1.0.0",
        EngineConfig("metric", "v1", True, {}),
        42,
        0,
        (EngineUnitRef("frame", FrameKey(9, 0)),),
    )
    output = run_metric_engine(inp)
    assert output.candidates == ()
    (result,) = output.unit_results
    assert result.unit == inp.units[0]
    assert result.outcome == "not_checked"
    assert result.not_checked_reason == "no_reference"
    # No empty-ground-truth result can be interpreted as a 0% or perfect score.
    assert count_detections([], [], tau_m=0.5) == {}


@pytest.mark.django_db(transaction=True)
def test_effort_review_and_recheck_timeline_keeps_idle_provenance_and_retry(settings):
    """A synthetic pilot fixture; not an approval of held-out acceptance policy."""
    assert connection.vendor == "postgresql"
    settings.EFFORT_IDLE_POLICY = {
        "source": "test-fixture/issue396",
        "decision_status": "approved_for_pilot",
        "t_idle_seconds": 120,
        "version": "issue396-fixture-v1",
    }
    reviewer = _user("issue396-reviewer", Role.REVIEWER, 42)
    frame = _frame(reviewer)
    api = _client(reviewer)
    start = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)
    review = _payload(
        frame.pk,
        started_at=start.isoformat(),
        ended_at=(start + timedelta(seconds=600)).isoformat(),
        policy_version="issue396-fixture-v1",
        gaps=[
            {
                "started_at": (start + timedelta(seconds=100)).isoformat(),
                "ended_at": (start + timedelta(seconds=300)).isoformat(),
                "reason": "idle",
            },
            {
                "started_at": (start + timedelta(seconds=200)).isoformat(),
                "ended_at": (start + timedelta(seconds=250)).isoformat(),
                "reason": "hidden",
            },
        ],
    )
    recheck = _payload(
        frame.pk,
        activity="recheck_verify",
        started_at=(start + timedelta(seconds=600)).isoformat(),
        ended_at=(start + timedelta(seconds=660)).isoformat(),
        policy_version="issue396-fixture-v1",
    )
    for payload in (review, recheck):
        accepted = api.post("/api/effort-events/", payload, format="json")
        assert accepted.status_code == 202, accepted.data
        assert accepted.data == {"accepted": 1, "duplicates": 0}
        retry = api.post("/api/effort-events/", payload, format="json")
        assert retry.status_code == 202
        assert retry.data == {"accepted": 0, "duplicates": 1}
    rows = EffortEvent.objects.filter(frame=frame).order_by("started_at")
    assert list(rows.values_list("activity", "active_ms")) == [
        ("review_issue", 400_000),
        ("recheck_verify", 60_000),
    ]
    assert sum(event.active_ms for event in rows) == 460_000
    assert all(event.config_snapshot["version"] == "issue396-fixture-v1" for event in rows)
    assert all(event.config_source == "test-fixture/issue396" for event in rows)


def test_kpi01_recall_at_k_counts_errors_not_frames_with_ceil_and_min_sample():
    """SRS phụ lục B: N=10, |E|=12, ⌈0,2×10⌉=2 → Recall@20% = (4+3)/12; frame recall = 2/6."""
    ranking = ["f07", "f02", "f09", "f01", "f05", "f03", "f10", "f04", "f06", "f08"]
    errors = {"f07": 4, "f02": 3, "f09": 1, "f01": 0, "f05": 2, "f10": 1, "f06": 1}
    result = recall_at_k(ranking, errors, e_min=12)
    assert (result.frames, result.top_frames) == (10, 2)
    assert (result.errors_total, result.errors_in_top) == (12, 7)
    assert result.status == "computed"
    assert result.value == pytest.approx(7 / 12)
    assert round(result.value * 100, 1) == 58.3
    assert (result.frames_with_errors, result.frames_with_errors_in_top) == (6, 2)
    assert result.frame_recall == pytest.approx(2 / 6)
    assert result.value != result.frame_recall  # đếm lỗi, không phải frame có lỗi

    # Mẫu lỗi dưới E_min (kể cả đúng ví dụ phụ lục B với E_min thực tế) là "không đủ mẫu".
    for e_min in (13, 30):
        small = recall_at_k(ranking, errors, e_min=e_min)
        assert small.status == "insufficient_sample"
        assert small.value is None and small.frame_recall is None
        assert (small.errors_total, small.errors_in_top) == (12, 7)  # vẫn ghi mẫu số, không số KPI

    # Không có lỗi nào: không phải 0% cũng không phải 100%, và không chia cho 0.
    none = recall_at_k(ranking, {}, e_min=1)
    assert none.status == "insufficient_sample" and none.value is None and none.errors_total == 0
    assert recall_at_k(ranking, {"f01": 0}, e_min=1).value is None

    # ⌈kN⌉ dùng Decimal: float 0.2*15 = 3.0000000000000004 sẽ cho 4 frame đầu.
    fifteen = [f"g{i:02d}" for i in range(15)]
    assert recall_at_k(fifteen, {"g02": 1, "g03": 1}, e_min=1).top_frames == 3
    assert recall_at_k(fifteen, {"g02": 1, "g03": 1}, e_min=1).value == pytest.approx(0.5)
    assert recall_at_k([*ranking, "f11"], {"f07": 1}, e_min=1).top_frames == 3  # ⌈2,2⌉
    assert recall_at_k(ranking, errors, k=Decimal("1"), e_min=12).value == 1.0
    assert recall_at_k(ranking, errors, k=Decimal("0.05"), e_min=12).top_frames == 1  # ⌈0,5⌉

    # Đầu vào mơ hồ bị từ chối thay vì âm thầm bỏ lỗi hoặc đổi mẫu số.
    for bad_ranking, bad_errors in [
        (["a", "a"], {"a": 1}),
        (["a", "b"], {"c": 1}),
        (["a", "b"], {"a": -1}),
        (["a", "b"], {"a": True}),
    ]:
        with pytest.raises(ValueError):
            recall_at_k(bad_ranking, bad_errors, e_min=1)
    for bad_k in (Decimal("0"), Decimal("1.01"), Decimal("NaN")):
        with pytest.raises(ValueError):
            recall_at_k(ranking, errors, k=bad_k, e_min=1)
    with pytest.raises(ValueError):
        recall_at_k(ranking, errors, e_min=0)
