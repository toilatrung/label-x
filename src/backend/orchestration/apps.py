from django.apps import AppConfig


class OrchestrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orchestration"
    verbose_name = "QC run orchestration"

    def ready(self) -> None:
        from orchestration.builtin_engines import register_builtin_engines
        from orchestration.registry import registry

        register_builtin_engines(registry)
