"""Issue #391: distinct assertions for the p0 matrix, with honest external gates.

SNP-05 has backend support coverage here; it remains unbound until browser e2e exists.
SNP-04 requires the same opt-in real S3 service as the existing storage integration tests.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
import yaml
from django.contrib.auth import get_user_model
from django.db import DatabaseError, transaction
from PIL import Image
from rest_framework.test import APIClient

from accounts.models import CvatIdentity, Role, RoleAssignment
from cvat_adapter.client import CvatReadClient, CvatWriteBlocked
from guideline.models import DatasetGuideline, GuidelineVersion
from snapshots.models import LockedSnapshotError, Snapshot, SnapshotFrame, SnapshotJob
from snapshots.normalization import FrameExport, JobExport, normalize_job
from snapshots.orchestration import SnapshotScope, SnapshotSourceError, create_snapshot_from_cvat
from storage.client import Blob, ObjectStorage, content_key

ROOT = Path(__file__).resolve().parents[4]
TOKEN = "synthetic-391-server-only-token"
CVAT_VERSION = "2.77.0"


def _image(color):
    stream = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(stream, format="PNG")
    return stream.getvalue()


class Cvat277Fixture:
    """Recorded endpoint shapes for the repository's pinned CVAT 2.77.0 contract."""

    def __init__(self, *, drift=False, outside=False):
        self.drift = drift
        self.outside = outside
        self.requests = []
        self.reads = {}
        self.media = {
            (31, 10): _image("red"),
            (31, 12): _image("blue"),
            (17, 4): _image("green"),
            (17, 6): _image("yellow"),
        }

    def handle(self, request):
        self.requests.append(request)
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        path = request.url.path.rstrip("/")
        if path == "/api/server/about":
            return httpx.Response(200, json={"version": CVAT_VERSION})
        if path == "/api/projects/42":
            payload = {"id": 42}
        elif path == "/api/labels":
            payload = {"results": [{"id": 2, "name": "car"}], "next": None}
        elif path.startswith("/api/tasks/"):
            payload = {"id": int(path.rsplit("/", 1)[1]), "project_id": 99 if self.outside else 42}
        elif path.startswith("/api/jobs/"):
            job_id = int(path.split("/")[3])
            start = 4 if job_id == 17 else 10
            task_id = 9 if job_id == 17 else 8
            if path.endswith("/annotations"):
                self.reads[job_id] = self.reads.get(job_id, 0) + 1
                right = 40 if self.drift and job_id == 31 and self.reads[job_id] == 2 else 30
                payload = {
                    "version": 1,
                    "shapes": [
                        {
                            "id": job_id,
                            "type": "rectangle",
                            "frame": start,
                            "label_id": 2,
                            "points": [1, 2, right, 32],
                            "attributes": [{"spec_id": 5, "value": "yes"}],
                        }
                    ],
                    "tracks": [],
                }
            elif path.endswith("/data/meta"):
                payload = {
                    "start_frame": start,
                    "frame_filter": "step=2",
                    "frames": [
                        {"name": f"{job_id}-{frame}.png", "width": 64, "height": 48}
                        for frame in (start, start + 2)
                    ],
                }
            elif path.endswith("/data"):
                return httpx.Response(
                    200,
                    content=self.media[job_id, int(request.url.params["number"])],
                    headers={"Content-Type": "image/png"},
                )
            else:
                payload = {
                    "id": job_id,
                    "task_id": task_id,
                    "start_frame": start,
                    "stop_frame": start + 2,
                    "updated_date": "2026-10-17T00:00:00Z",
                    "assignee": {"id": 500 + job_id},
                }
        else:
            raise AssertionError(f"Unexpected CVAT contract route {path}")
        return httpx.Response(200, json=payload)

    def client(self):
        return CvatReadClient(
            "https://cvat.test", TOKEN, transport=httpx.MockTransport(self.handle)
        )


class DiskBlobStore:
    """Support fixture: real temporary bytes, deliberately not claimed as S3."""

    def __init__(self, path):
        self.path = path

    def put(self, content, *, extension=None, content_type="application/octet-stream"):
        key, digest = content_key(content, extension)
        target = self.path / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return Blob("temporary", key, digest, len(content), True)


@pytest.fixture
def snapshot_actor(db):
    user = get_user_model().objects.create_user(username="p0-391-owner")
    RoleAssignment.objects.create(user=user, role=Role.QA_LEAD, dataset_id=42)
    version = GuidelineVersion.objects.create(
        version_tag="p0-391-v1",
        name="Snapshot policy",
        file_checksum="f" * 64,
        taxonomy={
            "version": "p0-391-taxonomy",
            "labels": [{"name": "car", "required_attributes": []}],
        },
    )
    DatasetGuideline.objects.create(dataset_id=42, guideline=version, updated_by=user)
    CvatIdentity.objects.create(user=user, cvat_user_id=517)
    return user


def _create(actor, source, storage, key):
    with source.client() as client:
        return create_snapshot_from_cvat(
            dataset_id=42,
            scope=SnapshotScope(cvat_job_ids=(31, 17)),
            note="issue-391",
            created_by=actor,
            idempotency_key=key,
            client=client,
            storage=storage,
        )


def test_snp01_cvat277_records_reads_and_blocks_all_annotation_writes():
    source = Cvat277Fixture()
    with source.client() as client:
        assert client._get("api/server/about")["version"] == CVAT_VERSION
        assert client.get_job_annotations(17)["shapes"][0]["frame"] == 4
        recorded = len(source.requests)
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            for route in (
                "/api/jobs/17/annotations",
                "/api/tasks/9/annotations",
                "/api/jobs/17/annotations/export",
            ):
                with pytest.raises(CvatWriteBlocked, match=method):
                    client._client.request(method, f"https://cvat.test{route}", json={})
        assert len(source.requests) == recorded
    assert all(request.method == "GET" for request in source.requests)


def test_snp02_equivalent_exports_hash_equal_but_each_semantic_edit_changes_hash():
    shapes = [
        {
            "id": i,
            "type": "rectangle",
            "frame": 0,
            "label_id": 2,
            "points": [1, 2, 30, 32],
            "attributes": [{"spec_id": 5, "value": "yes"}, {"spec_id": 6, "value": "clear"}],
        }
        for i in (1, 2)
    ]
    export = JobExport(
        17,
        9,
        "2026-10-17T00:00:00Z",
        {"shapes": shapes, "tracks": []},
        (FrameExport(0, "test.png", 64, 48, _image("red"), "sha256/test"),),
    )
    original = normalize_job(export)
    reordered = copy.deepcopy(shapes[::-1])
    for shape in reordered:
        shape["attributes"].reverse()
    equivalent = replace(
        export,
        annotations={
            "tracks": [],
            "shapes": [dict(reversed(list(shape.items()))) for shape in reordered],
        },
    )
    assert normalize_job(equivalent).canonical_json == original.canonical_json
    assert normalize_job(equivalent).sha256 == original.sha256
    for field, value in (
        ("points", [1, 2, 31, 32]),
        ("label_id", 3),
        ("attributes", [{"spec_id": 5, "value": "no"}]),
    ):
        edited = copy.deepcopy(shapes)
        edited[0][field] = value
        assert (
            normalize_job(replace(export, annotations={"shapes": edited})).sha256 != original.sha256
        )


@pytest.mark.django_db(transaction=True)
def test_snp03_r1_r2_drift_has_exact_job_ids_and_no_mixed_rows(snapshot_actor, tmp_path):
    source = Cvat277Fixture(drift=True)
    snapshot = _create(snapshot_actor, source, DiskBlobStore(tmp_path), "p0-drift")
    assert source.reads == {17: 2, 31: 2}
    assert snapshot.status == Snapshot.Status.FAILED
    assert snapshot.failure_reason == "drift_detected"
    assert snapshot.drift_jobs == [31]
    assert snapshot.locked_at is None and snapshot.revision_sha256 == ""
    assert snapshot.normalized_json == {}
    assert SnapshotJob.objects.count() == SnapshotFrame.objects.count() == 0
    assert not Snapshot.objects.filter(status=Snapshot.Status.LOCKED).exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    os.getenv("LABELX_RUN_S3_INTEGRATION") != "1",
    reason="SNP-04 requires an isolated real S3 bucket; set LABELX_RUN_S3_INTEGRATION=1",
)
def test_snp04_real_objects_mapping_lineage_and_database_immutability(snapshot_actor):
    storage = ObjectStorage.from_django_settings("snapshots")
    source = Cvat277Fixture()
    parent = _create(snapshot_actor, source, storage, "p0-parent")
    child = _create(snapshot_actor, Cvat277Fixture(), storage, "p0-child")
    assert child.pk != parent.pk and child.parent_snapshot_id == parent.pk
    assert child.revision_sha256 == parent.revision_sha256
    assert parent.guideline_version == "p0-391-v1"

    def independent_digest(payload):
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(serialized.encode()).hexdigest()

    # The locked taxonomy identifies both policy and its CVAT label mapping, not just
    # the taxonomy's human version tag. Calculate the fixture's binding independently.
    expected_context = {
        "guideline_version": "p0-391-v1",
        "guideline_checksum": "f" * 64,
        "taxonomy_definition": {
            "version": "p0-391-taxonomy",
            "labels": [{"name": "car", "required_attributes": []}],
        },
        "cvat_labels_sha256": independent_digest([{"id": 2, "name": "car"}]),
        "labels": [{"label_id": 2, "name": "car", "required_attributes": []}],
    }
    expected_version = f"guideline-taxonomy:{independent_digest(expected_context)}"
    assert parent.taxonomy_version == child.taxonomy_version == expected_version
    assert parent.normalized_json["taxonomy_version"] == expected_version
    locked_context = parent.provenance["guideline_context"]
    assert {key: locked_context[key] for key in expected_context} == expected_context
    assert locked_context["taxonomy"] == {
        "version": expected_version, "labels": expected_context["labels"],
    }
    assert list(parent.jobs.values_list("cvat_job_id", flat=True)) == [17, 31]
    for job in parent.jobs.all():
        assert job.assignee_cvat_user_id == 500 + job.cvat_job_id
        assert job.assignee_user_id == (snapshot_actor.pk if job.cvat_job_id == 17 else None)
        indices = [4, 6] if job.cvat_job_id == 17 else [10, 12]
        assert list(job.frames.values_list("frame_index", flat=True)) == indices
        for frame in job.frames.all():
            expected = source.media[job.cvat_job_id, frame.frame_index]
            assert frame.source_frame_id == frame.frame_index
            assert frame.file_name == f"{job.cvat_job_id}-{frame.frame_index}.png"
            assert (frame.width, frame.height) == (64, 48)
            assert storage.get(frame.media_storage_key) == expected
            assert frame.media_sha256 == hashlib.sha256(expected).hexdigest()
            assert frame.media_size_bytes == len(expected)
    parent.provenance = {"tampered": True}
    with pytest.raises(LockedSnapshotError):
        parent.save()
    for operation in (
        lambda: Snapshot.objects.filter(pk=parent.pk).update(guideline_version="tampered"),
        lambda: parent.jobs.all().update(assignee_cvat_user_id=999),
        lambda: SnapshotFrame.objects.filter(snapshot_job__snapshot=parent).delete(),
    ):
        with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
            operation()
    parent.refresh_from_db()
    assert parent.guideline_version == "p0-391-v1"
    assert SnapshotFrame.objects.filter(snapshot_job__snapshot=parent).count() == 4


@pytest.mark.django_db(transaction=True)
def test_snapshot_membership_missing_frames_and_blob_failures_leave_no_metadata(
    snapshot_actor,
    tmp_path,
    monkeypatch,
):
    storage = DiskBlobStore(tmp_path)
    with pytest.raises(SnapshotSourceError, match="outside dataset"):
        _create(snapshot_actor, Cvat277Fixture(outside=True), storage, "p0-outside")
    assert not list(tmp_path.rglob("sha256/*/*"))

    frame = FrameExport(4, "test.png", 64, 48, _image("red"), "sha256/test")
    export = JobExport(17, 9, "2026-10-17T00:00:00Z", {}, (frame,))
    with pytest.raises(ValueError, match="missing frame_index 5"):
        normalize_job(
            replace(
                export,
                annotations={
                    "shapes": [
                        {
                            "id": 1,
                            "type": "rectangle",
                            "frame": 5,
                            "label_id": 2,
                            "points": [1, 2, 30, 32],
                        }
                    ]
                },
            )
        )
    with pytest.raises(ValueError, match="width must be at least 1"):
        normalize_job(replace(export, frames=(replace(frame, width=0),)))
    with pytest.raises(ValueError, match="duplicate frame_index"):
        normalize_job(replace(export, frames=(frame, frame)))

    class FailingStorage(DiskBlobStore):
        def put(self, *args, **kwargs):
            raise OSError("synthetic object upload failure")

    with pytest.raises(OSError, match="upload failure"):
        _create(snapshot_actor, Cvat277Fixture(), FailingStorage(tmp_path), "p0-upload-fail")
    from snapshots import services

    persist = services._persist_job

    def fail_after_first_job(*args):
        persist(*args)
        raise RuntimeError("synthetic metadata failure")

    monkeypatch.setattr(services, "_persist_job", fail_after_first_job)
    with pytest.raises(RuntimeError, match="metadata failure"):
        _create(snapshot_actor, Cvat277Fixture(), storage, "p0-commit-fail")
    assert (
        Snapshot.objects.count()
        == SnapshotJob.objects.count()
        == SnapshotFrame.objects.count()
        == 0
    )
    assert list(tmp_path.rglob("sha256/*/*"))  # uploaded orphans survive; no invented GC policy


@pytest.mark.django_db(transaction=True)
def test_snp05_support_api_links_preserve_job_frame_and_do_not_leak_token(
    snapshot_actor,
    tmp_path,
    settings,
    caplog,
):
    settings.CVAT_BASE_URL = "https://cvat.test"
    settings.CVAT_SERVICE_TOKEN = TOKEN
    snapshot = _create(snapshot_actor, Cvat277Fixture(), DiskBlobStore(tmp_path), "p0-links")
    client = APIClient()
    client.force_authenticate(snapshot_actor)
    response = client.get(f"/api/snapshots/{snapshot.pk}/")
    assert response.status_code == 200
    for job in response.data["jobs"]:
        for frame in job["frames"]:
            assert frame["cvat_url"] == (
                f"https://cvat.test/tasks/{job['cvat_task_id']}/jobs/"
                f"{job['cvat_job_id']}?frame={frame['frame_index']}"
            )
    assert TOKEN not in response.content.decode() + caplog.text


def test_api01_support_snapshot_operation_ids_and_status_codes_match():
    # Partial support only: full response-shape drift is documented in bindings-391.
    from drf_spectacular.generators import SchemaGenerator

    contract_path = ROOT / "docs/04-api/openapi.yaml"
    documented = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    runtime = SchemaGenerator().get_schema(request=None, public=True)
    for path, methods in (("/api/snapshots/", ("get", "post")), ("/api/snapshots/{id}/", ("get",))):
        for method in methods:
            expected = documented["paths"][path][method]
            actual = runtime["paths"][path][method]
            assert actual["operationId"] == expected["operationId"]
            assert set(actual["responses"]) == set(expected["responses"])


def test_api01_support_generated_types_match_committed_schema(tmp_path):
    contract_path = ROOT / "docs/04-api/openapi.yaml"
    cli = Path(
        os.environ.get(
            "LABELX_OPENAPI_TYPESCRIPT_CLI",
            str(ROOT / "src/frontend/node_modules/openapi-typescript/bin/cli.js"),
        )
    )
    if not cli.is_file():
        pytest.skip("API-01 type-generation support requires frontend npm dependencies")
    generated = tmp_path / "contract.d.ts"
    result = subprocess.run(
        [
            os.environ.get("LABELX_NODE_BINARY", "node"),
            str(cli),
            str(contract_path),
            "--default-non-nullable",
            "false",
            "-o",
            str(generated),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    checked_in = ROOT / "src/frontend/src/lib/api/contract.d.ts"
    assert generated.read_text(encoding="utf-8") == checked_in.read_text(encoding="utf-8"), (
        "Frontend types are stale; run npm run gen:api:contract and review the schema change"
    )
