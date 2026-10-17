"""Validate real production startup in subprocesses, without connecting to a database."""

import json
import os
import subprocess
import sys
import unittest


class ProductionSettingsTests(unittest.TestCase):
    def run_settings(self, script: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "DJANGO_SETTINGS_MODULE": "config.production",
            "DJANGO_DEBUG": "False",
            "DJANGO_SECRET_KEY": "test-only-production-settings-placeholder-never-a-real-secret",
            "DJANGO_ALLOWED_HOSTS": "localhost",
            "DATABASE_URL": "sqlite:///:memory:",
            "AWS_EC2_METADATA_DISABLED": "true",
            **overrides,
        }
        return subprocess.run(
            [sys.executable, "-c", script], env=env, text=True, capture_output=True, check=False
        )

    def test_production_security_and_static_configuration(self):
        result = self.run_settings("""
import json
from django.conf import settings as s
print(json.dumps({
    'debug': s.DEBUG, 'middleware': s.MIDDLEWARE[:2],
    'static': s.STORAGES['staticfiles']['BACKEND'], 'static_url': s.STATIC_URL,
    'https': s.SECURE_SSL_REDIRECT, 'session': s.SESSION_COOKIE_SECURE,
    'csrf': s.CSRF_COOKIE_SECURE, 'proxy': s.SECURE_PROXY_SSL_HEADER,
}))
""")
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = json.loads(result.stdout)
        self.assertFalse(actual["debug"])
        self.assertEqual(
            actual["middleware"],
            [
                "django.middleware.security.SecurityMiddleware",
                "whitenoise.middleware.WhiteNoiseMiddleware",
            ],
        )
        self.assertEqual(
            actual["static"], "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
        self.assertEqual(actual["static_url"], "/static/")
        for key in ("https", "session", "csrf"):
            self.assertTrue(actual[key])
        self.assertEqual(actual["proxy"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_debug_or_missing_explicit_hosts_fails_closed(self):
        for overrides in (
            {"DJANGO_DEBUG": "True"},
            {"DJANGO_ALLOWED_HOSTS": "*"},
            {"DJANGO_ALLOWED_HOSTS": ""},
        ):
            with self.subTest(overrides=overrides):
                result = self.run_settings("from config import production", **overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ImproperlyConfigured", result.stderr)

    def test_http_liveness_does_not_redirect_or_query_the_database(self):
        result = self.run_settings("""
import django
django.setup()
from django.db import connection
from django.test import Client
def reject_query(execute, sql, params, many, context):
    raise AssertionError('Liveness must not query the database')
with connection.execute_wrapper(reject_query):
    response = Client().get('/healthz/', HTTP_HOST='localhost')
    assert response.status_code == 200, response.status_code
    assert response.json() == {'status': 'ok'}
""")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
