from django.conf import settings


def test_csrf_trusts_frontend_origins():
    for origin in settings.CORS_ALLOWED_ORIGINS:
        assert origin in settings.CSRF_TRUSTED_ORIGINS


def test_content_addressed_buckets_overwrite_instead_of_renaming():
    storages = settings.STORAGES
    assert storages["snapshots"]["OPTIONS"]["file_overwrite"] is True
    assert storages["evidence"]["OPTIONS"]["file_overwrite"] is True
    assert storages["reports"]["OPTIONS"]["file_overwrite"] is False
    assert storages["default"]["OPTIONS"]["file_overwrite"] is False


def test_cors_preflight_allows_idempotency_key(client, settings):
    """Trình duyệt gửi POST tạo snapshot/config/run kèm Idempotency-Key: preflight phải cho phép."""
    origin = settings.CORS_ALLOWED_ORIGINS[0] if settings.CORS_ALLOWED_ORIGINS else None
    if origin is None:
        settings.CORS_ALLOWED_ORIGINS = origin = "http://localhost:3000"
    response = client.options(
        "/api/runs/",
        HTTP_ORIGIN=origin,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,idempotency-key,x-csrftoken",
    )
    allowed = {h.strip() for h in response["access-control-allow-headers"].split(",")}
    assert {"idempotency-key", "x-csrftoken", "content-type"} <= allowed
