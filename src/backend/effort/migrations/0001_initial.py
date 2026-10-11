# Generated manually for T-036.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("review", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EffortEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("client_event_id", models.UUIDField(unique=True)),
                ("dataset_id", models.PositiveBigIntegerField(db_index=True)),
                (
                    "activity",
                    models.CharField(
                        choices=[
                            ("view_frame", "View frame"),
                            ("review_issue", "Review issue"),
                            ("adjudicate", "Adjudicate"),
                            ("recheck_verify", "Recheck / verify"),
                        ],
                        max_length=32,
                    ),
                ),
                ("started_at", models.DateTimeField()),
                ("ended_at", models.DateTimeField()),
                ("active_ms", models.PositiveBigIntegerField()),
                ("config_source", models.CharField(max_length=255)),
                ("t_idle_seconds", models.PositiveIntegerField(blank=True, null=True)),
                ("config_snapshot", models.JSONField(default=dict)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="effort_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "frame",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="effort_events",
                        to="review.framereview",
                    ),
                ),
            ],
            options={"db_table": "effort_event", "ordering": ["started_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="effortevent",
            index=models.Index(fields=["actor", "started_at"], name="effort_actor_start_idx"),
        ),
        migrations.AddIndex(
            model_name="effortevent",
            index=models.Index(fields=["frame", "started_at"], name="effort_frame_start_idx"),
        ),
        migrations.AddConstraint(
            model_name="effortevent",
            constraint=models.CheckConstraint(
                condition=models.Q(("ended_at__gt", models.F("started_at"))),
                name="effort_event_positive_interval",
            ),
        ),
    ]
