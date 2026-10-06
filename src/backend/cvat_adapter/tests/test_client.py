import httpx

from cvat_adapter.client import CvatReadClient


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
