import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0006_reworkrecheck_rounds"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GuidelineGap",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("rule_id", models.CharField(max_length=32)),
                ("description", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("resolved", "Resolved")],
                        default="open",
                        max_length=16,
                    ),
                ),
                ("guideline_version", models.CharField(blank=True, max_length=128, null=True)),
                ("resolved_in_version", models.CharField(blank=True, max_length=128, null=True)),
                ("idempotency_key", models.CharField(blank=True, max_length=36, null=True)),
                ("request_hash", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL
                    ),
                ),
                (
                    "issue",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guideline_gaps",
                        to="review.issue",
                    ),
                ),
            ],
            options={"db_table": "review_guideline_gap", "ordering": ["-created_at", "-pk"]},
        ),
        migrations.AddConstraint(
            model_name="guidelinegap",
            constraint=models.UniqueConstraint(
                condition=models.Q(("issue__isnull", False), ("status", "open")),
                fields=("issue", "rule_id"),
                name="guideline_gap_one_open_issue_rule",
            ),
        ),
        migrations.AddConstraint(
            model_name="guidelinegap",
            constraint=models.UniqueConstraint(
                condition=models.Q(("issue__isnull", True), ("status", "open")),
                fields=("rule_id",),
                name="guideline_gap_one_open_independent_rule",
            ),
        ),
        migrations.AddConstraint(
            model_name="guidelinegap",
            constraint=models.UniqueConstraint(
                condition=models.Q(("idempotency_key__isnull", False)),
                fields=("created_by", "idempotency_key"),
                name="guideline_gap_create_idempotency",
            ),
        ),
    ]
