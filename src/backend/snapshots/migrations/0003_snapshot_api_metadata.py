from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("snapshots", "0002_serialize_snapshot_mutations")]

    operations = [
        migrations.AddField(
            model_name="snapshot",
            name="drift_jobs",
            field=models.JSONField(default=list),
        ),
        migrations.AddField(
            model_name="snapshot",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="snapshot",
            name="request_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
