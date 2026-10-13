"""Pure detector matching; model scores are evidence, never calibrated quality."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from engines.interface import Anchor, Candidate, EngineDescriptor, FrameKey, ObjectRef

DETECTOR_DESCRIPTOR = EngineDescriptor("detector", "1.0.0", "frame", True, True, False, "1.0.0")
MATCH_POLICY = "detector-matching-v1"


def box(value: Any, width: int, height: int) -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("detector bbox must contain four coordinates")
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in value
    ):
        raise ValueError("detector bbox must be finite")
    x1, y1, x2, y2 = map(float, value)
    if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
        raise ValueError("detector bbox outside frame or degenerate")
    return x1, y1, x2, y2


def probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("detector probability must be numeric")
    number = float(value)
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise ValueError("detector probability must be in [0,1]")
    return number


def iou(a: Sequence[float], b: Sequence[float]) -> float:
    overlap = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1])
    )
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - overlap
    return overlap / union if union > 0 else 0.0


def assignment(weights: list[list[float]]) -> dict[int, int]:
    """Maximum-weight one-to-one assignment (Hungarian, dummy columns permit unmatched)."""
    n = len(weights)
    if not n:
        return {}
    columns = len(weights[0])
    m = columns + n
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    p, way = [0] * (m + 1), [0] * (m + 1)
    for row in range(1, n + 1):
        p[0] = row
        minimum, used = [float("inf")] * (m + 1), [False] * (m + 1)
        j0 = 0
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], float("inf"), 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cost = -(weights[i0 - 1][j - 1] if j <= columns else 0.0) - u[i0] - v[j]
                if cost < minimum[j]:
                    minimum[j], way[j] = cost, j0
                if minimum[j] < delta:
                    delta, j1 = minimum[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minimum[j] -= delta
            j0 = j1
            if not p[j0]:
                break
        while j0:
            p[j0] = p[way[j0]]
            j0 = way[j0]
    return {p[j] - 1: j - 1 for j in range(1, columns + 1) if p[j] and weights[p[j] - 1][j - 1] > 0}


def match_candidates(
    *,
    frame: FrameKey,
    width: int,
    height: int,
    shapes: list[dict[str, Any]],
    detections: list[dict[str, Any]],
    classes: Sequence[str],
    label_ids: Mapping[str, str],
    provenance: dict[str, Any],
    params: Mapping[str, Any],
) -> tuple[Candidate, ...]:
    """E2 matched label conflict; E1 detector-only or annotation-only (human, no Qwen)."""
    threshold = probability(params.get("match_iou", 0.5))
    conflict = probability(params.get("conflict_confidence", 0.5))
    missing = probability(params.get("missing_confidence", 0.5))
    if threshold <= 0:
        raise ValueError("match_iou must be greater than zero")
    if set(classes) != set(label_ids):
        raise ValueError("detector class map does not match snapshot taxonomy")
    annotations = []
    for shape in shapes:
        if shape.get("outside"):
            continue
        source = shape.get("source", {})
        if not isinstance(source, dict) or "kind" not in source or "id" not in source:
            raise ValueError("annotation source missing")
        try:
            bbox = box(shape.get("points"), width, height)
        except ValueError:
            continue  # Geometry owns invalid annotation boxes.
        annotations.append((f"{source['kind']}:{source['id']}", str(shape["label_id"]), bbox))
    annotations.sort()
    valid = []
    for detection in detections:
        if not isinstance(detection, dict):
            raise ValueError("detector detection must be an object")
        bbox = box(detection.get("bbox_xyxy"), width, height)
        class_id = detection.get("class_id")
        if (
            isinstance(class_id, bool)
            or not isinstance(class_id, int)
            or not 0 <= class_id < len(classes)
        ):
            raise ValueError("invalid detector class index")
        if detection.get("class_name") != classes[class_id]:
            raise ValueError("detector class name/order mismatch")
        scores = detection.get("class_scores")
        if not isinstance(scores, list) or len(scores) != len(classes) + 1:
            raise ValueError("full detector class scores including background required")
        scores = [probability(s) for s in scores]
        if abs(sum(scores) - 1) > 1e-4:
            raise ValueError("detector class scores must sum to one")
        confidence = probability(detection.get("confidence"))
        if abs(confidence - scores[class_id]) > 1e-4:
            raise ValueError("detector confidence inconsistent with class scores")
        valid.append({**detection, "bbox_xyxy": list(bbox), "class_scores": scores})
    valid.sort(key=lambda d: (tuple(d["bbox_xyxy"]), d["class_id"], -d["confidence"]))
    weights = [
        [(value if (value := iou(d["bbox_xyxy"], a[2])) >= threshold else 0.0) for a in annotations]
        for d in valid
    ]
    matches = assignment(weights)
    candidates = []

    def emit(family: str, kind: str, object_id: str, reason: str, evidence: dict[str, Any]) -> None:
        if kind == "detector_box":
            run_id = provenance.get("run_id")
            if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
                raise ValueError("detector prediction anchor requires a positive run ID")
            object_id = f"{run_id}:{frame.cvat_task_id}:{frame.frame_number}:{object_id}"
        candidates.append(
            Candidate(
                "detector",
                "1.0.0",
                family,
                frame,
                Anchor(
                    kind,
                    (ObjectRef("detector" if kind == "detector_box" else "cvat_shape", object_id),),
                    MATCH_POLICY,
                    reason,
                ),
                {
                    "source": "detector",
                    "trigger_reason": reason,
                    "matching_policy": MATCH_POLICY,
                    "match_iou_threshold": threshold,
                    **provenance,
                    **evidence,
                },
            )
        )

    for index, detection in enumerate(valid):
        scores = detection["class_scores"]
        ranked = sorted(range(len(scores)), key=lambda c: (-scores[c], c))
        unknown = ranked[0] == len(classes)
        proposal = {
            **detection,
            "class_id": label_ids[detection["class_name"]],
            "model_class_id": detection["class_id"],
            "margin": scores[ranked[0]] - scores[ranked[1]],
            "unknown": unknown,
            "background_score": scores[-1],
        }
        common = {"proposal": proposal, "crop_bbox": detection["bbox_xyxy"]}
        if index in matches:
            a = annotations[matches[index]]
            if unknown or (a[1] != proposal["class_id"] and detection["confidence"] >= conflict):
                overlaps = sorted(weights[index], reverse=True)
                emit(
                    "E2",
                    "annotation",
                    a[0],
                    "unknown" if unknown else "label_conflict",
                    {
                        **common,
                        "annotated_class_id": a[1],
                        "matching_iou": weights[index][matches[index]],
                        "ambiguous": len(overlaps) > 1
                        and overlaps[1] > 0
                        and overlaps[0] - overlaps[1] < 0.05,
                    },
                )
        elif detection["confidence"] >= missing and not unknown:
            emit("E1", "detector_box", f"det:{index:04d}", "missing_object", common)
    matched_annotations = set(matches.values())
    for index, a in enumerate(annotations):
        if index not in matched_annotations:
            emit(
                "E1",
                "annotation",
                a[0],
                "detector_no_match",
                {"annotated_class_id": a[1], "human_review_required": True},
            )
    return tuple(candidates)
