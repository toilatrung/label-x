from django.apps import AppConfig


class CvatAdapterConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "cvat_adapter"
    verbose_name = "CVAT read-only adapter"
