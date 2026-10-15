"""Local LabelX demo with a simulated read-only CVAT source; no CVAT installation.

Run `python scripts/development/demo.py serve` for the source on port 8091,
and use the backend Python environment with `... demo.py seed` to add demo data.
Only demo-prefixed users and dataset 99001 are created; existing data is retained.
Seeding requires DEBUG, a database with 'demo' in its name, and
LABELX_DEMO_PASSWORD when creating the demo account. LABELX_DEMO_IMAGE can
point to a local 1280x720 demo JPEG instead of the default cached BDD100K frame.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]
DATASET = 99001
TASK = 99011
JOB_IDS = (99021, 99022, 99023)
STAMP = "2026-10-15T04:00:00Z"
IMAGE = Path(
    os.environ.get(
        "LABELX_DEMO_IMAGE", str(ROOT / ".cache/bdd100k-validation/b1ceb32e-3f481b43.jpg")
    )
)
LABELS = [
    {"id": 1, "name": "car", "color": "#58d68d", "attributes": []},
    {"id": 2, "name": "truck", "color": "#f1948a", "attributes": []},
]


def annotations(job_id):
    boxes = (
        [190, 270, 272, 352],
        [280, 277, 362, 350],
        [380, 283, 466, 351],
        [477, 270, 562, 354],
        [625, 280, 748, 356],
    )
    return {
        "version": 1,
        "tags": [],
        "tracks": [],
        "shapes": [
            {
                "id": job_id * 100 + frame * 10 + i,
                "frame": frame,
                "type": "rectangle",
                "label_id": 2 if i == 0 else 1,
                "points": list(box),
                "rotation": 0,
                "occluded": False,
                "outside": False,
                "z_order": i,
                "attributes": [],
            }
            for frame in range((job_id - JOB_IDS[0]) * 2, (job_id - JOB_IDS[0]) * 2 + 2)
            for i, box in enumerate(boxes)
        ],
    }


def job(job_id):
    start = (job_id - JOB_IDS[0]) * 2
    return {
        "id": job_id,
        "task_id": TASK,
        "type": "annotation",
        "start_frame": start,
        "stop_frame": start + 1,
        "frame_count": 2,
        "updated_date": STAMP,
        "stage": "annotation" if job_id == JOB_IDS[-1] else "validation",
        "state": "in_progress" if job_id == JOB_IDS[-1] else "completed",
        "assignee": {"id": 99002, "username": "demo_annotator"},
    }


class DemoSource(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        query = parse_qs(parsed.query)
        project = {"id": DATASET, "name": "DEMO — Review giao thông (CVAT giả lập)"}
        task = {
            "id": TASK,
            "name": "DEMO — Bãi đỗ xe",
            "project_id": DATASET,
            "size": 6,
            "updated_date": STAMP,
            "mode": "annotation",
        }
        if path == "/api/projects":
            payload = [project]
        elif path == f"/api/projects/{DATASET}":
            payload = project
        elif path == "/api/tasks":
            payload = [task]
        elif path == f"/api/tasks/{TASK}":
            payload = task
        elif path == "/api/labels":
            payload = LABELS
        elif path == "/api/jobs":
            payload = [job(i) for i in JOB_IDS]
        elif path == "/api/server/about":
            payload = {"name": "LabelX demo source", "version": "demo"}
        elif path.startswith("/api/jobs/"):
            parts = path.split("/")
            try:
                job_id = int(parts[3])
                assert job_id in JOB_IDS
            except (ValueError, AssertionError):
                self.send_error(404)
                return
            suffix = "/".join(parts[4:])
            if suffix == "annotations":
                payload = annotations(job_id)
            elif suffix == "data/meta":
                payload = {
                    "size": 2,
                    "start_frame": job(job_id)["start_frame"],
                    "stop_frame": job(job_id)["stop_frame"],
                    "frame_filter": "",
                    "frames": [
                        {"width": 1280, "height": 720, "name": f"demo-{i}.jpg"} for i in range(2)
                    ],
                    "deleted_frames": [],
                }
            elif suffix == "data":
                return self.reply(IMAGE.read_bytes(), "image/jpeg")
            else:
                payload = job(job_id)
        elif path.startswith("/tasks/"):
            return self.reply(
                "<h1>CVAT giả lập — Demo LabelX</h1>"
                "<p>Đây là dữ liệu minh họa, không phải CVAT đã cài.</p>"
                "<p>Quay lại LabelX để kiểm tra annotation và đề xuất mô hình.</p>".encode(),
                "text/html; charset=utf-8",
            )
        else:
            self.send_error(404)
            return
        if isinstance(payload, list):
            if query.get("page", ["1"])[0] != "1":
                payload = []
            payload = {"count": len(payload), "next": None, "previous": None, "results": payload}
        self.reply(json.dumps(payload, ensure_ascii=False).encode(), "application/json")

    def reply(self, content, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def seed():
    sys.path.insert(0, str(ROOT / "src/backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth.models import User
    from django.core.files.base import ContentFile
    from django.core.files.storage import storages
    from django.db import transaction
    from django.utils import timezone

    from accounts.models import Role, RoleAssignment
    from guideline.models import DatasetGuideline, GuidelineRule, GuidelineVersion
    from orchestration.models import (
        CandidateRecord,
        Evaluation,
        LedgerUnit,
        ShardCommit,
        VlmEvidence,
        VlmUnit,
    )
    from review.decision_source import materialize_candidate_issue
    from review.models import FrameReview
    from runs.models import ConfigVersion, EngineResult, QCRun, RunRanking, RunRankingEntry
    from snapshots.normalization import FrameExport, JobExport, sha256_json
    from snapshots.services import create_locked_snapshot

    if not settings.DEBUG or "demo" not in str(settings.DATABASES["default"]["NAME"]).lower():
        raise SystemExit("Demo seeding requires DEBUG and a separate demo database.")
    password = os.environ.get("LABELX_DEMO_PASSWORD")
    if not password and not User.objects.filter(username="demo_admin").exists():
        raise SystemExit("Set LABELX_DEMO_PASSWORD before creating the demo account.")
    settings.ORCHESTRATION_AUTO_DISPATCH = False
    admin, created = User.objects.get_or_create(
        username="demo_admin", defaults={"first_name": "Demo Super Admin"}
    )
    if created:
        admin.set_password(password)
        admin.save()
    RoleAssignment.objects.get_or_create(user=admin, role=Role.SUPER_ADMIN, dataset_id=None)
    existing = QCRun.objects.filter(dataset_id=DATASET, created_by=admin).order_by("-pk").first()
    if existing:
        print(json.dumps({"run_id": existing.pk, "dataset_id": DATASET, "username": "demo_admin"}))
        return
    picture = IMAGE.read_bytes()
    storage = storages["snapshots"]
    client = storage.connection.meta.client
    try:
        client.head_bucket(Bucket=storage.bucket_name)
    except Exception:
        client.create_bucket(Bucket=storage.bucket_name)
    image_key = f"demo/{hashlib.sha256(picture).hexdigest()}.jpg"
    storage.save(image_key, ContentFile(picture))
    with transaction.atomic():
        taxonomy = {
            "version": "demo-v1",
            "labels": [{"name": label["name"], "required_attributes": []} for label in LABELS],
        }
        guideline, _ = GuidelineVersion.objects.get_or_create(
            version_tag="demo-v1",
            defaults={
                "name": "DEMO — Phân biệt car / truck",
                "taxonomy": taxonomy,
                "file_checksum": hashlib.sha256(b"labelx-demo-v1").hexdigest(),
            },
        )
        GuidelineRule.objects.get_or_create(
            version=guideline,
            rule_id="DEMO-01",
            defaults={
                "section": "Phân loại xe",
                "content": (
                    "Xe con và SUV được gán car. Truck dành cho xe tải. Đây là quy tắc demo."
                ),
            },
        )
        DatasetGuideline.objects.get_or_create(
            dataset_id=DATASET, defaults={"guideline": guideline, "updated_by": admin}
        )
        mapped = [
            {
                "label_id": label["id"],
                "name": label["name"],
                "color": label["color"],
                "required_attributes": [],
            }
            for label in LABELS
        ]
        snapshot = create_locked_snapshot(
            dataset_id=DATASET,
            created_by=admin,
            taxonomy_version="demo-taxonomy-v1",
            guideline_version=guideline.version_tag,
            provenance={
                "purpose": "Explicitly synthetic demo; Qwen results are prefilled",
                "guideline_context": {
                    "taxonomy": {"version": "demo-taxonomy-v1", "labels": mapped},
                    "annotation_labels": mapped,
                },
            },
            jobs=[
                JobExport(
                    cvat_job_id=i,
                    cvat_task_id=TASK,
                    source_updated_at=STAMP,
                    assignee_cvat_user_id=99002,
                    annotations=annotations(i),
                    frames=[
                        FrameExport(
                            frame_index=f,
                            file_name=f"demo-{f}.jpg",
                            width=1280,
                            height=720,
                            media_bytes=picture,
                            media_storage_key=image_key,
                        )
                        for f in range((i - JOB_IDS[0]) * 2, (i - JOB_IDS[0]) * 2 + 2)
                    ],
                )
                for i in JOB_IDS[:2]
            ],
        )
        config = ConfigVersion.objects.create(
            name="DEMO — Detector + model 2",
            status="published",
            created_by=admin,
            engines={"detector": True, "vlm": True},
            thresholds={},
        )
        run = QCRun.objects.create(
            snapshot=snapshot,
            config_version=config,
            seed=42,
            status="completed",
            dataset_id=DATASET,
            created_by=admin,
            scope_hash=sha256_json({"demo": True}),
            score_version="score_v0",
            started_at=timezone.now(),
            finished_at=timezone.now(),
            engine_versions={"detector": "demo", "vlm": "demo"},
        )
        shard = ShardCommit.objects.create(
            run=run,
            snapshot_id=snapshot.pk,
            engine="detector",
            engine_version="demo",
            shard_index=0,
            idempotency_key=f"demo-{run.pk}",
            output_sha256="d" * 64,
        )
        frames = list(snapshot.jobs.all().order_by("pk"))
        for source in ("risk", "random_audit"):
            ranking = RunRanking.objects.create(
                run=run,
                source=source,
                seed=42,
                score_version="score_v0",
                content_hash="d" * 64,
                ranking_hash="e" * 64,
            )
            for rank, frame in enumerate(
                (f for j in frames for f in j.frames.all().order_by("pk")), 1
            ):
                RunRankingEntry.objects.create(
                    ranking=ranking,
                    snapshot_frame=frame,
                    rank=rank,
                    score=0.94,
                    baseline_score=0.94,
                    tie_break_hash=f"{rank:064x}",
                    issue_counts={"E2": 1},
                    explanation={"summary": "DEMO — Annotation truck, hai mô hình đề xuất car"},
                )
        for j in frames:
            for frame in j.frames.all():
                review = FrameReview.objects.create(run=run, snapshot_frame=frame)
                box = {"x1": 190, "y1": 270, "x2": 272, "y2": 352}
                anchor = {
                    "kind": "annotation",
                    "objects": [
                        {"namespace": "cvat_shape", "id": str(frame.shapes[0]["source"]["id"])}
                    ],
                    "bbox": box,
                    "rule_id": "DEMO-01",
                    "policy_version": "anchor-v1",
                }
                evidence = {
                    "engine": "detector",
                    "prediction_class": "car",
                    "prediction_bbox": box,
                    "confidence": 0.92,
                    "iou": 0.94,
                    "actual": "truck",
                    "rule_id": "DEMO-01",
                }
                candidate = CandidateRecord.objects.create(
                    run=run,
                    shard=shard,
                    engine="detector",
                    engine_version="demo",
                    family="E2",
                    cvat_task_id=TASK,
                    frame_number=frame.frame_index,
                    dedup_key=sha256_json({"frame": frame.pk}),
                    anchor=anchor,
                    policy_version="anchor-v1",
                    evidence=evidence,
                    evidence_sha256=sha256_json(evidence),
                )
                materialize_candidate_issue(review, candidate)
                unit = VlmUnit.objects.create(
                    run=run,
                    candidate=candidate,
                    idempotency_key=f"demo-qwen-{candidate.pk}",
                    status="completed",
                    model="Qwen demo (kết quả giả lập)",
                    prompt_version="demo-v1",
                    policy_version="demo-v1",
                    result={"status": "checked"},
                )
                VlmEvidence.objects.create(
                    unit=unit,
                    run=run,
                    candidate=candidate,
                    status="checked",
                    class_name="car",
                    label_class_id="1",
                    rationale=(
                        "DEMO: thân xe và tỷ lệ giống xe con; đề xuất đổi truck thành car. "
                        "Kết quả được điền sẵn, không gọi AI thật."
                    ),
                    provider="demo",
                    model=unit.model,
                    prompt_version="demo-v1",
                    policy_version="demo-v1",
                    snapshot_revision=snapshot.revision_sha256,
                )
                Evaluation.objects.create(
                    run=run,
                    candidate=candidate,
                    generation=1,
                    source="auto",
                    snapshot_revision=snapshot.revision_sha256,
                    call_qwen=True,
                    reasons=["label_conflict"],
                    primary_reason="label_conflict",
                    human_review_required=False,
                    policy={"name": "demo"},
                    vlm_unit=unit,
                )
        for engine in ("detector", "vlm"):
            EngineResult.objects.create(
                run=run, engine=engine, status="completed", eligible_units=4, completed_units=4
            )
            for number in range(4):
                LedgerUnit.objects.create(
                    run=run,
                    engine=engine,
                    kind="frame",
                    cvat_task_id=TASK,
                    frame_number=number,
                    outcome="completed",
                )
        print(json.dumps({"run_id": run.pk, "dataset_id": DATASET, "username": "demo_admin"}))


if __name__ == "__main__":
    if sys.argv[1:] == ["serve"]:
        print("DEMO CVAT source: http://127.0.0.1:8091", flush=True)
        ThreadingHTTPServer(("127.0.0.1", 8091), DemoSource).serve_forever()
    elif sys.argv[1:] == ["seed"]:
        seed()
    else:
        raise SystemExit("Usage: demo.py serve|seed")
