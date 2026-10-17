# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0 PYTHONDONTWRITEBYTECODE=1
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY . .
# Public build-only placeholder: no deployment credentials, database or S3 are needed.
RUN DJANGO_SETTINGS_MODULE=config.production DJANGO_DEBUG=False \
    DJANGO_SECRET_KEY=collectstatic-build-only-placeholder-never-a-runtime-secret \
    DJANGO_ALLOWED_HOSTS=localhost DATABASE_URL=sqlite:///:memory: \
    .venv/bin/python manage.py collectstatic --noinput

FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.production DJANGO_DEBUG=False
LABEL org.opencontainers.image.source="https://github.com/toilatrung/label-x" \
      org.opencontainers.image.title="LabelX backend (API, CPU worker, beat, migration)"
RUN groupadd --gid 10001 labelx && useradd --uid 10001 --gid 10001 --create-home labelx
COPY --from=build /app /app
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8000", "--worker-class=gthread", "--workers=2", "--threads=2", "--timeout=300", "--graceful-timeout=30", "--access-logfile=-", "--error-logfile=-"]
