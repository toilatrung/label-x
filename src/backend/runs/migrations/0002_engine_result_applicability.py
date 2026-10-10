from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("runs", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="engineresult",
            name="unit",
            field=models.CharField(default="frame", max_length=16),
        ),
        migrations.AddField(
            model_name="engineresult",
            name="applicability_version",
            field=models.CharField(default="1.0.0", max_length=64),
        ),
    ]
