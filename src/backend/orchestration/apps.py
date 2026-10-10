from django.apps import AppConfig


class OrchestrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orchestration"
    verbose_name = "QC run orchestration"

    def ready(self) -> None:
        from engines.registration import register_structural_engines

        register_structural_engines()
