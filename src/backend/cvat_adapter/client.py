"""Small CVAT REST client with an intentionally read-only public API."""

from collections.abc import Mapping
from typing import cast
from urllib.parse import urljoin

import httpx

QueryValue = str | int | float | bool | None


class CvatConfigurationError(ValueError):
    """Raised when the adapter is initialized without safe configuration."""


class CvatReadClient:
    """Read jobs and annotations from CVAT using a read-only PAT.

    This boundary deliberately exposes no generic request function and no HTTP
    mutation method. Dataset provisioning lives in scripts/development, outside
    the product adapter.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.strip():
            raise CvatConfigurationError("CVAT_BASE_URL is required")
        if not token.strip():
            raise CvatConfigurationError("CVAT_SERVICE_TOKEN is required")

        self._base_url = base_url.rstrip("/") + "/"
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.cvat+json",
            },
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CvatReadClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _get(self, endpoint: str, *, params: Mapping[str, QueryValue] | None = None) -> object:
        response = self._client.get(urljoin(self._base_url, endpoint.lstrip("/")), params=params)
        response.raise_for_status()
        return cast(object, response.json())

    def list_jobs(
        self, *, task_id: int | None = None, page_size: int = 100
    ) -> list[dict[str, object]]:
        """Return every job, following CVAT's page-based pagination."""

        jobs: list[dict[str, object]] = []
        page = 1
        while True:
            params: dict[str, QueryValue] = {"page": page, "page_size": page_size}
            if task_id is not None:
                params["task_id"] = task_id
            payload = self._get("api/jobs", params=params)
            if not isinstance(payload, dict):
                raise TypeError("CVAT jobs response must be an object")
            raw_results = payload.get("results", [])
            if not isinstance(raw_results, list):
                raise TypeError("CVAT jobs results must be a list")
            jobs.extend(item for item in raw_results if isinstance(item, dict))
            if not payload.get("next"):
                return jobs
            page += 1

    def get_job(self, job_id: int) -> dict[str, object]:
        return self._get_object(f"api/jobs/{job_id}")

    def get_job_annotations(self, job_id: int) -> dict[str, object]:
        return self._get_object(f"api/jobs/{job_id}/annotations")

    def get_job_data_meta(self, job_id: int) -> dict[str, object]:
        return self._get_object(f"api/jobs/{job_id}/data/meta")

    def _get_object(self, endpoint: str) -> dict[str, object]:
        payload = self._get(endpoint)
        if not isinstance(payload, dict):
            raise TypeError(f"CVAT response for {endpoint} must be an object")
        return payload
