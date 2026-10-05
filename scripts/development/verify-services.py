"""Read-only checks of actual Django connections, including all three S3 buckets."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

try:
    import django

    django.setup()
    from django.conf import settings
    from django.core.files.storage import storages
    from django.db import connection
    from redis import Redis
    from botocore.config import Config

    connection.settings_dict.setdefault("OPTIONS", {})["connect_timeout"] = 5
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)
    for url in (settings.CELERY_BROKER_URL, settings.CELERY_RESULT_BACKEND):
        client = Redis.from_url(url, socket_connect_timeout=5, socket_timeout=5)
        try:
            assert client.ping()
        finally:
            client.close()
    for name in ("snapshots", "evidence", "reports"):
        storage = storages[name]
        options = settings.STORAGES[name]["OPTIONS"]
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=options["endpoint_url"],
            aws_access_key_id=options["access_key"],
            aws_secret_access_key=options["secret_key"],
            region_name=options["region_name"],
            config=Config(connect_timeout=5, read_timeout=5, retries={"max_attempts": 0}),
        )
        try:
            client.head_bucket(Bucket=storage.bucket_name)
        finally:
            client.close()
    print("PostgreSQL, Redis and three S3 buckets: reachable through Django settings")
except Exception:
    # Driver exception messages can contain credentials. Do not print them.
    print("Service verification failed. Check local containers and private .env settings.", file=sys.stderr)
    sys.exit(1)
