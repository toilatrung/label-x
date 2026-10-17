"""Container settings shared by Gunicorn, CPU workers, beat and migration jobs."""

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403
from .settings import ALLOWED_HOSTS, DEBUG, MIDDLEWARE, STORAGES, env

if DEBUG:
    raise ImproperlyConfigured("Production requires DJANGO_DEBUG=False.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Production requires explicit DJANGO_ALLOWED_HOSTS.")

MIDDLEWARE = [MIDDLEWARE[0], "whitenoise.middleware.WhiteNoiseMiddleware", *MIDDLEWARE[1:]]
STATIC_URL = "/static/"
STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
ROOT_URLCONF = "config.production_urls"

# Only expose the backend behind a proxy which overwrites X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
