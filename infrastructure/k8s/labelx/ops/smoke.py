"""Verify live HTTPS and deployment dependencies; never claims MVP acceptance."""
import hashlib
import http.cookiejar
import json
import os
import re
import secrets
import urllib.error
import urllib.request


def public_smoke():
    origin = "https://label-x.williamtrinh.online"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(path, expected=200, **kwargs):
        req = urllib.request.Request(origin + path, **kwargs)
        try:
            response = opener.open(req, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        if response.status != expected or not response.url.startswith(origin + "/"):
            raise RuntimeError(f"Unexpected HTTPS response: {path}: {response.status}")
        return response

    login = request("/login").read().decode()
    asset = re.search(r'(?:src|href)="([^"<>]*/_next/static/[^"<>]+)"', login)
    if not asset:
        raise RuntimeError("Next.js static asset missing")
    request(asset[1].replace("&amp;", "&"))
    request("/labelx-logo.png")
    csrf = request("/api/auth/csrf/", 204)
    cookie = next((cookie for cookie in jar if cookie.name == "labelx_csrftoken"), None)
    if cookie is None or not cookie.secure or "max-age=" not in csrf.headers.get("Strict-Transport-Security", ""):
        raise RuntimeError("Secure CSRF cookie or HSTS missing")
    bad = request("/api/auth/login", 400, method="POST",
        headers={"Content-Type": "application/json", "X-CSRFToken": cookie.value, "Origin": origin},
        data=json.dumps({"username": "labelx-smoke-" + secrets.token_hex(8), "password": secrets.token_hex(24)}).encode())
    if json.load(bad).get("code") != "INVALID_CREDENTIALS":
        raise RuntimeError("Login did not reach real Django authentication")
    request("/api/auth/mock-users/", 404)
    request("/healthz/")
    print("PASS public TLS trust, login/assets, CSRF/HSTS, real Django proxy, no mock login")


def dependencies():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.production")
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import connection
    from config.celery import app
    from storage.client import ObjectStorage
    import redis

    call_command("migrate", check=True)
    call_command("check", deploy=True, tags=["database"])
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = current_user")
        if any(cursor.fetchone()):
            raise RuntimeError("Application DB role has administrative privileges")
    redis.Redis.from_url(os.environ["CELERY_BROKER_URL"], socket_timeout=5).ping()
    if not app.control.ping(timeout=5):
        raise RuntimeError("CPU Celery worker did not answer through Redis")
    for alias in ("default", "snapshots", "evidence", "reports"):
        storage = ObjectStorage.from_django_settings(alias)
        key = "ops-smoke/" + secrets.token_hex(16)
        payload = secrets.token_bytes(64)
        try:
            storage._client.put_object(Bucket=storage.bucket, Key=key, Body=payload)
            downloaded = storage._client.get_object(Bucket=storage.bucket, Key=key)["Body"].read()
            if hashlib.sha256(downloaded).digest() != hashlib.sha256(payload).digest():
                raise RuntimeError("S3 read/write checksum mismatch")
        finally:
            storage._client.delete_object(Bucket=storage.bucket, Key=key)
    print("PASS migrations, restricted DB role, Redis, CPU Celery, S3 put/get/delete")
    print("UNVERIFIED: GPU/CVAT/VLM end-to-end, evaluation, NFR and full MVP evidence; issues remain open")


if __name__ == "__main__":
    try:
        if os.environ.get("DATABASE_URL"):
            dependencies()
        public_smoke()
    except Exception as error:
        print(f"FAIL smoke: {type(error).__name__}", flush=True)
        raise SystemExit(1) from None
