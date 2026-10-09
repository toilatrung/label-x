from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "audit"

    def ready(self) -> None:
        from audit import checks  # noqa: F401  (registers the deployment check)
