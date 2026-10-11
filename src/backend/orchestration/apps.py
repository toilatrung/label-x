from django.apps import AppConfig


class OrchestrationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orchestration"
    verbose_name = "QC run orchestration"

    def ready(self) -> None:
        from engines.registration import register_structural_engines
        from orchestration.builtin_engines import register_builtin_engines
        from orchestration.registry import registry

        # Cả hai hàm idempotent: ready() có thể chạy nhiều lần trong tooling/test.
        register_builtin_engines(registry)
        register_structural_engines(registry)
        # Worker Celery chỉ autodiscover `orchestration.tasks`: nạp dispatch để đăng ký
        # run_work_unit/redispatch_pending.
        import orchestration.dispatch  # noqa: F401
