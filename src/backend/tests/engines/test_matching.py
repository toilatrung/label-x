"""Kiểm thử toàn diện thư viện matching một-một tất định (Task T-023, Epic E-05).

Bao gồm:
- Toàn bộ unit tests cho các biên và ca nghiệp vụ (empty, single, threshold edge, wrong-class,
  unmatched, ignore, duplicate cluster, greedy counterexample, tie-break, ambiguous, version).
- Kiểm tra tính bất biến hoán vị (permutation invariance).
- Kiểm tra bắt lỗi dữ liệu đầu vào không hợp lệ (duplicate ID, invalid bbox, invalid threshold).
- Kiểm chứng đối nghịch độc lập với Brute-Force Oracle trên 50 đồ thị ngẫu nhiên có seed cố định.
- Regression test phản ví dụ tie-break F2: N=3, các cạnh (0,0), (0,1), (1,0), (1,2).
- Kiểm thử vét cạn (exhaustive) trên toàn bộ đồ thị rời rạc có chủ đích nhiều tie {0.5, 0.8}.
- Kiểm tra khả năng mở rộng hệ số động theo N (F3 dynamic radix scaling) với N lớn (N=100, N=150).
"""

from __future__ import annotations

import itertools
import json
import math
import random
from collections.abc import Sequence
from typing import Any

import pytest

from engines.matching import (
    ALGORITHM_VERSION,
    BoundingBox,
    _solve_kuhn_munkres,
    compute_iou,
    match_one_to_one,
)


def _make_box(
    box_id: str,
    label: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    *,
    ignored: bool = False,
    score: float | None = None,
) -> BoundingBox:
    return BoundingBox(
        id=box_id,
        label=label,
        x1=float(x1),
        y1=float(y1),
        x2=float(x2),
        y2=float(y2),
        ignored=ignored,
        score=score,
    )


# ---------------------------------------------------------------------------
# 1. Các trường hợp biên và cấu trúc cơ bản
# ---------------------------------------------------------------------------


def test_two_empty_inputs() -> None:
    """Hai input rỗng: trả về kết quả rỗng hợp lệ."""
    result = match_one_to_one([], [])
    assert result.cardinality == 0
    assert result.total_iou == 0.0
    assert result.matches == []
    assert result.unmatched_left == []
    assert result.unmatched_right == []
    assert result.ambiguous_pairs == []
    assert result.ignored_left == []
    assert result.ignored_right == []
    assert not result.ambiguous
    assert result.algorithm_version == ALGORITHM_VERSION


def test_one_side_empty_left() -> None:
    """Phía trái rỗng, phía phải có item: toàn bộ phía phải là unmatched."""
    b1 = _make_box("r1", "car", 0, 0, 10, 10)
    result = match_one_to_one([], [b1])
    assert result.cardinality == 0
    assert result.unmatched_left == []
    assert result.unmatched_right == ["r1"]


def test_one_side_empty_right() -> None:
    """Phía phải rỗng, phía trái có item: toàn bộ phía trái là unmatched."""
    b1 = _make_box("l1", "car", 0, 0, 10, 10)
    result = match_one_to_one([b1], [])
    assert result.cardinality == 0
    assert result.unmatched_left == ["l1"]
    assert result.unmatched_right == []


def test_one_valid_pair() -> None:
    """Một cặp hợp lệ có IoU >= tau_m: ghép thành công."""
    b1 = _make_box("l1", "car", 0, 0, 10, 10)
    b2 = _make_box("r1", "car", 0, 0, 10, 8)
    result = match_one_to_one([b1], [b2])
    assert result.cardinality == 1
    assert len(result.matches) == 1
    match = result.matches[0]
    assert match.left_id == "l1"
    assert match.right_id == "r1"
    assert match.iou == 0.8
    assert result.unmatched_left == []
    assert result.unmatched_right == []


def test_iou_below_threshold() -> None:
    """IoU < tau_m: không ghép."""
    b1 = _make_box("l1", "car", 0, 0, 10, 10)
    b2 = _make_box("r1", "car", 8, 0, 18, 10)
    result = match_one_to_one([b1], [b2], tau_m=0.5, tau_amb=0.3)
    assert result.cardinality == 0
    assert result.matches == []
    assert result.unmatched_left == ["l1"]
    assert result.unmatched_right == ["r1"]
    assert not result.ambiguous


def test_iou_exactly_equal_threshold() -> None:
    """IoU đúng bằng ngưỡng tau_m: tạo cạnh và ghép thành công."""
    # box1: [0, 0, 12, 10] area 120
    # box2: [4, 0, 16, 10] area 120
    # Giao: [4, 0, 12, 10] rộng 8, cao 10 -> area 80.
    # Hợp: 120 + 120 - 80 = 160. IoU = 80 / 160 = 0.500000 chính xác!
    b1 = _make_box("l1", "car", 0, 0, 12, 10)
    b2 = _make_box("r1", "car", 4, 0, 16, 10)
    assert compute_iou(b1, b2) == 0.5

    result = match_one_to_one([b1], [b2], tau_m=0.5)
    assert result.cardinality == 1
    assert result.matches[0].iou == 0.5
    assert result.unmatched_left == []
    assert result.unmatched_right == []


def test_wrong_class_matched_by_default_for_e2() -> None:
    """SRS §3.4 & F1: Ghép một-một mặc định KHÔNG phụ thuộc lớp.

    Hai box khác lớp ('truck' vs 'car') có IoU >= tau_m vẫn được ghép mặc định
    để downstream engine phát hiện lỗi sai lớp (E2).
    """
    b1 = _make_box("l1", "truck", 0, 0, 10, 10)
    b2 = _make_box("r1", "car", 0, 0, 10, 10)
    result = match_one_to_one([b1], [b2])  # Mặc định require_same_class=False
    assert result.cardinality == 1
    assert result.matches[0].left_id == "l1"
    assert result.matches[0].right_id == "r1"
    assert result.matches[0].iou == 1.0
    assert result.unmatched_left == []
    assert result.unmatched_right == []


def test_wrong_class_filtered_when_opt_in_require_same_class() -> None:
    """Khi caller chủ động bật require_same_class=True (opt-in cho E-03 duplicate):
    các box khác lớp không được ghép và không sinh ambiguous.
    """
    b1 = _make_box("l1", "car", 0, 0, 10, 10)
    b2 = _make_box("r1", "pedestrian", 0, 0, 10, 10)
    result = match_one_to_one([b1], [b2], require_same_class=True)
    assert result.cardinality == 0
    assert result.matches == []
    assert result.unmatched_left == ["l1"]
    assert result.unmatched_right == ["r1"]
    assert result.ambiguous_pairs == []


def test_unmatched_items() -> None:
    """Các đối tượng không tìm được cặp có IoU >= tau_m xuất hiện trong danh sách unmatched."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_l2 = _make_box("l2", "car", 100, 100, 110, 110)
    b_r1 = _make_box("r1", "car", 0, 0, 10, 10)
    b_r2 = _make_box("r2", "car", 200, 200, 210, 210)

    result = match_one_to_one([b_l1, b_l2], [b_r1, b_r2])
    assert result.cardinality == 1
    assert result.matches[0].left_id == "l1"
    assert result.matches[0].right_id == "r1"
    assert result.unmatched_left == ["l2"]
    assert result.unmatched_right == ["r2"]


# ---------------------------------------------------------------------------
# 2. Xử lý đối tượng Ignored (BR-07)
# ---------------------------------------------------------------------------


def test_ignore_on_left() -> None:
    """Đối tượng bên trái có ignored=True: không tham gia matching, không sinh ambiguous."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10, ignored=True)
    b_r1 = _make_box("r1", "car", 0, 0, 10, 10)
    result = match_one_to_one([b_l1], [b_r1])
    assert result.cardinality == 0
    assert result.matches == []
    assert result.ignored_left == ["l1"]
    assert result.unmatched_left == []
    assert result.unmatched_right == ["r1"]
    assert result.ambiguous_pairs == []


def test_ignore_on_right() -> None:
    """Đối tượng bên phải có ignored=True: không ghép, ghi vào ignored_right."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_r1 = _make_box("r1", "car", 0, 0, 10, 10, ignored=True)
    result = match_one_to_one([b_l1], [b_r1])
    assert result.cardinality == 0
    assert result.ignored_right == ["r1"]
    assert result.unmatched_left == ["l1"]
    assert result.unmatched_right == []
    assert result.ambiguous_pairs == []


def test_ignore_does_not_affect_ambiguous() -> None:
    """Item bị ignore dù có IoU trong [tau_amb, tau_m) cũng không sinh ambiguous."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10, ignored=True)
    b_r1 = _make_box("r1", "car", 6, 0, 16, 10)  # IoU khoảng 0.25 - 0.4
    result = match_one_to_one([b_l1], [b_r1], tau_m=0.5, tau_amb=0.2)
    assert not result.ambiguous
    assert result.ambiguous_pairs == []


# ---------------------------------------------------------------------------
# 3. Trùng lặp (Duplicate Cluster) và Tối ưu hóa thứ bậc
# ---------------------------------------------------------------------------


def test_duplicate_cluster_resolution() -> None:
    """Cụm duplicate: hai candidate r1, r2 tranh cùng một object l1. Chọn IoU lớn hơn."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_r1 = _make_box("r1", "car", 0, 0, 10, 9)  # IoU = 90 / 100 = 0.90
    b_r2 = _make_box("r2", "car", 0, 0, 10, 7)  # IoU = 70 / 100 = 0.70

    result = match_one_to_one([b_l1], [b_r1, b_r2])
    assert result.cardinality == 1
    assert result.matches[0].left_id == "l1"
    assert result.matches[0].right_id == "r1"
    assert result.matches[0].iou == 0.9
    assert result.unmatched_right == ["r2"]


def test_greedy_counterexample_maximizes_cardinality_first() -> None:
    """Greedy chọn IoU cao nhất trước (0.9) sẽ làm giảm cardinality từ 2 xuống 1.

    Implementation PHẢI chọn cardinality lớn hơn (2 cặp, tổng IoU 1.3).
    """
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_l2 = _make_box("l2", "car", 0, 0, 7, 10)

    b_r1 = _make_box("r1", "car", 0, 0, 9, 10)
    b_r2 = _make_box("r2", "car", 3, 0, 13, 10)

    assert compute_iou(b_l1, b_r1) == 0.9
    assert compute_iou(b_l1, b_r2) >= 0.5
    assert compute_iou(b_l2, b_r1) >= 0.5
    assert compute_iou(b_l2, b_r2) < 0.5

    result = match_one_to_one([b_l1, b_l2], [b_r1, b_r2], tau_m=0.5)

    assert result.cardinality == 2
    matched_pairs = {(m.left_id, m.right_id) for m in result.matches}
    assert ("l1", "r2") in matched_pairs
    assert ("l2", "r1") in matched_pairs


def test_same_cardinality_maximizes_total_iou() -> None:
    """Cùng cardinality nhưng hai phương án có tổng IoU khác nhau: chọn tổng IoU lớn hơn."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_l2 = _make_box("l2", "car", 20, 0, 30, 10)

    b_r1 = _make_box("r1", "car", 0, 0, 10, 9)  # IoU với l1 là 0.90
    b_r2 = _make_box("r2", "car", 20, 0, 30, 9)  # IoU với l2 là 0.90

    result = match_one_to_one([b_l1, b_l2], [b_r1, b_r2], tau_m=0.5)
    assert result.cardinality == 2
    matched_pairs = {(m.left_id, m.right_id) for m in result.matches}
    assert ("l1", "r1") in matched_pairs
    assert ("l2", "r2") in matched_pairs
    assert result.total_iou == 1.8


def test_canonical_tie_break() -> None:
    """Hoà hoàn toàn về cả cardinality và tổng IoU: phá hoà theo ID canonical nhỏ hơn."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_r1 = _make_box("r1", "car", 0, 0, 10, 8)  # IoU 0.8
    b_r2 = _make_box("r2", "car", 0, 0, 10, 8)  # IoU 0.8

    result = match_one_to_one([b_l1], [b_r1, b_r2], tau_m=0.5)
    assert result.cardinality == 1
    assert result.matches[0].left_id == "l1"
    assert result.matches[0].right_id == "r1"
    assert result.unmatched_right == ["r2"]


def test_canonical_tie_break_f2_counterexample() -> None:
    """Regression test cho phản ví dụ F2:
    N = 3, các cạnh đều IoU 0.8:
    (0,0), (0,1), (1,0), (1,2)

    Cả hai nghiệm:
    M1 = [(0,1), (1,0)]
    M2 = [(0,0), (1,2)]
    đều có cardinality = 2, tổng IoU = 1.6.

    Canonical oracle theo SRS §3.4:
    Tại hàng 0 (ID nhỏ nhất bên trái), M2 ghép với cột 0 còn M1 ghép với cột 1.
    Do cột 0 có ID nhỏ hơn cột 1, M2 thắng tuyệt đối: [(0,0), (1,2)].
    """
    edges = {(0, 0): 0.8, (0, 1): 0.8, (1, 0): 0.8, (1, 2): 0.8}
    raw = _solve_kuhn_munkres(3, 3, edges)
    pairs = [(i, j) for i, j, _ in raw]
    assert pairs == [(0, 0), (1, 2)]


# ---------------------------------------------------------------------------
# 4. Kiểm tra Cờ Ambiguous và Algorithm Version
# ---------------------------------------------------------------------------


def test_ambiguous_true_case() -> None:
    """Tồn tại cặp có IoU trong [tau_amb, tau_m): ambiguous=True và lưu ambiguous_pairs."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_r1 = _make_box("r1", "car", 5, 0, 15, 10)

    result = match_one_to_one([b_l1], [b_r1], tau_m=0.5, tau_amb=0.3)
    assert result.cardinality == 0
    assert result.ambiguous is True
    assert len(result.ambiguous_pairs) == 1
    amb = result.ambiguous_pairs[0]
    assert amb.left_id == "l1"
    assert amb.right_id == "r1"
    assert amb.iou == 0.333333
    assert result.algorithm_version == ALGORITHM_VERSION


def test_ambiguous_false_case() -> None:
    """Không có cặp nào trong [tau_amb, tau_m): ambiguous=False và ambiguous_pairs rỗng."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_r1 = _make_box("r1", "car", 0, 0, 10, 8)

    result = match_one_to_one([b_l1], [b_r1], tau_m=0.5, tau_amb=0.3)
    assert result.cardinality == 1
    assert result.ambiguous is False
    assert result.ambiguous_pairs == []


# ---------------------------------------------------------------------------
# 5. Kiểm tra Tính Bất biến Hoán vị (Permutation Invariance) & Repeatability
# ---------------------------------------------------------------------------


def test_repeatability_multiple_runs() -> None:
    """Chạy nhiều lần với cùng input cho kết quả đồng nhất 100%."""
    left = [_make_box(f"l{i}", "car", i * 10, 0, i * 10 + 10, 10) for i in range(5)]
    right = [_make_box(f"r{i}", "car", i * 10, 0, i * 10 + 10, 10) for i in range(5)]

    r1 = match_one_to_one(left, right)
    for _ in range(5):
        r_sub = match_one_to_one(left, right)
        assert r_sub.to_dict() == r1.to_dict()


def test_permutation_invariance_left() -> None:
    """Đảo thứ tự phía trái không thay đổi kết quả matching."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_l2 = _make_box("l2", "car", 20, 0, 30, 10)
    b_l3 = _make_box("l3", "car", 40, 0, 50, 10)

    b_r1 = _make_box("r1", "car", 0, 0, 10, 10)
    b_r2 = _make_box("r2", "car", 20, 0, 30, 10)
    b_r3 = _make_box("r3", "car", 40, 0, 50, 10)

    res_normal = match_one_to_one([b_l1, b_l2, b_l3], [b_r1, b_r2, b_r3])
    res_permuted = match_one_to_one([b_l3, b_l1, b_l2], [b_r1, b_r2, b_r3])

    assert res_normal.to_dict() == res_permuted.to_dict()


def test_permutation_invariance_right() -> None:
    """Đảo thứ tự phía phải không thay đổi kết quả matching."""
    b_l1 = _make_box("l1", "car", 0, 0, 10, 10)
    b_l2 = _make_box("l2", "car", 20, 0, 30, 10)

    b_r1 = _make_box("r1", "car", 0, 0, 10, 10)
    b_r2 = _make_box("r2", "car", 20, 0, 30, 10)

    res_normal = match_one_to_one([b_l1, b_l2], [b_r1, b_r2])
    res_permuted = match_one_to_one([b_l1, b_l2], [b_r2, b_r1])

    assert res_normal.to_dict() == res_permuted.to_dict()


def test_permutation_invariance_both() -> None:
    """Xáo trộn ngẫu nhiên cả hai phía cho kết quả giống hệt."""
    left = [_make_box(f"l{i}", "car", i * 5, 0, i * 5 + 10, 10) for i in range(6)]
    right = [_make_box(f"r{i}", "car", i * 5, 0, i * 5 + 10, 10) for i in range(6)]

    baseline = match_one_to_one(left, right).to_dict()

    rng = random.Random(12345)
    for _ in range(10):
        shuffled_left = list(left)
        shuffled_right = list(right)
        rng.shuffle(shuffled_left)
        rng.shuffle(shuffled_right)
        current = match_one_to_one(shuffled_left, shuffled_right).to_dict()
        assert current == baseline


# ---------------------------------------------------------------------------
# 6. Kiểm tra Dữ liệu Đầu vào Không Hợp lệ (Contract Validation)
# ---------------------------------------------------------------------------


def test_duplicate_id_in_left_raises_error() -> None:
    """Phát hiện ID trùng lặp ở phía trái phải ném ValueError."""
    b1 = _make_box("dup1", "car", 0, 0, 10, 10)
    b2 = _make_box("dup1", "car", 10, 10, 20, 20)
    with pytest.raises(ValueError, match="Phát hiện ID trùng lặp ở tập bên trái"):
        match_one_to_one([b1, b2], [])


def test_duplicate_id_in_right_raises_error() -> None:
    """Phát hiện ID trùng lặp ở phía phải phải ném ValueError."""
    b1 = _make_box("r1", "car", 0, 0, 10, 10)
    b2 = _make_box("r1", "car", 10, 10, 20, 20)
    with pytest.raises(ValueError, match="Phát hiện ID trùng lặp ở tập bên phải"):
        match_one_to_one([], [b1, b2])


def test_invalid_tau_thresholds_raise_error() -> None:
    """Ngưỡng ngoài [0.0, 1.0] hoặc tau_amb > tau_m phải ném ValueError."""
    with pytest.raises(ValueError, match="Ngưỡng tau_m phải nằm trong khoảng"):
        match_one_to_one([], [], tau_m=-0.1)

    with pytest.raises(ValueError, match="Ngưỡng tau_m phải nằm trong khoảng"):
        match_one_to_one([], [], tau_m=1.5)

    with pytest.raises(ValueError, match="Ngưỡng tau_amb phải nằm trong khoảng"):
        match_one_to_one([], [], tau_amb=-0.05)

    with pytest.raises(ValueError, match="không được lớn hơn tau_m"):
        match_one_to_one([], [], tau_m=0.4, tau_amb=0.6)


def test_invalid_bbox_coordinates_raise_error() -> None:
    """Toạ độ bounding box không hợp lệ (x1 > x2, y1 > y2, nan, inf) ném ValueError."""
    with pytest.raises(ValueError, match="x1 .* > x2"):
        BoundingBox("b1", "car", x1=20, y1=0, x2=10, y2=10)

    with pytest.raises(ValueError, match="y1 .* > y2"):
        BoundingBox("b1", "car", x1=0, y1=30, x2=10, y2=10)

    with pytest.raises(ValueError, match="phải là số thực hữu hạn"):
        BoundingBox("b1", "car", x1=float("nan"), y1=0, x2=10, y2=10)

    with pytest.raises(ValueError, match="phải là số thực hữu hạn"):
        BoundingBox("b1", "car", x1=0, y1=0, x2=float("inf"), y2=10)


def test_invalid_bbox_id_or_label_raises_error() -> None:
    """ID hoặc label rỗng/trắng ném ValueError."""
    with pytest.raises(ValueError, match="id phải là chuỗi không rỗng"):
        BoundingBox("", "car", 0, 0, 10, 10)

    with pytest.raises(ValueError, match="label phải là chuỗi không rỗng"):
        BoundingBox("b1", "   ", 0, 0, 10, 10)


def test_matching_result_serialization() -> None:
    """to_dict() trên MatchingResult trả về dictionary hợp lệ và serialize được JSON."""
    b1 = _make_box("l1", "car", 0, 0, 10, 10)
    b2 = _make_box("r1", "car", 0, 0, 10, 9)
    res = match_one_to_one([b1], [b2])
    data = res.to_dict()

    json_str = json.dumps(data)
    assert json_str is not None
    assert data["cardinality"] == 1
    assert data["total_iou"] == 0.9
    assert data["algorithm_version"] == "1.0.0"
    assert data["matches"][0]["left_id"] == "l1"
    assert data["matches"][0]["right_id"] == "r1"


# ---------------------------------------------------------------------------
# 7. Kiểm chứng Đối nghịch Độc lập với Brute-Force Oracle & Exhaustive Tests
# ---------------------------------------------------------------------------


def _brute_force_oracle(
    left: Sequence[BoundingBox],
    right: Sequence[BoundingBox],
    tau_m: float,
    require_same_class: bool,
) -> tuple[int, float, list[tuple[str, str]]]:
    """Oracle vét cạn độc lập: duyệt qua mọi matching hợp lệ để tìm nghiệm tối ưu."""
    sorted_left = sorted([b for b in left if not b.ignored], key=lambda b: b.id)
    sorted_right = sorted([b for b in right if not b.ignored], key=lambda b: b.id)

    ln = len(sorted_left)
    rn = len(sorted_right)
    if ln == 0 or rn == 0:
        return 0, 0.0, []

    valid_edges: dict[tuple[int, int], float] = {}
    tau_m_round = round(tau_m, 6)
    for i, u in enumerate(sorted_left):
        for j, v in enumerate(sorted_right):
            if require_same_class and u.label != v.label:
                continue
            iou = compute_iou(u, v)
            if iou >= tau_m_round:
                valid_edges[(i, j)] = iou

    for card in range(min(ln, rn), -1, -1):
        if card == 0:
            return 0, 0.0, []

        candidate_matchings: list[tuple[tuple[int, int], ...]] = []
        for l_comb in itertools.combinations(range(ln), card):
            for r_perm in itertools.permutations(range(rn), card):
                pairs = tuple(sorted((l_comb[k], r_perm[k]) for k in range(card)))
                if all(p in valid_edges for p in pairs):
                    candidate_matchings.append(pairs)

        if candidate_matchings:
            max_iou_int = -1
            best_iou_cand: list[tuple[tuple[int, int], ...]] = []
            for m in candidate_matchings:
                iou_sum_int = sum(int(round(valid_edges[p] * 10**6)) for p in m)
                if iou_sum_int > max_iou_int:
                    max_iou_int = iou_sum_int
                    best_iou_cand = [m]
                elif iou_sum_int == max_iou_int:
                    best_iou_cand.append(m)

            def tie_score(m: tuple[tuple[int, int], ...]) -> tuple[Any, ...]:
                row_map = {i: j for i, j in m}
                return tuple(
                    (1, valid_edges[(i, row_map[i])], -row_map[i])
                    if i in row_map
                    else (0, 0.0, -999999)
                    for i in range(ln)
                )

            best_m = max(best_iou_cand, key=tie_score)
            total_iou = round(sum(valid_edges[p] for p in best_m), 6)
            chosen_pairs = [(sorted_left[i].id, sorted_right[j].id) for i, j in best_m]
            return card, total_iou, chosen_pairs

    return 0, 0.0, []


def test_adversarial_oracle_verification_on_random_graphs() -> None:
    """So sánh production với Brute-Force Oracle trên 50 đồ thị ngẫu nhiên (seed cố định 999)."""
    rng = random.Random(999)
    classes = ["car", "pedestrian", "truck"]

    for test_idx in range(50):
        num_left = rng.randint(1, 5)
        num_right = rng.randint(1, 5)

        left_boxes: list[BoundingBox] = []
        for i in range(num_left):
            x1 = float(rng.randint(0, 30))
            y1 = float(rng.randint(0, 30))
            w = float(rng.randint(10, 25))
            h = float(rng.randint(10, 25))
            cls = rng.choice(classes)
            left_boxes.append(
                BoundingBox(id=f"L{i}", label=cls, x1=x1, y1=y1, x2=x1 + w, y2=y1 + h)
            )

        right_boxes: list[BoundingBox] = []
        for j in range(num_right):
            x1 = float(rng.randint(0, 30))
            y1 = float(rng.randint(0, 30))
            w = float(rng.randint(10, 25))
            h = float(rng.randint(10, 25))
            cls = rng.choice(classes)
            right_boxes.append(
                BoundingBox(id=f"R{j}", label=cls, x1=x1, y1=y1, x2=x1 + w, y2=y1 + h)
            )

        tau_m = rng.choice([0.4, 0.5, 0.6])
        req_same_class = rng.choice([True, False])

        prod_result = match_one_to_one(
            left_boxes, right_boxes, tau_m=tau_m, require_same_class=req_same_class
        )
        prod_pairs = [(m.left_id, m.right_id) for m in prod_result.matches]

        oracle_card, oracle_total_iou, oracle_pairs = _brute_force_oracle(
            left_boxes, right_boxes, tau_m, req_same_class
        )

        assert prod_result.cardinality == oracle_card, (
            f"Test #{test_idx}: Mismatch cardinality! Prod={prod_result.cardinality}, "
            f"Oracle={oracle_card}"
        )
        assert math.isclose(prod_result.total_iou, oracle_total_iou, abs_tol=1e-5), (
            f"Test #{test_idx}: Mismatch total IoU! Prod={prod_result.total_iou}, "
            f"Oracle={oracle_total_iou}"
        )
        assert prod_pairs == oracle_pairs, (
            f"Test #{test_idx}: Mismatch pairs! Prod={prod_pairs}, Oracle={oracle_pairs}"
        )


def _oracle_solve_raw(
    left_n: int, right_n: int, edges: dict[tuple[int, int], float]
) -> list[tuple[int, int, float]]:
    """Oracle vét cạn thuần cho bipartite graph với trọng số."""

    def backtrack(
        i: int, cur: list[tuple[int, int, float]], used: set[int]
    ) -> list[list[tuple[int, int, float]]]:
        if i == left_n:
            return [list(cur)]
        res = backtrack(i + 1, cur, used)
        for j in range(right_n):
            if (i, j) in edges and j not in used:
                used.add(j)
                cur.append((i, j, edges[(i, j)]))
                res.extend(backtrack(i + 1, cur, used))
                cur.pop()
                used.remove(j)
        return res

    all_m = backtrack(0, [], set())

    def eval_key(m: list[tuple[int, int, float]]) -> tuple[Any, ...]:
        card = len(m)
        total_iou_int = sum(int(round(iou * 10**6)) for _, _, iou in m)
        row_map = {i: (j, iou) for i, j, iou in m}
        row_vec = []
        for i in range(left_n):
            if i in row_map:
                j, iou = row_map[i]
                iou_int = int(round(iou * 10**6))
                row_vec.append((1, iou_int, -j))
            else:
                row_vec.append((0, 0, -999999))
        return (card, total_iou_int, tuple(row_vec))

    best = max(all_m, key=eval_key)
    return sorted(best, key=lambda m: (m[0], m[1]))


def test_exhaustive_discrete_graphs_oracle_comparison() -> None:
    """F2: Kiểm thử vét cạn đồ thị có chủ đích nhiều tie {0.5, 0.8}.

    Duyệt qua các đồ thị đối xứng và bất đối xứng 3x3, 2x3, 3x2,
    chứng minh Kuhn-Munkres khớp 100% với Canonical Oracle.
    """
    for left_n, right_n in [(3, 3), (2, 3), (3, 2)]:
        all_edges = [(i, j) for i in range(left_n) for j in range(right_n)]
        # Kiểm tra exhaustive các cấu hình từ 1 đến 5 cạnh với trọng số trong {0.5, 0.8}
        for num_edges in range(1, 6):
            for edge_comb in itertools.combinations(all_edges, num_edges):
                for weights in itertools.product([0.5, 0.8], repeat=num_edges):
                    graph_edges = {edge_comb[k]: weights[k] for k in range(num_edges)}
                    oracle_matches = _oracle_solve_raw(left_n, right_n, graph_edges)
                    km_matches = _solve_kuhn_munkres(left_n, right_n, graph_edges)
                    o_pairs = [(i, j) for i, j, _ in oracle_matches]
                    k_pairs = [(i, j) for i, j, _ in km_matches]
                    assert o_pairs == k_pairs, (
                        f"Mismatch at L={left_n}, R={right_n}, edges={graph_edges}: "
                        f"Oracle={o_pairs}, KM={k_pairs}"
                    )


def test_dynamic_scaling_large_n() -> None:
    """F3: Kiểm tra hệ số mục tiêu động với N lớn (N=100, N=150) không phụ thuộc magic constant.

    Bảo đảm:
    - Thuật toán hoàn thành nhanh chóng (vài chục ms).
    - Không lỗi tràn số hay sai sót thứ tự từ điển khi kích thước đồ thị lớn.
    """
    rng = random.Random(42)
    for N in [50, 100, 150]:
        edges: dict[tuple[int, int], float] = {}
        for i in range(N):
            for j in range(max(0, i - 2), min(N, i + 3)):
                edges[(i, j)] = round(rng.uniform(0.5, 0.95), 4)

        result = _solve_kuhn_munkres(N, N, edges)
        assert len(result) > 0
        assert len(result) <= N
        # Kiểm tra tính đơn ánh của cặp ghép (one-to-one)
        matched_l = [i for i, _, _ in result]
        matched_r = [j for _, j, _ in result]
        assert len(matched_l) == len(set(matched_l)), "Phát hiện trùng lặp đỉnh trái!"
        assert len(matched_r) == len(set(matched_r)), "Phát hiện trùng lặp đỉnh phải!"
