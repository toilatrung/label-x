"""Shared HTTP transport; callers enforce worker URL and credential policies."""

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
