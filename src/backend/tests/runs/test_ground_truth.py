"""Upload validation, RBAC, pinning, success-only cleanup and replay."""

import json
from unittest.mock import Mock

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import InMemoryStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Role, RoleAssignment
from engines import metric
from orchestration.dispatch import build_engine_input
from runs import ground_truth
from runs.models import GroundTruthUpload, Reference
from runs.services import BusinessRuleUnmetError, create_qc_run
from tests.engines import test_metric as metric_tests
from tests.orchestration.helpers import make_run

setup_metric = metric_tests.setup_metric


@pytest.fixture
def world(db, monkeypatch):
    run = make_run(engine="metric")
    user = run.created_by
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=run.dataset_id)
    approver = User.objects.create_user("gt-approver")
    RoleAssignment.objects.create(user=approver, role=Role.QA_LEAD, dataset_id=run.dataset_id)
    storage = InMemoryStorage()
    monkeypatch.setattr(ground_truth, "storages", {"snapshots": storage})
    monkeypatch.setattr(metric, "storages", {"snapshots": storage})
    payload = {
        "schema_version": "labelx.metric.gt.v1",
        "snapshot_id": run.snapshot_id,
        "mapping_version": "bdd100k-det-10-v1",
        "frames": [
            {
                "cvat_task_id": 9,
                "frame_number": i,
                "boxes": [{"id": "a", "label": "car", "bbox_xyxy": [0, 0, 10, 10]}],
            }
            for i in range(3)
        ],
    }
    return run, user, approver, storage, payload


def client(user):
    api = APIClient()
    api.force_authenticate(user)
    return api


def upload(world, key="upload-1", payload=None):
    run, user, _, _, default = world
    file = SimpleUploadedFile(
        "truth.json", json.dumps(payload or default).encode(), "application/json"
    )
    return client(user).post(
        "/api/ground-truth/",
        {
            "snapshot_id": run.snapshot_id,
            "mapping_version": "bdd100k-det-10-v1",
            "file": file,
        },
        format="multipart",
        HTTP_IDEMPOTENCY_KEY=key,
    )


def lock(world, ref):
    response = client(world[2]).post(f"/api/references/{ref.pk}/lock/", {}, format="json")
    assert response.status_code == 200, response.data
    ref.refresh_from_db()


def new_run(world, ref=None, key=None):
    original = world[0]
    return create_qc_run(
        snapshot_id=original.snapshot_id,
        config_version_id=original.config_version_id,
        seed=42,
        created_by=world[1],
        metric_reference_id=ref.pk if ref else None,
        idempotency_key=key,
    )[0]


def test_upload_replay_metadata_and_independent_lock(world):
    response = upload(world)
    assert response.status_code == 201, response.data
    assert response.data["frame_count"] == response.data["box_count"] == 3
    ref = Reference.objects.get(pk=response.data["reference"]["id"])
    assert upload(world).data["reference"]["id"] == ref.pk
    assert GroundTruthUpload.objects.count() == 1
    assert client(world[1]).post(f"/api/references/{ref.pk}/lock/", {}).status_code == 403
    with pytest.raises(BusinessRuleUnmetError):
        new_run(world, ref)
    lock(world, ref)
    run = new_run(world, ref)
    assert run.metric_reference_id == ref.pk
    current = client(world[1]).get("/api/ground-truth/", {"dataset_id": run.dataset_id})
    assert current.data["reference"]["status"] == "locked"
    preview = client(world[2]).get(f"/api/ground-truth/{ref.pk}/preview/")
    assert preview.status_code == 200 and len(preview.data["frames"]) == 3


@pytest.mark.parametrize("bad", ["snapshot", "mapping", "frame", "class", "bbox", "duplicate"])
def test_upload_rejects_bad_input_without_saving_file(world, bad):
    payload = world[-1]
    if bad == "snapshot":
        payload["snapshot_id"] += 999
    elif bad == "mapping":
        payload["mapping_version"] = "wrong"
    elif bad == "frame":
        payload["frames"][0]["frame_number"] = 999
    elif bad == "class":
        payload["frames"][0]["boxes"][0]["label"] = "unknown"
    elif bad == "bbox":
        payload["frames"][0]["boxes"][0]["bbox_xyxy"] = [0, 0, 11, 10]
    else:
        payload["frames"].append(payload["frames"][0])
    assert upload(world, payload=payload).status_code == 400
    assert not GroundTruthUpload.objects.exists()


def test_dataset_scope_and_upload_size(world, monkeypatch):
    stranger = User.objects.create_user("other-dataset")
    RoleAssignment.objects.create(user=stranger, role=Role.QA_LEAD, dataset_id=999)
    assert (
        client(stranger).get("/api/ground-truth/", {"dataset_id": world[0].dataset_id}).status_code
        == 403
    )
    monkeypatch.setattr(ground_truth, "MAX_UPLOAD_BYTES", 10)
    assert upload(world).status_code == 400


def test_replacement_of_unused_upload_deletes_only_after_commit(
    world, django_capture_on_commit_callbacks
):
    first = upload(world)
    ref = Reference.objects.get(pk=first.data["reference"]["id"])
    with django_capture_on_commit_callbacks(execute=True):
        second = upload(world, key="replacement")
        assert second.status_code == 201
        assert world[3].exists(ref.gt_source)
    assert not world[3].exists(ref.gt_source)
    assert client(world[2]).get(f"/api/ground-truth/{ref.pk}/preview/").status_code == 410
    assert GroundTruthUpload.objects.filter(is_current=True).count() == 1


def test_upload_idempotency_conflict_preserves_current(world):
    first = upload(world)
    world[-1]["frames"][0]["boxes"] = []
    assert upload(world).status_code == 400
    assert (
        GroundTruthUpload.objects.get(is_current=True).reference_id == first.data["reference"]["id"]
    )


def test_replacement_pins_runs_and_cleanup_preserves_active_shared_input(world):
    first = upload(world)
    ref = Reference.objects.get(pk=first.data["reference"]["id"])
    lock(world, ref)
    a, b = new_run(world, ref), new_run(world, ref)
    second = upload(world, key="upload-2")
    assert second.status_code == 201
    assert not GroundTruthUpload.objects.get(reference=ref).is_current
    with pytest.raises(BusinessRuleUnmetError, match="thay thế"):
        new_run(world, ref)
    # Older active run still has its original reference, even after a replacement.
    from runs.models import WorkUnit

    unit = WorkUnit.objects.create(
        run=a,
        engine="metric",
        shard_key="job:5:frames:0-2",
        shard_index=0,
        idempotency_key="pinning",
    )
    assert build_engine_input(unit).config.params["reference_id"] == ref.pk
    for run in (a, b):
        run.engine_results.filter(engine="metric").update(status="checked", completed_units=3)
    a.status = "completed"
    a.save()
    assert not ground_truth.cleanup_upload(ref.pk)
    assert world[3].exists(ref.gt_source)
    b.status = "completed"
    b.save()
    assert ground_truth.cleanup_upload(ref.pk)
    assert not world[3].exists(ref.gt_source)
    metadata = GroundTruthUpload.objects.get(reference=ref)
    assert metadata.deleted_at and metadata.filename == "truth.json"
    assert ref.gt_checksum
    assert not ground_truth.cleanup_upload(ref.pk)
    with pytest.raises(BusinessRuleUnmetError, match="upload lại"):
        new_run(world, ref)


@pytest.mark.parametrize("state", ["running", "partial", "failed", "cancelled"])
def test_non_successful_run_keeps_gt_for_retry(world, state):
    response = upload(world)
    ref = Reference.objects.get(pk=response.data["reference"]["id"])
    lock(world, ref)
    run = new_run(world, ref)
    run.status = state
    run.save()
    assert not ground_truth.cleanup_upload(ref.pk)
    assert world[3].exists(ref.gt_source)


def test_cleanup_storage_failure_is_retried_and_not_checked_keeps_file(world, monkeypatch):
    response = upload(world)
    ref = Reference.objects.get(pk=response.data["reference"]["id"])
    lock(world, ref)
    run = new_run(world, ref)
    run.status = "completed"
    run.save()
    assert not ground_truth.cleanup_upload(ref.pk)
    run.engine_results.filter(engine="metric").update(status="checked", completed_units=3)
    original = world[3].delete
    monkeypatch.setattr(world[3], "delete", Mock(side_effect=OSError("offline")))
    assert not ground_truth.cleanup_upload_safely(ref.pk)
    assert GroundTruthUpload.objects.get(reference=ref).deleted_at is None
    monkeypatch.setattr(world[3], "delete", original)
    assert ground_truth.cleanup_finished_uploads() == 1


def test_deleted_gt_idempotent_run_replay_does_not_need_reupload(world):
    response = upload(world)
    ref = Reference.objects.get(pk=response.data["reference"]["id"])
    lock(world, ref)
    run = new_run(world, ref, "same-run")
    run.status = "completed"
    run.finished_at = timezone.now()
    run.save()
    run.engine_results.filter(engine="metric").update(status="checked", completed_units=3)
    assert ground_truth.cleanup_upload(ref.pk)
    assert new_run(world, ref, "same-run").pk == run.pk


def test_successful_dispatch_deletes_only_after_commit_and_replay_keeps_metrics(
    setup_metric,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    from orchestration.dispatch import run_work_unit
    from orchestration.models import LedgerUnit, ShardCommit

    run, ref, _, _, predictor, _ = setup_metric
    monkeypatch.setattr(ground_truth, "storages", metric.storages)
    upload = GroundTruthUpload.objects.create(
        reference=ref, dataset_id=run.dataset_id, filename="truth.json", frame_count=3, box_count=3
    )
    run.metric_reference = ref
    run.save()
    with django_capture_on_commit_callbacks(execute=True):
        for unit in run.work_units.order_by("shard_index"):
            run_work_unit.apply(args=[unit.pk]).get()
        assert metric.storages["snapshots"].exists(ref.gt_source)
    run.refresh_from_db()
    upload.refresh_from_db()
    assert run.status == "completed" and upload.deleted_at
    assert not metric.storages["snapshots"].exists(ref.gt_source)
    assert LedgerUnit.objects.filter(run=run, outcome="completed").count() == 3
    for unit in run.work_units.all():
        run_work_unit.apply(args=[unit.pk]).get()
    assert predictor.call_count == 2 and ShardCommit.objects.filter(run=run).count() == 2
