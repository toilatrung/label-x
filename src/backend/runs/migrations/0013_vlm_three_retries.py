"""Use three retries for new runs while retaining pinned connection revisions."""

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def upgrade_current_connection(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    alias = schema_editor.connection.alias
    selection_model = apps.get_model("runs", "VlmConfiguration")
    connection_model = apps.get_model("runs", "VlmConnection")
    selection = selection_model.objects.using(alias).select_for_update().filter(pk=1).first()
    if selection is None or selection.connection_id is None:
        return
    previous = connection_model.objects.using(alias).get(pk=selection.connection_id)
    if previous.config.get("max_attempts") != 3:
        return
    connection = connection_model.objects.using(alias).create(
        config={**previous.config, "max_attempts": 4},
        encrypted_api_key=previous.encrypted_api_key,
        confidence_threshold=previous.confidence_threshold,
    )
    selection.connection_id = connection.pk
    selection.save(using=alias, update_fields=["connection"])


class Migration(migrations.Migration):
    dependencies = [("runs", "0012_merge_20261014_2205")]

    # Published configs and completed evidence may reference either revision after rollout.
    operations = [migrations.RunPython(upgrade_current_connection, migrations.RunPython.noop)]
