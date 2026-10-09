# Generated for T-031: persisted source-separated run rankings.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("runs", "0001_initial"),
        ("snapshots", "0003_snapshot_api_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="RunRanking",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("risk", "Risk"),
                            ("random_audit", "Random audit"),
                            ("random_control", "Random control"),
                            ("annotation_count_control", "Annotation count control"),
                            ("max_confidence_control", "Max confidence control"),
                        ],
                        max_length=32,
                    ),
                ),
                ("seed", models.BigIntegerField()),
                ("score_version", models.CharField(max_length=64)),
                ("content_hash", models.CharField(max_length=64)),
                ("ranking_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rankings",
                        to="runs.qcrun",
                    ),
                ),
            ],
            options={"db_table": "run_ranking", "ordering": ["source"]},
        ),
        migrations.CreateModel(
            name="RunRankingEntry",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("rank", models.PositiveIntegerField()),
                ("score", models.DecimalField(decimal_places=12, max_digits=30)),
                ("baseline_score", models.DecimalField(decimal_places=12, max_digits=30)),
                ("missing_evidence", models.BooleanField(default=False)),
                ("issue_counts", models.JSONField(default=dict)),
                ("explanation", models.JSONField(default=dict)),
                ("tie_break_hash", models.CharField(max_length=64)),
                (
                    "source_value",
                    models.DecimalField(blank=True, decimal_places=12, max_digits=30, null=True),
                ),
                (
                    "ranking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="runs.runranking",
                    ),
                ),
                (
                    "snapshot_frame",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ranking_entries",
                        to="snapshots.snapshotframe",
                    ),
                ),
            ],
            options={"db_table": "run_ranking_entry", "ordering": ["rank"]},
        ),
        migrations.AddConstraint(
            model_name="runranking",
            constraint=models.UniqueConstraint(
                fields=("run", "source"), name="run_ranking_unique_run_source"
            ),
        ),
        migrations.AddIndex(
            model_name="runrankingentry",
            index=models.Index(fields=["ranking", "rank"], name="run_rank_entry_order_idx"),
        ),
        migrations.AddConstraint(
            model_name="runrankingentry",
            constraint=models.UniqueConstraint(
                fields=("ranking", "snapshot_frame"), name="run_rank_entry_unique_frame"
            ),
        ),
        migrations.AddConstraint(
            model_name="runrankingentry",
            constraint=models.UniqueConstraint(
                fields=("ranking", "rank"), name="run_rank_entry_unique_rank"
            ),
        ),
        migrations.AddConstraint(
            model_name="runrankingentry",
            constraint=models.CheckConstraint(
                condition=models.Q(("rank__gte", 1)), name="run_rank_entry_rank_positive"
            ),
        ),
    ]
