"""Django settings cho LabelX backend.

Mọi giá trị môi trường đọc từ biến môi trường / file .env (xem .env.example).
Stack theo DEC-001: Django + DRF, PostgreSQL, Celery + Redis, Object Storage (S3-compatible).
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, None),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "corsheaders",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "django_celery_beat",
    # LabelX modules (modular monolith) — thêm khi epic tương ứng được triển khai
    "guideline",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Object Storage (S3-compatible): snapshot, evidence, report/manifest.
_S3_CONNECTION = {
    "endpoint_url": env("OBJECT_STORAGE_ENDPOINT_URL", default=None),
    "access_key": env("OBJECT_STORAGE_ACCESS_KEY", default=None),
    "secret_key": env("OBJECT_STORAGE_SECRET_KEY", default=None),
    "region_name": env("OBJECT_STORAGE_REGION", default=None),
}


def _s3_storage(bucket: str, *, content_addressed: bool) -> dict[str, object]:
    # content_addressed: khoá là sha256 nội dung (docs/11-integrations/object-storage.md mục 3),
    # ghi lại cùng khoá là ghi cùng nội dung nên phải overwrite — file_overwrite=False sẽ tự đổi
    # tên file và phá khoá theo hash. Bucket còn lại giữ False để không ghi đè nhầm.
    return {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {**_S3_CONNECTION, "bucket_name": bucket, "file_overwrite": content_addressed},
    }


STORAGES = {
    "default": _s3_storage(
        env("OBJECT_STORAGE_BUCKET", default="labelx-evidence"), content_addressed=False
    ),
    "snapshots": _s3_storage(
        env("OBJECT_STORAGE_BUCKET_SNAPSHOTS", default="labelx-snapshots"), content_addressed=True
    ),
    "evidence": _s3_storage(
        env("OBJECT_STORAGE_BUCKET_EVIDENCE", default="labelx-evidence"), content_addressed=True
    ),
    "reports": _s3_storage(
        env("OBJECT_STORAGE_BUCKET_REPORTS", default="labelx-reports"), content_addressed=False
    ),
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# DRF — quyền project/job kiểm ở API (B-12); mặc định yêu cầu đăng nhập.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.CursorPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "LabelX API",
    "DESCRIPTION": "Quality Control cho annotation CVAT",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
# Frontend khác origin (dev: :3000 gọi API :8000) gửi POST kèm session cookie phải qua kiểm Origin
# của CSRF; mặc định tin cùng danh sách với CORS.
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS") or CORS_ALLOWED_ORIGINS

# Celery — task phải idempotent dù có retry; timeout đặt riêng theo loại task sau đo pilot.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# CVAT adapter — chỉ đọc job/meta/annotation/media bằng service account (B-18).
CVAT_BASE_URL = env("CVAT_BASE_URL", default="")
CVAT_SERVICE_TOKEN = env("CVAT_SERVICE_TOKEN", default="")
