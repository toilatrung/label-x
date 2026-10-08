import io
import json
import logging

from django.http import HttpResponse
from django.test import RequestFactory

import config.middleware as middleware_module
from config.logging import JsonFormatter, RequestContextFilter, SecretRedactionFilter, log_context
from config.middleware import RequestIDMiddleware


def _json_logger(name: str, stream: io.StringIO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestContextFilter())
    handler.addFilter(SecretRedactionFilter())
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    return logger


def test_error_request_log_has_request_id_and_redacts_secrets(monkeypatch):
    stream = io.StringIO()
    logger = _json_logger("test.labelx.request", stream)
    fake_token = "fake-cvat-token-T015"
    fake_password = "fake-password-T015"

    def failing_response(_request):
        logger.error(
            "CVAT failed Authorization: Bearer %s password=%s",
            fake_token,
            fake_password,
            extra={
                "headers": {"Cookie": f"sessionid={fake_token}"},
                "cvat_service_token": fake_token,
            },
        )
        return HttpResponse(status=500)

    monkeypatch.setattr(middleware_module, "request_logger", logger)
    request = RequestFactory().get(
        "/api/failure/",
        HTTP_X_REQUEST_ID="request-t015-test",
        HTTP_AUTHORIZATION=f"Bearer {fake_token}",
        HTTP_COOKIE=f"sessionid={fake_token}",
    )

    response = RequestIDMiddleware(failing_response)(request)
    output = stream.getvalue()
    records = [json.loads(line) for line in output.splitlines()]

    assert response.status_code == 500
    assert response["X-Request-ID"] == "request-t015-test"
    assert records
    assert all(record["request_id"] == "request-t015-test" for record in records)
    assert any(record.get("event") == "request.completed" for record in records)
    assert fake_token not in output
    assert fake_password not in output
    assert "[REDACTED]" in output


def test_run_and_snapshot_context_are_structured_and_secrets_are_recursive():
    stream = io.StringIO()
    logger = _json_logger("test.labelx.context", stream)
    fake_token = "nested-fake-token-T015"

    with log_context(request_id="request-42", run_id=42, snapshot_id="snapshot-9"):
        logger.info(
            "worker completed",
            extra={"payload": {"token": fake_token, "safe": "kept"}},
        )

    output = stream.getvalue()
    record = json.loads(output)
    assert record["request_id"] == "request-42"
    assert record["run_id"] == "42"
    assert record["snapshot_id"] == "snapshot-9"
    assert record["payload"] == {"token": "[REDACTED]", "safe": "kept"}
    assert fake_token not in output
