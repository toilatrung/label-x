"""Django app config for QC Run, Sharding and Engine Lifecycle."""

from django.apps import AppConfig


class RunsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "runs"
    verbose_name = "QC Runs and Shards"
