import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0004_reworkrequest_reworkrecheck_reworkverification_and_more"),
        ("runs", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="FinalRunVerification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "final_run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="verification_lineage",
                        to="runs.qcrun",
                    ),
                ),
                (
                    "verification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="final_run_links",
                        to="review.reworkverification",
                    ),
                ),
            ],
            options={"db_table": "final_run_link", "ordering": ["verification_id"]},
        ),
        migrations.AddConstraint(
            model_name="finalrunverification",
            constraint=models.UniqueConstraint(
                fields=("final_run", "verification"),
                name="final_run_link_unique_verification",
            ),
        ),
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION final_run_link_reject_mutation() RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'final_run_link is append-only';
                END;
                $$ LANGUAGE plpgsql;
                CREATE TRIGGER final_run_link_append_only
                BEFORE UPDATE OR DELETE ON final_run_link
                FOR EACH ROW EXECUTE FUNCTION final_run_link_reject_mutation();
            """,
            reverse_sql="""
                DROP TRIGGER IF EXISTS final_run_link_append_only ON final_run_link;
                DROP FUNCTION IF EXISTS final_run_link_reject_mutation();
            """,
        ),
    ]
