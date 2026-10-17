"""Liveness is independent of PostgreSQL, Redis, S3 and the remote GPU worker."""

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.urls import path

from .urls import urlpatterns as application_urls


@transaction.non_atomic_requests
def healthz(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


urlpatterns = [path("healthz/", healthz, name="healthz"), *application_urls]
