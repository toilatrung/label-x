"""Fixed 10-class taxonomy shared with the detector worker (``bdd100k-det-10-v1``).

``unknown`` is an abstention decided by routing policy, never an eleventh class.
"""

from __future__ import annotations

MAPPING_VERSION = "bdd100k-det-10-v1"
CLASSES: tuple[str, ...] = (
    "pedestrian",
    "rider",
    "car",
    "truck",
    "bus",
    "train",
    "motorcycle",
    "bicycle",
    "traffic light",
    "traffic sign",
)
CLASS_INDEX: dict[str, int] = {name: index for index, name in enumerate(CLASSES)}
