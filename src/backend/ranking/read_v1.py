"""Read-side helpers for stored score_v1 explanations (pure; no DB, no model calls)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SCORE_V1 = "score_v1"
EVIDENCE_GROUPS = ("suspected", "unassessed", "no_suspicions")


def is_v1(score_version: str | None) -> bool:
    return score_version == SCORE_V1


def _explanation(explanation: Any) -> Mapping[str, Any]:
    return explanation if isinstance(explanation, Mapping) else {}


def dominant_tier(score_version: str | None, explanation: Any) -> int | None:
    if not is_v1(score_version):
        return None
    tier = _explanation(explanation).get("dominant_tier")
    return tier if isinstance(tier, int) and not isinstance(tier, bool) else None


def issue_counts_by_tier(score_version: str | None, explanation: Any) -> dict[str, int] | None:
    if not is_v1(score_version):
        return None
    counts = {str(tier): 0 for tier in range(1, 6)}
    contributions = _explanation(explanation).get("contributions")
    for item in contributions if isinstance(contributions, list) else []:
        tier = str(item.get("tier")) if isinstance(item, Mapping) else ""
        if tier in counts:
            counts[tier] += 1
    return counts


def evidence_scope(score_version: str | None, explanation: Any) -> dict[str, Any] | None:
    if not is_v1(score_version):
        return None
    scope = _explanation(explanation).get("evidence_scope")
    return dict(scope) if isinstance(scope, Mapping) else None


def evidence_group(score_version: str | None, explanation: Any) -> str | None:
    """Group stored by the scorer; the single predicate lives where the explanation is built."""
    if not is_v1(score_version):
        return None
    group = _explanation(explanation).get("evidence_group")
    return group if group in EVIDENCE_GROUPS else None
