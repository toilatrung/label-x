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
