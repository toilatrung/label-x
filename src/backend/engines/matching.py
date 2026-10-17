"""Thư viện matching một-một tất định, dùng chung cho LabelX (Task T-023, Epic E-05).

Quy tắc nghiệp vụ và đặc tả thuật toán theo SRS §3.4 (FR-ENG-06, B-21):
1. Không phụ thuộc ORM, database hay dịch vụ ngoài (pure functions).
2. Tối ưu thứ tự từ điển:
   - Tối đa hoá cardinality (số cặp ghép hợp lệ).
   - Trong các nghiệm cùng cardinality, tối đa hoá tổng IoU.
   - Nếu vẫn hoà, phá hoà tất định theo khóa định danh canonical (SRS §3.4 rule 4:
     ưu tiên IoU cạnh lớn hơn, sau đó ID đối tượng nhỏ hơn).
3. Ghép một-một mặc định KHÔNG phụ thuộc lớp (class-agnostic matching theo SRS §3.4):
   Cặp hình học có IoU >= tau_m nhưng khác lớp vẫn được ghép để downstream engine
   (lỗi sai lớp E2) suy ra và đếm lỗi phân loại. Tùy chọn require_same_class=True
   chỉ dùng khi caller chủ động yêu cầu phân tách lớp trước (ví dụ phát hiện trùng
   lặp trong cùng lớp của E-03).
4. Lọc cạnh có IoU >= tau_m trước khi tối ưu; các cặp trong [tau_amb, tau_m) ghi nhận
   là ambiguous đưa vào bằng chứng (evidence).
5. Đối tượng bị bỏ qua (ignored=True) không tham gia matching và không sinh ambiguous pair.
6. Bảo đảm tính bất biến hoán vị (permutation invariance): đảo thứ tự phần tử đầu vào
   ở bên trái, bên phải hay cả hai phía luôn cho kết quả hoàn toàn đồng nhất.
7. Động hóa hệ số mục tiêu Kuhn-Munkres theo N (dynamic radix scaling) loại bỏ magic
   constant và bảo đảm chặt chẽ thứ tự ưu tiên từ điển với mọi N.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

ALGORITHM_VERSION: str = "1.0.0"
DEFAULT_TAU_M: float = 0.5
DEFAULT_TAU_AMB: float = 0.3


@dataclass(frozen=True)
class BoundingBox:
    """Biểu diễn một bounding box 2D chuẩn hóa cho matching.

    Toạ độ (x1, y1, x2, y2) theo quy ước toạ độ ảnh (gốc trên-trái):
    x1 <= x2 và y1 <= y2.
    """

    id: str
    label: str
    x1: float
    y1: float
    x2: float
    y2: float
    ignored: bool = False
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError(f"id phải là chuỗi không rỗng, nhận được: {self.id!r}")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError(f"label phải là chuỗi không rỗng, nhận được: {self.label!r}")

        for name, val in (("x1", self.x1), ("y1", self.y1), ("x2", self.x2), ("y2", self.y2)):
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError(f"Toạ độ {name} phải là số thực hữu hạn, nhận được: {val!r}")

        if self.x1 > self.x2:
            raise ValueError(f"Toạ độ không hợp lệ: x1 ({self.x1}) > x2 ({self.x2})")
        if self.y1 > self.y2:
            raise ValueError(f"Toạ độ không hợp lệ: y1 ({self.y1}) > y2 ({self.y2})")

        if self.score is not None:
            if not isinstance(self.score, (int, float)) or not math.isfinite(self.score):
                raise ValueError(f"score phải là số thực hữu hạn, nhận được: {self.score!r}")
            if self.score < 0.0:
                raise ValueError(f"score không được âm, nhận được: {self.score!r}")

    @property
    def area(self) -> float:
        """Diện tích của bounding box."""
        return (self.x2 - self.x1) * (self.y2 - self.y1)


def compute_iou(box1: BoundingBox, box2: BoundingBox) -> float:
    """Tính Intersection over Union (IoU) giữa hai bounding box.

    Làm tròn 6 chữ số thập phân (theo DEC-007) để bảo đảm tính ổn định số học.
    """
    ix1 = max(box1.x1, box2.x1)
    iy1 = max(box1.y1, box2.y1)
    ix2 = min(box1.x2, box2.x2)
    iy2 = min(box1.y2, box2.y2)

    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    intersection = iw * ih

    union = box1.area + box2.area - intersection
    if union <= 0.0:
        return 0.0

    iou = intersection / union
    return round(iou, 6)


@dataclass(frozen=True)
class MatchPair:
    """Một cặp ghép một-một thành công."""

    left_id: str
    right_id: str
    iou: float
    is_ambiguous: bool = False


@dataclass(frozen=True)
class AmbiguousPair:
    """Cặp nghi vấn (IoU trong khoảng [tau_amb, tau_m))."""

    left_id: str
    right_id: str
    iou: float


@dataclass(frozen=True)
class MatchingResult:
    """Kết quả matching một-một tất định."""

    matches: list[MatchPair]
    unmatched_left: list[str]
    unmatched_right: list[str]
    ambiguous_pairs: list[AmbiguousPair]
    ignored_left: list[str] = field(default_factory=list)
    ignored_right: list[str] = field(default_factory=list)
    algorithm_version: str = ALGORITHM_VERSION

    @property
    def cardinality(self) -> int:
        """Số cặp ghép thành công."""
        return len(self.matches)

    @property
    def total_iou(self) -> float:
        """Tổng IoU của các cặp ghép, làm tròn 6 chữ số thập phân."""
        return round(sum(m.iou for m in self.matches), 6)

    @property
    def ambiguous(self) -> bool:
        """Cờ ambiguous: True nếu tồn tại ít nhất một cặp trong [tau_amb, tau_m)."""
        return len(self.ambiguous_pairs) > 0

    def to_dict(self) -> dict[str, Any]:
        """Chuyển thành dictionary thuần có thể serialize JSON."""
        return {
            "matches": [
                {
                    "left_id": m.left_id,
                    "right_id": m.right_id,
                    "iou": m.iou,
                    "is_ambiguous": m.is_ambiguous,
                }
                for m in self.matches
            ],
            "unmatched_left": list(self.unmatched_left),
            "unmatched_right": list(self.unmatched_right),
            "ambiguous_pairs": [
                {"left_id": a.left_id, "right_id": a.right_id, "iou": a.iou}
                for a in self.ambiguous_pairs
            ],
            "ignored_left": list(self.ignored_left),
            "ignored_right": list(self.ignored_right),
            "cardinality": self.cardinality,
            "total_iou": self.total_iou,
            "ambiguous": self.ambiguous,
            "algorithm_version": self.algorithm_version,
        }


def _solve_kuhn_munkres(
    left_n: int, right_n: int, edges: dict[tuple[int, int], float]
) -> list[tuple[int, int, float]]:
    """Giải bài toán gán cực đại trọng số 2 phía (Maximum Weight Bipartite Matching).

    Sử dụng thuật toán Kuhn-Munkres (Hungarian algorithm) với số nguyên lớn
    chính xác tuyệt đối (arbitrary precision integer arithmetic) và cơ chế
    mã hóa cơ số động (dynamic radix encoding) để bảo đảm thứ tự tối ưu từ điển
    cho mọi kích thước N:

    1. Cấu trúc tầng mục tiêu (Tiered Objective):
       - Tier 1: Cardinality (số cặp ghép hợp lệ k).
       - Tier 2: Tổng IoU (độ chính xác micro-precision: 10^-6).
       - Tier 3: Canonical tie-break thứ tự từ điển theo từng hàng:
         + Ưu tiên cạnh có IoU lớn hơn.
         + Nếu bằng IoU, ưu tiên đỉnh phải có chỉ số j nhỏ hơn (ID canonical nhỏ hơn).
         + Trọng số tie-break được mã hóa cơ số R: TIE_BONUS(i, j) = V(i, j) * R^(N - 1 - i).

    2. Bất đẳng thức bảo đảm thứ tự tuyệt đối:
       - Với V(i, j) = iou_int * (N + 1) + (N - j):
         Do 0 <= iou_int <= 10^6 và 0 <= j <= N - 1 (nên 1 <= N - j <= N), ta có:
         0 < V(i, j) <= 10^6 * (N + 1) + N < R = 10^6 * (N + 1) + N + 1.
       - Tổng tie-break lớn nhất của mọi bộ ghép size k <= N là:
         MAX_TIE_SUM = sum_{i=0}^{N-1} (R - 1) * R^(N - 1 - i) = R^N - 1.
       - Đặt IOU_SCALE = R^N:
         Mọi chênh lệch tổng IoU nhỏ nhất (1 đơn vị integer = 10^-6) đóng góp 1 * IOU_SCALE = R^N
         > MAX_TIE_SUM = R^N - 1. Do đó tổng IoU luôn thắng toàn bộ tie-break kết hợp.
       - Đặt CARD_BONUS = (N * 10^6 + 2) * IOU_SCALE:
         Thêm 1 cặp ghép (+1 cardinality) đóng góp CARD_BONUS. Giá trị cực đại của tổng IoU
         kèm tie-break của nghiệm size k là <= (N * 10^6) * IOU_SCALE + (R^N - 1)
         = (N * 10^6 + 1) * IOU_SCALE - 1 < CARD_BONUS.
         Do đó cardinality luôn thắng mọi chênh lệch tổng IoU và tie-break với mọi N >= 1.
    """
    N = max(left_n, right_n)
    if N == 0 or not edges:
        return []

    MV = 10**6 * (N + 1) + N + 1
    R = MV
    IOU_SCALE = R**N
    CARD_BONUS = (N * 10**6 + 2) * IOU_SCALE
    INF = 10 * CARD_BONUS

    cost_matrix = [[2 * CARD_BONUS for _ in range(N)] for _ in range(N)]
    for (i, j), iou in edges.items():
        iou_int = int(round(iou * 10**6))
        v_ij = iou_int * (N + 1) + (N - j)
        tie_bonus = v_ij * (R ** (N - 1 - i))
        w_ij = CARD_BONUS + iou_int * IOU_SCALE + tie_bonus
        cost_matrix[i][j] = 2 * CARD_BONUS - w_ij

    # Thuật toán Kuhn-Munkres O(N^3) với thế đối ngẫu u, v
    u = [0] * (N + 1)
    v = [0] * (N + 1)
    p = [0] * (N + 1)
    way = [0] * (N + 1)

    for i in range(1, N + 1):
        p[0] = i
        minv = [INF] * (N + 1)
        used = [False] * (N + 1)
        j0 = 0
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = 0
            for j in range(1, N + 1):
                if not used[j]:
                    cur = cost_matrix[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(0, N + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    ans = [-1] * N
    for j in range(1, N + 1):
        if p[j] != 0:
            ans[p[j] - 1] = j - 1

    matches: list[tuple[int, int, float]] = []
    for i in range(left_n):
        j = ans[i]
        if j < right_n and (i, j) in edges:
            matches.append((i, j, edges[(i, j)]))

    return sorted(matches, key=lambda m: (m[0], m[1]))


def match_one_to_one(
    left: Sequence[BoundingBox],
    right: Sequence[BoundingBox],
    *,
    tau_m: float = DEFAULT_TAU_M,
    tau_amb: float = DEFAULT_TAU_AMB,
    require_same_class: bool = False,
) -> MatchingResult:
    """Thực hiện ghép một-một tất định giữa hai tập bounding box.

    Tham số:
    - left: danh sách BoundingBox phía trái (ví dụ GT hoặc reference).
    - right: danh sách BoundingBox phía phải (ví dụ annotation hoặc detection).
    - tau_m: ngưỡng IoU tối thiểu để tạo cạnh ghép hợp lệ (mặc định 0.5).
    - tau_amb: ngưỡng IoU dưới để xác định cặp ambiguous trong [tau_amb, tau_m) (mặc định 0.3).
    - require_same_class: nếu False (mặc định theo SRS §3.4), ghép hình học không phụ thuộc
      lớp để phục vụ phát hiện lỗi sai lớp (E2). Nếu True (opt-in tường minh), chỉ ghép các
      box có cùng label (dành riêng cho kiểm tra trùng lặp trong cùng lớp của E-03).
    """
    if not (0.0 <= tau_m <= 1.0) or not math.isfinite(tau_m):
        raise ValueError(f"Ngưỡng tau_m phải nằm trong khoảng [0.0, 1.0], nhận: {tau_m}")
    if not (0.0 <= tau_amb <= 1.0) or not math.isfinite(tau_amb):
        raise ValueError(f"Ngưỡng tau_amb phải nằm trong khoảng [0.0, 1.0], nhận: {tau_amb}")
    if tau_amb > tau_m:
        raise ValueError(f"tau_amb ({tau_amb}) không được lớn hơn tau_m ({tau_m})")

    # Kiểm tra ID trùng lặp
    left_seen: set[str] = set()
    for item in left:
        if item.id in left_seen:
            raise ValueError(f"Phát hiện ID trùng lặp ở tập bên trái: {item.id!r}")
        left_seen.add(item.id)

    right_seen: set[str] = set()
    for item in right:
        if item.id in right_seen:
            raise ValueError(f"Phát hiện ID trùng lặp ở tập bên phải: {item.id!r}")
        right_seen.add(item.id)

    # Sắp xếp canonical theo ID để bảo đảm tuyệt đối tính bất biến hoán vị
    sorted_left = sorted(left, key=lambda b: b.id)
    sorted_right = sorted(right, key=lambda b: b.id)

    # Tách các item bị bỏ qua (ignored)
    active_left = [b for b in sorted_left if not b.ignored]
    ignored_left = [b.id for b in sorted_left if b.ignored]

    active_right = [b for b in sorted_right if not b.ignored]
    ignored_right = [b.id for b in sorted_right if b.ignored]

    # Nếu một trong hai phía không còn phần tử active
    if not active_left or not active_right:
        return MatchingResult(
            matches=[],
            unmatched_left=[b.id for b in active_left],
            unmatched_right=[b.id for b in active_right],
            ambiguous_pairs=[],
            ignored_left=ignored_left,
            ignored_right=ignored_right,
            algorithm_version=ALGORITHM_VERSION,
        )

    edges: dict[tuple[int, int], float] = {}
    ambiguous_pairs: list[AmbiguousPair] = []

    tau_m_round = round(tau_m, 6)
    tau_amb_round = round(tau_amb, 6)

    for i, u in enumerate(active_left):
        for j, v in enumerate(active_right):
            if require_same_class and u.label != v.label:
                continue

            iou = compute_iou(u, v)
            if iou >= tau_m_round:
                edges[(i, j)] = iou
            elif tau_amb_round <= iou < tau_m_round:
                ambiguous_pairs.append(AmbiguousPair(left_id=u.id, right_id=v.id, iou=iou))

    raw_matches = _solve_kuhn_munkres(len(active_left), len(active_right), edges)

    matched_left_indices = {i for i, _, _ in raw_matches}
    matched_right_indices = {j for _, j, _ in raw_matches}

    matches: list[MatchPair] = [
        MatchPair(
            left_id=active_left[i].id,
            right_id=active_right[j].id,
            iou=iou,
            is_ambiguous=False,
        )
        for i, j, iou in raw_matches
    ]
    matches.sort(key=lambda m: (m.left_id, m.right_id))

    unmatched_left = [
        active_left[i].id for i in range(len(active_left)) if i not in matched_left_indices
    ]
    unmatched_right = [
        active_right[j].id for j in range(len(active_right)) if j not in matched_right_indices
    ]

    ambiguous_pairs.sort(key=lambda a: (a.left_id, a.right_id))

    return MatchingResult(
        matches=matches,
        unmatched_left=unmatched_left,
        unmatched_right=unmatched_right,
        ambiguous_pairs=ambiguous_pairs,
        ignored_left=ignored_left,
        ignored_right=ignored_right,
        algorithm_version=ALGORITHM_VERSION,
    )
