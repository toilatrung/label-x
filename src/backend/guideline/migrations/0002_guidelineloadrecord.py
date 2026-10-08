import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("guideline", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GuidelineLoadRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("actor_username", models.CharField(max_length=150)),
                ("attempted_at", models.DateTimeField(auto_now_add=True)),
                ("file_checksum", models.CharField(max_length=64)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("result", models.CharField(choices=[("accepted", "Accepted"), ("rejected", "Rejected"), ("skipped", "Skipped")], max_length=16)),
                ("errors", models.JSONField(default=list)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="guideline_loads", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-attempted_at", "-id"]},
        ),
    ]
