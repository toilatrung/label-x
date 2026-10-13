"""The runtime OpenAPI schema must expose GET and POST /api/rework/ (silent-drop regression)."""

from __future__ import annotations

from collections import Counter
from typing import Any

import pytest
from drf_spectacular.generators import SchemaGenerator


@pytest.fixture(scope="module")
def runtime_schema() -> dict[str, Any]:
    return dict(SchemaGenerator().get_schema(request=None, public=True))


def test_rework_collection_route_has_get_and_post(runtime_schema):
    path = runtime_schema["paths"].get("/api/rework/")
    assert path is not None, "/api/rework/ missing from runtime schema"
    assert {"get", "post"} <= set(path)
    assert path["get"]["operationId"] == "rework_list"
    assert path["post"]["operationId"] == "rework_create"
    assert set(path["get"]["responses"]) == {"200", "400", "403"}
    assert set(path["post"]["responses"]) == {"201", "400", "403", "404", "409"}
    assert path["post"]["requestBody"]["required"] is True
    assert {p["name"] for p in path["get"]["parameters"]} == {"dataset_id", "status", "cursor"}


def test_every_rework_route_is_in_runtime_schema(runtime_schema):
    paths = runtime_schema["paths"]
    expected = {
        "/api/rework/": {"get", "post"},
        "/api/rework/{id}/": {"get"},
        "/api/rework/{id}/submitted/": {"post"},
        "/api/rework/{id}/verify/": {"post"},
    }
    for path, methods in expected.items():
        assert path in paths, f"{path} missing from runtime schema"
        assert methods <= set(paths[path]), path


def test_operation_ids_are_unique(runtime_schema):
    ids = [
        op["operationId"]
        for item in runtime_schema["paths"].values()
        for method, op in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    ]
    assert [name for name, count in Counter(ids).items() if count > 1] == []
