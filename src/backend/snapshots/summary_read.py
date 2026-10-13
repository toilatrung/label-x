"""Shared bounded CVAT reads for names, never fake upstream metadata."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import httpx

from config.exceptions import ApiError
from cvat_adapter.client import CvatReadClient


@contextmanager
def read_cvat(factory: Callable[[], CvatReadClient]) -> Iterator[CvatReadClient]:
    try:
        with factory() as cvat:
            yield cvat
    except ApiError:
        raise
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ApiError(404, "NOT_FOUND", "Dataset không tồn tại.") from None
        raise ApiError(502, "BUSINESS_RULE_UNMET", "Không đọc được metadata CVAT.") from None
    except (httpx.HTTPError, RuntimeError, ValueError, TypeError):
        raise ApiError(502, "BUSINESS_RULE_UNMET", "Không đọc được metadata CVAT.") from None
