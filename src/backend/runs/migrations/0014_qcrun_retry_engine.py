from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("runs", "0013_vlm_three_retries")]

    operations = [
        migrations.AddField(
            model_name="qcrun",
            name="retry_engine",
            field=models.CharField(max_length=64, blank=True, default=""),
        ),
    ]
