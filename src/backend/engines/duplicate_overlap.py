"""Pure duplicate/overlap engine boundary (T-028).

T-023 owns IoU calculation and deterministic matching.  Duplicate detection
must retain every qualifying annotation-to-annotation edge, so this adapter
invokes the public matcher once per unordered pair instead of consuming only
the selected edges from one global one-to-one solution.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations

from engines.interface import (
    Anchor,
    Candidate,
    EngineDescriptor,
    EngineInput,
    EngineOutput,
    EngineUnitResult,
    FrameKey,
    ObjectRef,
)
from engines.matching import BoundingBox, match_one_to_one

DUPLICATE_OVERLAP_ENGINE_NAME = "duplicate"
DUPLICATE_OVERLAP_ENGINE_VERSION = "1.0.0"
DUPLICATE_OVERLAP_APPLICABILITY_VERSION = "1.0.0"
DUPLICATE_OVERLAP_ANCHOR_POLICY_VERSION = "1.0.0"
DUPLICATE_OVERLAP_RULE_ID = "DUP-01"
DUPLICATE_OVERLAP_SRS_REQUIREMENT = "FR-ENG-04"
DUPLICATE_OVERLAP_THRESHOLD = 0.85

DUPLICATE_OVERLAP_DESCRIPTOR = EngineDescriptor(
    name=DUPLICATE_OVERLAP_ENGINE_NAME,
    version=DUPLICATE_OVERLAP_ENGINE_VERSION,
    unit="frame",
    required=True,
    needs_model=False,
    needs_reference=False,
    applicability_version=DUPLICATE_OVERLAP_APPLICABILITY_VERSION,
)


@dataclass(frozen=True, order=True)
class Annotation:
    """Snapshot annotation fields required by matching and E3 evidence."""

    annotation_id: str
    label: str

    x1: float
    y1: float
    x2: float
    y2: float
    ignored: bool = False

    def as_matching_box(self) -> BoundingBox:
        return BoundingBox(
            id=self.annotation_id,
            label=self.label,
            x1=self.x1,
            y1=self.y1,
            x2=self.x2,
            y2=self.y2,
            ignored=self.ignored,
        )


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

    engine: str
    rule_id: str
    srs_requirement: str
    iou: float
    annotation_ids: tuple[str, str]
    labels: tuple[str, str]
    same_label: bool
    cluster_annotation_ids: tuple[str, ...]
    structural_warning: bool = True
    is_kpi_error: bool = False


def generate_duplicate_overlap_candidates(
    *,
    frame: FrameKey,
    annotations: Iterable[Annotation],
    matching_pairs: Iterable[MatchingPair],
    threshold: float = DUPLICATE_OVERLAP_THRESHOLD,
) -> tuple[Candidate, ...]:
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
            Candidate(
                engine=DUPLICATE_OVERLAP_ENGINE_NAME,
                engine_version=DUPLICATE_OVERLAP_ENGINE_VERSION,
                family="E3",
                frame=frame,
                anchor=Anchor(
                    kind="annotation_cluster",
                    objects=tuple(
                        ObjectRef(namespace="cvat_shape", id=annotation_id)
                        for annotation_id in cluster_ids
                    ),
                    rule_id=DUPLICATE_OVERLAP_RULE_ID,
                    policy_version=DUPLICATE_OVERLAP_ANCHOR_POLICY_VERSION,
                ),
                evidence=DuplicateOverlapEvidence(
                    engine=DUPLICATE_OVERLAP_ENGINE_NAME,
                    rule_id=DUPLICATE_OVERLAP_RULE_ID,
                    srs_requirement=DUPLICATE_OVERLAP_SRS_REQUIREMENT,
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
                tuple(obj.id for obj in candidate.anchor.objects),
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


def match_duplicate_overlap_pairs(
    annotations: Iterable[Annotation],
    *,
    threshold: float = DUPLICATE_OVERLAP_THRESHOLD,
) -> tuple[MatchingPair, ...]:
    """Discover every qualifying edge through T-023's public matcher API."""
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be in [0, 1]")

    boxes = tuple(
        sorted((annotation.as_matching_box() for annotation in annotations), key=lambda b: b.id)
    )
    if len({box.id for box in boxes}) != len(boxes):
        raise ValueError("annotation_id must be unique")

    pairs: list[MatchingPair] = []
    for left, right in combinations(boxes, 2):
        result = match_one_to_one(
            (left,),
            (right,),
            tau_m=threshold,
            tau_amb=threshold,
        )
        if result.matches:
            match = result.matches[0]
            pairs.append(MatchingPair(match.left_id, match.right_id, match.iou))
    return tuple(pairs)


def run_duplicate_overlap_engine(
    engine_input: EngineInput,
    annotations_by_frame: Mapping[FrameKey, Iterable[Annotation]],
) -> EngineOutput:
    """Run a duplicate shard and return one ledger result for every input frame."""
    _validate_engine_input(engine_input)
    threshold_value = engine_input.config.params.get("iou_threshold", DUPLICATE_OVERLAP_THRESHOLD)
    if not isinstance(threshold_value, int | float):
        raise ValueError("iou_threshold must be a number")
    threshold = float(threshold_value)
    if not 0 <= threshold <= 1:
        raise ValueError("iou_threshold must be in [0, 1]")

    if len({unit.frame for unit in engine_input.units}) != len(engine_input.units):
        raise ValueError("duplicate frame unit in engine input")

    candidates: list[Candidate] = []
    unit_results: list[EngineUnitResult] = []
    for unit in engine_input.units:
        if unit.kind != "frame":
            raise ValueError("duplicate overlap engine only accepts frame units")
        try:
            annotations = tuple(annotations_by_frame[unit.frame])
        except KeyError as exc:
            raise ValueError(f"missing annotations for frame {unit.frame}") from exc

        pairs = match_duplicate_overlap_pairs(annotations, threshold=threshold)
        candidates.extend(
            generate_duplicate_overlap_candidates(
                frame=unit.frame,
                annotations=annotations,
                matching_pairs=pairs,
                threshold=threshold,
            )
        )
        unit_results.append(EngineUnitResult(unit=unit, outcome="completed", attempts=1))

    candidates.sort(
        key=lambda candidate: (
            candidate.frame,
            tuple(obj.id for obj in candidate.anchor.objects),
            candidate.evidence.annotation_ids,
        )
    )
    return EngineOutput(
        idempotency_key=engine_input.idempotency_key,
        engine=DUPLICATE_OVERLAP_ENGINE_NAME,
        engine_version=DUPLICATE_OVERLAP_ENGINE_VERSION,
        candidates=tuple(candidates),
        unit_results=tuple(unit_results),
    )


def _validate_engine_input(engine_input: EngineInput) -> None:
    if engine_input.engine != DUPLICATE_OVERLAP_ENGINE_NAME:
        raise ValueError("engine input is not for the duplicate engine")
    if engine_input.engine_version != DUPLICATE_OVERLAP_ENGINE_VERSION:
        raise ValueError("engine version does not match the duplicate engine")
    if engine_input.config.engine != DUPLICATE_OVERLAP_ENGINE_NAME:
        raise ValueError("engine config is not for the duplicate engine")
    if not engine_input.config.enabled:
        raise ValueError("disabled engine must not be dispatched to a worker")
