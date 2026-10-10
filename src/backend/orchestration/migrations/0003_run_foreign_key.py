"""run_id số nguyên -> FK runs.QCRun, giữ nguyên cột `run_id`, tên và cột của constraint.

Chỉ thêm ràng buộc FK ở DB; state đổi field `run_id` thành `run` (attname vẫn là `run_id`).
"""

import django.db.models.deletion
from django.db import migrations, models

TABLES = ("shardcommit", "candidaterecord", "ledgerunit")

CONSTRAINTS: dict[str, list[tuple[str, tuple[str, ...], tuple[str, ...]]]] = {
    "ledgerunit": [
        (
            "uniq_ledger_unit",
            ("run", "engine", "kind", "cvat_task_id", "frame_number"),
            ("run_id", "engine", "kind", "cvat_task_id", "frame_number"),
        )
    ],
    "shardcommit": [
        (
            "uniq_shard_per_run_engine",
            ("run", "engine", "shard_index"),
            ("run_id", "engine", "shard_index"),
        ),
        ("uniq_shard_key_per_run", ("run", "idempotency_key"), ("run_id", "idempotency_key")),
    ],
    "candidaterecord": [
        ("uniq_candidate_dedup", ("run", "dedup_key"), ("run_id", "dedup_key")),
    ],
}


def fk_sql(table: str) -> tuple[str, str]:
    name = f"orchestration_{table}_run_id_fk_qc_run"
    return (
        f'ALTER TABLE "orchestration_{table}" ADD CONSTRAINT "{name}" '
        'FOREIGN KEY ("run_id") REFERENCES "qc_run" ("id") DEFERRABLE INITIALLY DEFERRED',
        f'ALTER TABLE "orchestration_{table}" DROP CONSTRAINT "{name}"',
    )


def state_operations() -> list[migrations.operations.base.Operation]:
    ops: list[migrations.operations.base.Operation] = []
    for table, items in CONSTRAINTS.items():
        for name, _new, _old in items:
            ops.append(migrations.RemoveConstraint(model_name=table, name=name))
    for table in TABLES:
        ops.append(migrations.RemoveField(model_name=table, name="run_id"))
        ops.append(
            migrations.AddField(
                model_name=table,
                name="run",
                field=models.ForeignKey(
                    db_column="run_id",
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+",
                    to="runs.qcrun",
                    default=0,
                ),
                preserve_default=False,
            )
        )
    for table, items in CONSTRAINTS.items():
        for name, new, _old in items:
            ops.append(
                migrations.AddConstraint(
                    model_name=table,
                    constraint=models.UniqueConstraint(fields=new, name=name),
                )
            )
    return ops


class Migration(migrations.Migration):
    dependencies = [
        ("orchestration", "0002_shard_key_per_run"),
        ("runs", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=state_operations(),
            database_operations=[
                migrations.RunSQL(sql=forward, reverse_sql=backward)
                for forward, backward in (fk_sql(t) for t in TABLES)
            ],
        )
    ]
