"""Deterministic audit sampling and control rankings for E-11 (T-031).

These functions deliberately use only locked snapshot inputs.  Persistence and
HTTP delivery belong to the runs app (T-022); keeping the policy here pure
makes the algorithm reproducible and straightforward to audit.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from hashlib import sha256

from .score_v0 import FrameInput, RankedFrame


class RankingSource(StrEnum):
    """Sources are stored separately; none may be mixed into the risk queue."""

    RANDOM_AUDIT = "random_audit"
    RANDOM_CONTROL = "random_control"
    ANNOTATION_COUNT_CONTROL = "annotation_count_control"
    MAX_CONFIDENCE_CONTROL = "max_confidence_control"


@dataclass(frozen=True, slots=True)
class QueueEntry:
    frame_key: str
    rank: int
    source: RankingSource
    tie_break_hash: str
    value: Decimal | None = None


@dataclass(frozen=True, slots=True)
class StoredOrdering:
    """A separately persistable ordering with canonical content hash."""

    source: RankingSource
    seed: int
    entries: tuple[QueueEntry, ...]
    content_hash: str


def random_audit_slice(
    frames: Sequence[FrameInput], *, percent: Decimal, seed: int
) -> StoredOrdering:
    """Select ceil(r% × N) frames independently of risk ranking (FR-RNK-07)."""
    _validate_seed(seed)
    is_valid_percent = (
        isinstance(percent, Decimal)
        and percent.is_finite()
        and Decimal(0) <= percent <= Decimal(100)
    )
    if not is_valid_percent:
        raise ValueError("percent must be a finite Decimal between 0 and 100")
    unique = _unique_frames(frames)
    count = int((Decimal(len(unique)) * percent / Decimal(100)).to_integral_value(ROUND_CEILING))
    ordered = sorted(
        unique,
        key=lambda frame: (_hash(RankingSource.RANDOM_AUDIT, frame.key, seed), frame.key),
    )
    entries = tuple(
        QueueEntry(
            frame.key,
            index,
            RankingSource.RANDOM_AUDIT,
            _hash(RankingSource.RANDOM_AUDIT, frame.key, seed),
        )
        for index, frame in enumerate(ordered[:count], start=1)
    )
    return _stored(RankingSource.RANDOM_AUDIT, seed, entries)


def control_rankings(
    frames: Sequence[FrameInput], candidates: Iterable[Mapping[str, object]], *, seed: int
) -> tuple[StoredOrdering, ...]:
    """Produce random, annotation-density and max-confidence control orderings."""
    _validate_seed(seed)
    unique = _unique_frames(frames)
    max_confidence = {frame.key: Decimal(0) for frame in unique}
    known = set(max_confidence)
    for candidate in candidates:
        frame_key = _frame_key(candidate)
        if frame_key not in known:
            raise ValueError(f"candidate refers to frame outside snapshot: {frame_key}")
        confidence = _candidate_confidence(candidate)
        if confidence is not None:
            max_confidence[frame_key] = max(max_confidence[frame_key], confidence)

    random_entries = _entries_by_key(unique, RankingSource.RANDOM_CONTROL, seed)
    annotation_entries = _entries_by_value(
        unique,
        RankingSource.ANNOTATION_COUNT_CONTROL,
        seed,
        lambda frame: Decimal(frame.annotation_count),
    )
    confidence_entries = _entries_by_value(
        unique, RankingSource.MAX_CONFIDENCE_CONTROL, seed, lambda frame: max_confidence[frame.key]
    )
    return (
        _stored(RankingSource.RANDOM_CONTROL, seed, random_entries),
        _stored(RankingSource.ANNOTATION_COUNT_CONTROL, seed, annotation_entries),
        _stored(RankingSource.MAX_CONFIDENCE_CONTROL, seed, confidence_entries),
    )


def explain_score(frame: RankedFrame) -> dict[str, object]:
    """Return a JSON-safe score explanation for the audit/review UI."""
    return {
        "frame_key": frame.frame_key,
        "score_version": frame.score_version,
        "rank": frame.rank,
        "score": str(frame.score),
        "baseline_score": str(frame.baseline_score),
        "missing_evidence": frame.missing_evidence,
        "issue_counts": dict(frame.anchor_counts),
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


def _entries_by_key(
    frames: Sequence[FrameInput], source: RankingSource, seed: int
) -> tuple[QueueEntry, ...]:
    ordered = sorted(frames, key=lambda frame: (_hash(source, frame.key, seed), frame.key))
    return tuple(
        QueueEntry(frame.key, index, source, _hash(source, frame.key, seed))
        for index, frame in enumerate(ordered, start=1)
    )


def _entries_by_value(
    frames: Sequence[FrameInput],
    source: RankingSource,
    seed: int,
    value_for: Callable[[FrameInput], Decimal],
) -> tuple[QueueEntry, ...]:
    ordered = sorted(
        frames,
        key=lambda frame: (-value_for(frame), _hash(source, frame.key, seed), frame.key),
    )
    return tuple(
        QueueEntry(frame.key, index, source, _hash(source, frame.key, seed), value_for(frame))
        for index, frame in enumerate(ordered, start=1)
    )


def _stored(source: RankingSource, seed: int, entries: tuple[QueueEntry, ...]) -> StoredOrdering:
    serialized_entries = [
        asdict(entry)
        | {
            "source": entry.source.value,
            "value": str(entry.value) if entry.value is not None else None,
        }
        for entry in entries
    ]
    payload = {"source": source.value, "seed": seed, "entries": serialized_entries}
    content_hash = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return StoredOrdering(source, seed, entries, content_hash)


def _unique_frames(frames: Sequence[FrameInput]) -> tuple[FrameInput, ...]:
    values = tuple(frames)
    if len({frame.key for frame in values}) != len(values):
        raise ValueError("frames must have unique frame keys")
    return values


def _hash(source: RankingSource, frame_key: str, seed: int) -> str:
    return sha256(f"{source.value}|{frame_key}|{seed}".encode()).hexdigest()


def _validate_seed(seed: int) -> None:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError("seed must be an integer")


def _frame_key(candidate: Mapping[str, object]) -> str:
    frame = candidate.get("frame")
    if not isinstance(frame, Mapping):
        raise ValueError("candidate.frame must be an object")
    task_id, frame_number = frame.get("cvat_task_id"), frame.get("frame_number")
    values = (task_id, frame_number)
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0 for value in values
    ):
        raise ValueError("candidate.frame requires non-negative integer IDs")
    return f"{task_id}:{frame_number}"


def _candidate_confidence(candidate: Mapping[str, object]) -> Decimal | None:
    evidence = candidate.get("evidence")
    if not isinstance(evidence, Mapping) or "confidence" not in evidence:
        return None
    try:
        value = Decimal(str(evidence["confidence"]))
    except Exception as error:  # Decimal exposes multiple exception types.
        raise ValueError("candidate.evidence.confidence must be numeric") from error
    if not value.is_finite() or not Decimal(0) <= value <= Decimal(1):
        raise ValueError("candidate.evidence.confidence must be between 0 and 1")
    return value
