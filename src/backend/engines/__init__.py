"""Interface engine dùng chung (T-006, DEC-010); cài đặt engine cụ thể thuộc E-08, E-10.

Thư viện matching một-một tất định (T-023, E-05).
"""

from engines.duplicate_overlap import (
    DUPLICATE_OVERLAP_DESCRIPTOR,
    Annotation,
    run_duplicate_overlap_engine,
)
from engines.matching import (
    ALGORITHM_VERSION,
    DEFAULT_TAU_AMB,
    DEFAULT_TAU_M,
    AmbiguousPair,
    BoundingBox,
    MatchingResult,
    MatchPair,
    compute_iou,
    match_one_to_one,
)

__all__ = [
    "ALGORITHM_VERSION",
    "DEFAULT_TAU_AMB",
    "DEFAULT_TAU_M",
    "AmbiguousPair",
    "BoundingBox",
    "MatchPair",
    "MatchingResult",
    "compute_iou",
    "match_one_to_one",
    "Annotation",
    "DUPLICATE_OVERLAP_DESCRIPTOR",
    "run_duplicate_overlap_engine",
]
