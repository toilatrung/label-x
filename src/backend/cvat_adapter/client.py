"""Small CVAT REST client with an intentionally read-only public API."""

from collections.abc import Mapping
from typing import cast
from urllib.parse import urlencode, urljoin

import httpx

QueryValue = str | int | float | bool | None


class CvatConfigurationError(ValueError):
    """Raised when the adapter is initialized without safe configuration."""


class CvatWriteBlocked(RuntimeError):
    """Raised before a non-read HTTP request can leave the adapter."""


def _enforce_read_only(request: httpx.Request) -> None:
    if request.method.upper() not in {"GET", "HEAD"}:
        raise CvatWriteBlocked(f"CVAT adapter blocked HTTP {request.method.upper()}")


def build_job_url(
    base_url: str, task_id: int, job_id: int, *, frame_index: int | None = None
) -> str:
    url = urljoin(base_url.rstrip("/") + "/", f"tasks/{task_id}/jobs/{job_id}")
    if frame_index is None:
        return url
    return f"{url}?{urlencode({'frame': frame_index})}"


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
            event_hooks={"request": [_enforce_read_only]},
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

    def _get_bytes(
        self, endpoint: str, *, params: Mapping[str, QueryValue] | None = None
    ) -> tuple[bytes, str]:
        response = self._client.get(urljoin(self._base_url, endpoint.lstrip("/")), params=params)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "application/octet-stream")

    def _list(
        self,
        endpoint: str,
        *,
        filters: Mapping[str, QueryValue] | None = None,
        page_size: int = 100,
        max_pages: int = 1000,
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        page = 1
        while page <= max_pages:
            params: dict[str, QueryValue] = {
                "page": page,
                "page_size": page_size,
                **dict(filters or {}),
            }
            payload = self._get(endpoint, params=params)
            if not isinstance(payload, dict):
                raise TypeError(f"CVAT list response for {endpoint} must be an object")
            raw_results = payload.get("results", [])
            if not isinstance(raw_results, list):
                raise TypeError(f"CVAT list results for {endpoint} must be a list")
            results.extend(item for item in raw_results if isinstance(item, dict))
            if not raw_results or not payload.get("next"):
                return results
            page += 1
        raise RuntimeError(f"CVAT pagination for {endpoint} exceeded {max_pages} pages")

    def list_jobs(
        self, *, task_id: int | None = None, page_size: int = 100, max_pages: int = 1000
    ) -> list[dict[str, object]]:
        """Return every job, following CVAT's page-based pagination."""

        filters: dict[str, QueryValue] = {}
        if task_id is not None:
            filters["task_id"] = task_id
        return self._list("api/jobs", filters=filters, page_size=page_size, max_pages=max_pages)

    def list_tasks(
        self, *, project_id: int, page_size: int = 100, max_pages: int = 1000
    ) -> list[dict[str, object]]:
        return self._list(
            "api/tasks",
            filters={"project_id": project_id},
            page_size=page_size,
            max_pages=max_pages,
        )

    def list_projects(
        self, *, page_size: int = 100, max_pages: int = 1000
    ) -> list[dict[str, object]]:
        return self._list("api/projects", page_size=page_size, max_pages=max_pages)

    def list_labels(
        self, *, project_id: int, page_size: int = 100, max_pages: int = 1000
    ) -> list[dict[str, object]]:
        return self._list(
            "api/labels",
            filters={"project_id": project_id},
            page_size=page_size,
            max_pages=max_pages,
        )

    def get_project(self, project_id: int) -> dict[str, object]:
        return self._get_object(f"api/projects/{project_id}")

    def get_task(self, task_id: int) -> dict[str, object]:
        return self._get_object(f"api/tasks/{task_id}")

    def get_job(self, job_id: int) -> dict[str, object]:
        return self._get_object(f"api/jobs/{job_id}")

    def get_job_annotations(self, job_id: int) -> dict[str, object]:
        return self._get_object(f"api/jobs/{job_id}/annotations")

    def get_job_data_meta(self, job_id: int) -> dict[str, object]:
        return self._get_object(f"api/jobs/{job_id}/data/meta")

    def get_job_frame(self, job_id: int, frame_index: int) -> tuple[bytes, str]:
        return self._get_bytes(
            f"api/jobs/{job_id}/data",
            params={"type": "frame", "number": frame_index, "quality": "original"},
        )

    def job_url(self, task_id: int, job_id: int, *, frame_index: int | None = None) -> str:
        return build_job_url(self._base_url, task_id, job_id, frame_index=frame_index)

    def _get_object(self, endpoint: str) -> dict[str, object]:
        payload = self._get(endpoint)
        if not isinstance(payload, dict):
            raise TypeError(f"CVAT response for {endpoint} must be an object")
        return payload
