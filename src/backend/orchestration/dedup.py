"""Khoá dedup candidate (DEC-006) và chuẩn hoá JSON tất định."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from enum import Enum
from typing import Any

from engines.interface import Candidate


def to_jsonable(value: Any) -> Any:
    """Dataclass/tuple/enum -> JSON thuần, khoá sắp xếp để băm tất định."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(v) for v in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(to_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def dedup_key(candidate: Candidate) -> str:
    """Cùng engine/family/frame/anchor (kèm policy version) -> cùng khoá, bất kể thứ tự object."""
    anchor = candidate.anchor
    return sha256_hex(
        {
            "engine": candidate.engine,
            "family": candidate.family,
            "frame": candidate.frame,
            "kind": anchor.kind,
            "objects": sorted((o.namespace, o.id) for o in anchor.objects),
            "policy_version": anchor.policy_version,
            "rule_id": anchor.rule_id,
        }
    )
