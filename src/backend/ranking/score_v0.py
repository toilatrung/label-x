"""The frozen ``score_v0`` ranking rule (FR-RNK-01..06, 12)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256

from engines.interface import EngineStatus

SCORE_V0 = "score_v0"
_MISSING_EVIDENCE_STATUSES = frozenset({EngineStatus.FAILED.value, EngineStatus.NOT_CHECKED.value})


@dataclass(frozen=True, slots=True)
class ScoreVersion:
    """Immutable definition of the baseline score algorithm."""

    name: str = SCORE_V0
    annotation_epsilon: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        if self.name != SCORE_V0:
            raise ValueError(f"score_v0 only accepts version {SCORE_V0!r}")
        if not isinstance(self.annotation_epsilon, Decimal):
            raise TypeError("annotation_epsilon must be a Decimal")
        if not self.annotation_epsilon.is_finite() or self.annotation_epsilon < 0:
            raise ValueError("annotation_epsilon must be finite and non-negative")


DEFAULT_SCORE_VERSION = ScoreVersion()


@dataclass(frozen=True, slots=True)
class FrameInput:
    """One snapshot frame, including frames without any Candidate."""

    cvat_task_id: int
    frame_number: int
    annotation_count: int = 0
    engine_statuses: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        numeric_values = (self.cvat_task_id, self.frame_number, self.annotation_count)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in numeric_values):
            raise TypeError("frame identifiers and annotation_count must be integers")
        if any(value < 0 for value in numeric_values):
            raise ValueError("frame identifiers and annotation_count must be non-negative")
        engines = [engine for engine, _status in self.engine_statuses]
        if len(engines) != len(set(engines)):
            raise ValueError("engine_statuses must contain at most one status per engine")
        valid_statuses = {status.value for status in EngineStatus}
        if any(status not in valid_statuses for _engine, status in self.engine_statuses):
            raise ValueError("engine_statuses contains an unknown status")

    @property
    def key(self) -> str:
        return f"{self.cvat_task_id}:{self.frame_number}"


@dataclass(frozen=True, slots=True)
class IssueContribution:
    """Persistable explanation for one provisional issue from a Candidate."""

    candidate_hash: str
    family: str
    anchor_count: int
    n_i: int
    q_i: Decimal
    contribution: Decimal


@dataclass(frozen=True, slots=True)
class RankedFrame:
    """Complete score record; tuple fields prevent accidental mutation."""

    frame_key: str
    score_version: str
    rank: int
    score: Decimal
    baseline_score: Decimal
    missing_evidence: bool
    anchor_counts: tuple[tuple[str, int], ...]
    contributions: tuple[IssueContribution, ...]
    tie_break_hash: str


def rank_frames(
    frames: Sequence[FrameInput],
    candidates: Iterable[Mapping[str, object]],
    *,
    seed: int,
    required_engines: Iterable[str] = (),
    score_version: ScoreVersion = DEFAULT_SCORE_VERSION,
) -> tuple[tuple[RankedFrame, ...], str]:
    """Score all supplied frames and return a deterministic ranking and hash.

    The function consumes Candidate-shaped mappings from the engine contract.
    Before aggregation is connected, each candidate is a provisional issue; its
    anchor nevertheless derives the required ``n_i`` value.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError("seed must be an integer")

    by_key: dict[str, FrameInput] = {}
    for frame in frames:
        if frame.key in by_key:
            raise ValueError(f"duplicate frame key: {frame.key}")
        by_key[frame.key] = frame

    contributions: dict[str, list[IssueContribution]] = defaultdict(list)
    for candidate in candidates:
        frame_key = _candidate_frame_key(candidate)
        if frame_key not in by_key:
            raise ValueError(f"candidate refers to frame outside snapshot: {frame_key}")
        contributions[frame_key].append(_contribution(candidate))

    required = frozenset(required_engines)
    if any(not engine for engine in required):
        raise ValueError("required_engines cannot contain an empty engine name")
    unranked: list[RankedFrame] = []
    for frame_key, frame in by_key.items():
        items = tuple(sorted(contributions[frame_key], key=lambda item: item.candidate_hash))
        baseline = score_version.annotation_epsilon * frame.annotation_count
        score = baseline + sum((item.contribution for item in items), start=Decimal())
        statuses = dict(frame.engine_statuses)
        missing_evidence = any(
            statuses.get(engine) in _MISSING_EVIDENCE_STATUSES or engine not in statuses
            for engine in required
        )
        counts = Counter(item.family for item in items)
        unranked.append(
            RankedFrame(
                frame_key,
                score_version.name,
                0,
                score,
                baseline,
                missing_evidence,
                tuple(sorted(counts.items())),
                items,
                _tie_break_hash(frame_key, seed),
            )
        )

    ordered = sorted(unranked, key=lambda item: (-item.score, item.tie_break_hash, item.frame_key))
    ranked = tuple(
        RankedFrame(
            item.frame_key,
            item.score_version,
            index,
            item.score,
            item.baseline_score,
            item.missing_evidence,
            item.anchor_counts,
            item.contributions,
            item.tie_break_hash,
        )
        for index, item in enumerate(ordered, start=1)
    )
    return ranked, _ranking_hash(ranked, seed, score_version)


def _contribution(candidate: Mapping[str, object]) -> IssueContribution:
    family = _required_string(candidate, "family")
    anchor = _required_mapping(candidate, "anchor")
    objects = anchor.get("objects")
    if not isinstance(objects, Sequence) or isinstance(objects, (str, bytes)):
        raise ValueError("candidate.anchor.objects must be an array")
    anchor_count = len(objects)
    if family in {"E1", "E2"}:
        n_i, q_i = 1, _confidence(candidate)
    elif family == "E3":
        if anchor_count < 2:
            raise ValueError("E3 candidate must have at least two anchor objects")
        n_i, q_i = anchor_count - 1, Decimal("0.5")
    else:
        raise ValueError(f"score_v0 does not define a score for family {family!r}")
    return IssueContribution(
        _canonical_hash(candidate), family, anchor_count, n_i, q_i, Decimal(n_i) * q_i
    )


def _confidence(candidate: Mapping[str, object]) -> Decimal:
    evidence = _required_mapping(candidate, "evidence")
    try:
        confidence = Decimal(str(evidence["confidence"]))
    except (KeyError, InvalidOperation) as error:
        raise ValueError("E1/E2 candidate requires numeric evidence.confidence") from error
    if not confidence.is_finite() or not Decimal() <= confidence <= Decimal(1):
        raise ValueError("evidence.confidence must be between 0 and 1")
    return confidence


def _candidate_frame_key(candidate: Mapping[str, object]) -> str:
    frame = _required_mapping(candidate, "frame")
    task_id, frame_number = frame.get("cvat_task_id"), frame.get("frame_number")
    if (
        not isinstance(task_id, int)
        or isinstance(task_id, bool)
        or not isinstance(frame_number, int)
        or isinstance(frame_number, bool)
        or task_id < 0
        or frame_number < 0
    ):
        raise ValueError("candidate.frame requires integer cvat_task_id and frame_number")
    return f"{task_id}:{frame_number}"


def _required_mapping(source: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = source.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"candidate.{key} must be an object")
    return value


def _required_string(source: Mapping[str, object], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str):
        raise ValueError(f"candidate.{key} must be a string")
    return value


def _tie_break_hash(frame_key: str, seed: int) -> str:
    """SHA256(frame_key || seed), as specified by FR-RNK-04."""
    return sha256(f"{frame_key}{seed}".encode()).hexdigest()


def _canonical_hash(value: Mapping[str, object]) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _ranking_hash(ranked: Sequence[RankedFrame], seed: int, version: ScoreVersion) -> str:
    payload = {
        "score_version": version.name,
        "annotation_epsilon": str(version.annotation_epsilon),
        "seed": seed,
        "frames": [
            {
                "frame_key": frame.frame_key,
                "rank": frame.rank,
                "score": str(frame.score),
                "baseline_score": str(frame.baseline_score),
                "missing_evidence": frame.missing_evidence,
                "anchor_counts": frame.anchor_counts,
                "contributions": [
                    {
                        "candidate_hash": item.candidate_hash,
                        "family": item.family,
                        "anchor_count": item.anchor_count,
                        "n_i": item.n_i,
                        "q_i": str(item.q_i),
                        "contribution": str(item.contribution),
                    }
                    for item in frame.contributions
                ],
            }
            for frame in ranked
        ],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
