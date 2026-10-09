import ast
from pathlib import Path

import httpx
import pytest

from cvat_adapter.client import CvatReadClient, CvatWriteBlocked


def test_adapter_exposes_no_write_method() -> None:
    public_names = {name for name in dir(CvatReadClient) if not name.startswith("_")}
    assert public_names.isdisjoint({"post", "put", "patch", "delete", "create", "update"})


def test_client_only_gets_and_uses_bearer_token() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"version": 1, "shapes": []})

    with CvatReadClient(
        "http://cvat.example.test/",
        "secret-read-token",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.get_job_annotations(42) == {"version": 1, "shapes": []}

    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/jobs/42/annotations"
    assert requests[0].headers["Authorization"] == "Bearer secret-read-token"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_private_http_client_blocks_writes_before_transport(method: str) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    with CvatReadClient(
        "http://cvat.example.test", "token", transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(CvatWriteBlocked):
            getattr(client._client, method)("http://cvat.example.test/api/jobs")
    assert requests == []


def test_list_jobs_follows_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params["page"]
        if page == "1":
            return httpx.Response(200, json={"results": [{"id": 1}], "next": "page-2"})
        return httpx.Response(200, json={"results": [{"id": 2}], "next": None})

    with CvatReadClient(
        "http://cvat.example.test",
        "token",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.list_jobs(task_id=9) == [{"id": 1}, {"id": 2}]


def test_list_jobs_stops_on_empty_page_even_if_next_is_present() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": [], "next": "broken-next"})

    with CvatReadClient(
        "http://cvat.example.test", "token", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.list_jobs() == []
    assert calls == 1


def test_frame_download_and_deep_links_are_read_only() -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"jpeg", headers={"content-type": "image/jpeg"})

    with CvatReadClient(
        "http://cvat.example.test", "token", transport=httpx.MockTransport(handler)
    ) as client:
        assert client.get_job_frame(12, 7) == (b"jpeg", "image/jpeg")
        assert client.job_url(5, 12) == "http://cvat.example.test/tasks/5/jobs/12"
        assert client.job_url(5, 12, frame_index=7).endswith("/tasks/5/jobs/12?frame=7")

    assert [request.method for request in requests] == ["GET"]
    assert dict(requests[0].url.params) == {
        "type": "frame",
        "number": "7",
        "quality": "original",
    }


def test_only_adapter_constructs_httpx_client_in_backend() -> None:
    backend = Path(__file__).resolve().parents[2]
    offenders = []
    for path in backend.rglob("*.py"):
        relative = path.relative_to(backend)
        if (
            "tests" in relative.parts
            or path.name == "client.py"
            or any(part.startswith(".") for part in relative.parts)
        ):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module_aliases = {"httpx"}
        client_aliases: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                module_aliases.update(
                    alias.asname or alias.name for alias in node.names if alias.name == "httpx"
                )
            elif isinstance(node, ast.ImportFrom) and node.module == "httpx":
                client_aliases.update(
                    alias.asname or alias.name for alias in node.names if alias.name == "Client"
                )
        creates_client = any(
            isinstance(node, ast.Call)
            and (
                (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Client"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in module_aliases
                )
                or (isinstance(node.func, ast.Name) and node.func.id in client_aliases)
            )
            for node in ast.walk(tree)
        )
        if creates_client:
            offenders.append(relative.as_posix())
    assert offenders == []
