"""Integration seam for T-035's append-only ReviewDecision source.

There is no competing decision projection in T-033. Until T-035 installs its
model there cannot be a persisted review decision in this database. Once the
model exists, expiry fails closed unless T-035 supplies the adapter path.
"""

from django.apps import apps
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from review.models import FrameReview


def has_persisted_decision(frame: FrameReview) -> bool:
    try:
        apps.get_model("review", "ReviewDecision")
    except LookupError:
        return False
    adapter_path = getattr(settings, "REVIEW_PERSISTED_DECISION_CHECK", None)
    if not adapter_path:
        raise ImproperlyConfigured(
            "T-035 must configure REVIEW_PERSISTED_DECISION_CHECK before decision expiry"
        )
    return bool(import_string(adapter_path)(frame))
