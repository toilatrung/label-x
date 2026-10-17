import django.db.models.deletion
from django.apps.registry import Apps
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor


def backfill_submission(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    recheck_model = apps.get_model("review", "ReworkRecheck")
    for recheck in recheck_model.objects.select_related("rework"):
        recheck.idempotency_key = recheck.rework.submission_idempotency_key
        recheck.request_hash = recheck.rework.submission_request_hash
        recheck.save(update_fields=["idempotency_key", "request_hash"])


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0005_finalrunverification"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reworkrecheck",
            name="rework",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="rechecks",
                to="review.reworkrequest",
            ),
        ),
        migrations.AddField(
            model_name="reworkrecheck",
            name="round",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="reworkrecheck",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=36, null=True),
        ),
        migrations.AddField(
            model_name="reworkrecheck",
            name="request_hash",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AlterModelOptions(
            name="reworkrecheck",
            options={"ordering": ["rework_id", "round"]},
        ),
        migrations.RunPython(backfill_submission, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="reworkrecheck",
            constraint=models.UniqueConstraint(
                fields=("rework", "round"), name="rework_recheck_unique_round"
            ),
        ),
        migrations.AddConstraint(
            model_name="reworkrecheck",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("rework", "idempotency_key"),
                name="rework_recheck_idempotency",
            ),
        ),
    ]
