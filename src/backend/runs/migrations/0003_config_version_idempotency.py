from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("runs", "0002_engine_result_applicability")]

    operations = [
        migrations.AddField(
            model_name="configversion",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=128, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="configversion",
            name="request_sha256",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
