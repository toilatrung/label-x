"""Shared HTTP transport; callers enforce worker URL and credential policies."""

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx


def request_json(
    method: str,
    url: str,
    *,
    token: str,
    timeout: float,
    body: dict[str, Any] | None = None,
) -> object:
    # Never use host proxy variables or follow redirects with worker credentials.
    with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        response = client.request(
            method, url, json=body, headers={"Authorization": "Bearer " + token}
        )
        response.raise_for_status()
        payload: object = response.json()
    return payload


def retry_after_seconds(response: httpx.Response) -> float:
    """Accept delta-seconds and HTTP-date; bound provider-controlled delays."""
    raw = response.headers.get("Retry-After", "")
    if raw.isdigit():
        return min(float(raw), 120)
    try:
        until = parsedate_to_datetime(raw)
        if until.tzinfo is None:
            until = until.replace(tzinfo=UTC)
        return max(0, min(120, (until - datetime.now(UTC)).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return 0
