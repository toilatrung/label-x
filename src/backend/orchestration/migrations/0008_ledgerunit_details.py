from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("orchestration", "0007_evaluation")]

    operations = [
        migrations.AddField(
            model_name="ledgerunit", name="details", field=models.JSONField(default=dict)
        ),
    ]
