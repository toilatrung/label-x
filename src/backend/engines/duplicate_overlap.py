"""Pure duplicate/overlap candidate generation (T-028).

The one-to-one matcher from T-023 owns pair discovery.  This module only turns
its deterministic pair fixture into review candidates; it deliberately has no
database, Django, or orchestrator dependency.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

DUPLICATE_OVERLAP_RULE_ID = "FR-ENG-04"
DUPLICATE_OVERLAP_THRESHOLD = 0.85


@dataclass(frozen=True, order=True)
class Annotation:
    """The stable annotation fields required in E3 evidence."""

    annotation_id: str
    label: str


@dataclass(frozen=True)
class MatchingPair:
    """A pair returned by the T-023 matching boundary.

    ``annotation_ids`` may arrive in either order.  ``iou`` is retained as
    matcher evidence, rather than recalculated by this engine.
    """

    left_annotation_id: str
    right_annotation_id: str
    iou: float

    @property
    def annotation_ids(self) -> tuple[str, str]:
        return (
            min(self.left_annotation_id, self.right_annotation_id),
            max(self.left_annotation_id, self.right_annotation_id),
        )


@dataclass(frozen=True)
class DuplicateOverlapEvidence:
    """Evidence a reviewer needs to judge an E3 suspicion."""

    rule_id: str
    iou: float
    annotation_ids: tuple[str, str]
    labels: tuple[str, str]
    same_label: bool
    cluster_annotation_ids: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateOverlapCandidate:
    """An immutable E3 suspicion, not a confirmed KPI error."""

    family: str
    frame_key: str
    anchor_annotation_id: str
    evidence: DuplicateOverlapEvidence
    structural_warning: bool = True
    is_kpi_error: bool = False


def generate_duplicate_overlap_candidates(
    *,
    frame_key: str,
    annotations: Iterable[Annotation],
    matching_pairs: Iterable[MatchingPair],
    threshold: float = DUPLICATE_OVERLAP_THRESHOLD,
) -> tuple[DuplicateOverlapCandidate, ...]:
    """Return ordered E3 candidates for matching pairs at or above ``threshold``.

    Input order never affects the result.  All connected qualifying pairs carry
    the same stable cluster anchor, allowing later aggregation to represent a
    cluster of ``m`` boxes as ``m - 1`` errors without treating a candidate as a
    KPI error by itself.
    """
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be in [0, 1]")

    annotation_values = tuple(annotations)
    annotation_by_id = {annotation.annotation_id: annotation for annotation in annotation_values}
    if len(annotation_by_id) != len(annotation_values):
        raise ValueError("annotation_id must be unique")

    pairs_by_ids: dict[tuple[str, str], float] = {}
    for pair in matching_pairs:
        annotation_ids = pair.annotation_ids
        if annotation_ids[0] == annotation_ids[1]:
            raise ValueError("a matching pair must contain two different annotations")
        if not 0 <= pair.iou <= 1:
            raise ValueError("pair IoU must be in [0, 1]")
        if set(annotation_ids) - annotation_by_id.keys():
            raise ValueError("matching pair references an unknown annotation")
        if pair.iou >= threshold:
            pairs_by_ids[annotation_ids] = max(pairs_by_ids.get(annotation_ids, 0.0), pair.iou)

    clusters = _clusters(pairs_by_ids)
    candidates = []
    for annotation_ids, iou in pairs_by_ids.items():
        left, right = (annotation_by_id[annotation_id] for annotation_id in annotation_ids)
        cluster_ids = clusters[annotation_ids[0]]
        candidates.append(
            DuplicateOverlapCandidate(
                family="E3",
                frame_key=frame_key,
                anchor_annotation_id=cluster_ids[0],
                evidence=DuplicateOverlapEvidence(
                    rule_id=DUPLICATE_OVERLAP_RULE_ID,
                    iou=iou,
                    annotation_ids=annotation_ids,
                    labels=(left.label, right.label),
                    same_label=left.label == right.label,
                    cluster_annotation_ids=cluster_ids,
                ),
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.anchor_annotation_id,
                candidate.evidence.annotation_ids,
                -candidate.evidence.iou,
            ),
        )
    )


def _clusters(pairs_by_ids: dict[tuple[str, str], float]) -> dict[str, tuple[str, ...]]:
    """Connected components over qualifying pairs, with lexical stable roots."""
    parents = {annotation_id: annotation_id for pair in pairs_by_ids for annotation_id in pair}

    def find(annotation_id: str) -> str:
        while parents[annotation_id] != annotation_id:
            parents[annotation_id] = parents[parents[annotation_id]]
            annotation_id = parents[annotation_id]
        return annotation_id

    for left, right in sorted(pairs_by_ids):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    members: dict[str, list[str]] = {}
    for annotation_id in parents:
        members.setdefault(find(annotation_id), []).append(annotation_id)
    return {annotation_id: tuple(sorted(members[find(annotation_id)])) for annotation_id in parents}
