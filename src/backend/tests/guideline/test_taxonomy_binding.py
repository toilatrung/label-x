"""A-03: policy import, scope, immutable reference and schema execution without ORM config."""

from dataclasses import replace

import pytest
import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from accounts.models import RoleAssignment
from engines.registration import run_registered_schema_taxonomy_engine
from engines.structural import structural_frames_from_snapshot
from guideline.importing import load_guideline
from guideline.models import DatasetGuideline, GuidelineVersion
from guideline.taxonomy import GuidelineBindingError, bind_taxonomy
from snapshots.orchestration import SnapshotScope, SnapshotSourceError, create_snapshot_from_cvat
from tests.snapshots.test_orchestration import FakeCvatClient, FakeStorage
from tests.test_schema_geometry_engines import _engine_input

pytestmark = pytest.mark.django_db(transaction=True)


def policy(version="v1"):
    return {
        "version": version,
        "name": "Policy",
        "rules": [{"id": "A-001", "section": "1", "content": "State required"}],
        "taxonomy": {
            "version": version,
            "labels": [
                {
                    "name": "car",
                    "required_attributes": [
                        {
                            "name": "state",
                            "rule_id": "A-001",
                            "allowed_values": ["parked", "moving"],
                        }
                    ],
                }
            ],
        },
        "mappings": [{"class_name": "car", "rule_ids": ["A-001"]}],
    }


def owner(role="qc_admin", dataset_id=None):
    user = get_user_model().objects.create_user(username=f"{role}-{dataset_id}")
    RoleAssignment.objects.create(user=user, role=role, dataset_id=dataset_id)
    return user


def imported(user, version="v1"):
    return load_guideline(yaml.safe_dump(policy(version)).encode(), user.username)[0]


class Cvat(FakeCvatClient):
    def list_labels(self, *, project_id):
        return [
            {
                "id": 2,
                "name": "car",
                "attributes": [
                    {
                        "id": 8,
                        "name": "state",
                        "input_type": "select",
                        "values": ["moving", "parked"],
                    }
                ],
            },
            {"id": 3, "name": "foreign", "attributes": []},
        ]

    def close(self):
        pass


def snapshot(user, key="s1", **kwargs):
    return create_snapshot_from_cvat(
        dataset_id=42,
        scope=SnapshotScope(cvat_job_ids=(17,)),
        note="",
        created_by=user,
        idempotency_key=key,
        client=Cvat(),
        storage=FakeStorage(),
        **kwargs,
    )


def test_import_replay_and_immutable_version():
    user = owner()
    raw = yaml.safe_dump(policy()).encode()
    first, skipped = load_guideline(raw, user.username)
    replay, skipped = load_guideline(raw, user.username)
    assert first.pk == replay.pk and skipped
    changed = policy()
    changed["taxonomy"]["labels"][0]["required_attributes"][0]["allowed_values"] = ["parked"]
    with pytest.raises(CommandError, match="already exists"):
        load_guideline(yaml.safe_dump(changed).encode(), user.username)
    first.refresh_from_db()
    assert first.taxonomy["labels"][0]["required_attributes"][0]["allowed_values"] == [
        "moving",
        "parked",
    ]


@pytest.mark.parametrize("change", ["foreign_mapping", "unknown_rule", "duplicate_label"])
def test_import_invalid_policy_is_atomic(change):
    user = owner()
    data = policy()
    if change == "foreign_mapping":
        data["mappings"][0]["class_name"] = "foreign"
    elif change == "unknown_rule":
        data["taxonomy"]["labels"][0]["required_attributes"][0]["rule_id"] = "missing"
    else:
        data["taxonomy"]["labels"] *= 2
    with pytest.raises(CommandError):
        load_guideline(yaml.safe_dump(data).encode(), user.username)
    assert not GuidelineVersion.objects.exists()


def test_snapshot_requires_mapping_and_taxonomy():
    user = owner()
    with pytest.raises(SnapshotSourceError, match="chưa được gắn"):
        snapshot(user)
    old = GuidelineVersion.objects.create(
        version_tag="legacy", name="Legacy", file_checksum="a" * 64
    )
    DatasetGuideline.objects.create(dataset_id=42, guideline=old, updated_by=user)
    with pytest.raises(SnapshotSourceError, match="chưa có taxonomy"):
        snapshot(user)


def test_snapshot_engine_uses_frozen_policy_over_config_and_new_binding():
    user = owner()
    v1 = imported(user)
    binding = DatasetGuideline.objects.create(dataset_id=42, guideline=v1, updated_by=user)
    frozen = snapshot(user)
    assert frozen.guideline_version == "v1"
    v2 = imported(user, "v2")
    binding.guideline = v2
    binding.save()
    frames = tuple(structural_frames_from_snapshot(frozen.normalized_json))
    engine_input = replace(_engine_input("schema", "1.0.0", *frames), snapshot_id=frozen.pk)
    result = run_registered_schema_taxonomy_engine(engine_input)
    assert [c.anchor.rule_id for c in result.candidates] == ["A-001"]
    assert all(unit.outcome == "completed" for unit in result.unit_results)
    assert frozen.provenance["guideline_context"]["guideline_checksum"] == v1.file_checksum
    new = snapshot(user, "s2")
    assert new.guideline_version == "v2" and new.taxonomy_version != frozen.taxonomy_version
    assert snapshot(user).pk == frozen.pk  # Replay after binding change remains original.
    pinned = snapshot(user, "rework", guideline_version="v1")
    assert pinned.revision_sha256 == frozen.revision_sha256
    with pytest.raises(SnapshotSourceError, match="đã thay đổi"):
        snapshot(user, "stale-ui", expected_guideline_version="v1")


@pytest.mark.parametrize(
    "change", ["missing_class", "ambiguous_class", "missing_attribute", "bad_values"]
)
def test_mapping_fails_without_guessing(change):
    user = owner()
    version = imported(user)
    DatasetGuideline.objects.create(dataset_id=42, guideline=version, updated_by=user)
    labels = Cvat().list_labels(project_id=42)
    if change == "missing_class":
        labels = labels[1:]
    elif change == "ambiguous_class":
        labels.append({**labels[0], "id": 7})
    elif change == "missing_attribute":
        labels[0]["attributes"] = []
    else:
        labels[0]["attributes"][0]["values"] = ["parked"]
    with pytest.raises(GuidelineBindingError):
        bind_taxonomy(42, labels)


def test_api_import_binding_rbac_and_stale_write(monkeypatch):
    monkeypatch.setattr("guideline.config_views._client", Cvat)
    admin = owner()
    client = APIClient()
    client.force_authenticate(admin)
    imported_response = client.post(
        "/api/guidelines/import/", {"content": yaml.safe_dump(policy())}, format="json"
    )
    assert imported_response.status_code == 200, imported_response.data
    body = {"guideline_version": "v1", "expected_revision": 0}
    response = client.put("/api/datasets/42/guideline/", body, format="json")
    assert response.status_code == 200 and response.data["revision"] == 1
    assert client.put("/api/datasets/42/guideline/", body, format="json").status_code == 409
    qa = owner("qa_lead", 42)
    client.force_authenticate(qa)
    assert client.get("/api/datasets/42/guideline/").data["guideline_version"] == "v1"
    assert client.get("/api/datasets/99/guideline/").status_code == 403
    assert client.put("/api/datasets/42/guideline/", body, format="json").status_code == 403
    assert (
        client.post(
            "/api/guidelines/import/", {"content": yaml.safe_dump(policy())}, format="json"
        ).status_code
        == 403
    )


def test_cvat_taxonomy_drift_never_locks():
    user = owner()
    version = imported(user)
    DatasetGuideline.objects.create(dataset_id=42, guideline=version, updated_by=user)

    class Drifting(Cvat):
        reads = 0

        def list_labels(self, *, project_id):
            self.reads += 1
            labels = super().list_labels(project_id=project_id)
            if self.reads > 1:
                labels[0]["id"] = 99
            return labels

    with pytest.raises(SnapshotSourceError, match="đã thay đổi"):
        create_snapshot_from_cvat(
            dataset_id=42,
            scope=SnapshotScope(cvat_job_ids=(17,)),
            note="",
            created_by=user,
            idempotency_key="drift-policy",
            client=Drifting(),
            storage=FakeStorage(),
        )
    from snapshots.models import Snapshot

    assert not Snapshot.objects.exists()


def test_foreign_cvat_label_is_reported_and_valid_values_are_accepted():
    user = owner()
    version = imported(user)
    DatasetGuideline.objects.create(dataset_id=42, guideline=version, updated_by=user)

    class Annotated(Cvat):
        def get_job_annotations(self, job_id):
            data = super().get_job_annotations(job_id)
            data["shapes"][0]["attributes"] = [{"spec_id": 8, "value": "parked"}]
            data["shapes"].append({**data["shapes"][0], "id": 99, "label_id": 3})
            return data

    frozen = create_snapshot_from_cvat(
        dataset_id=42,
        scope=SnapshotScope(cvat_job_ids=(17,)),
        note="",
        created_by=user,
        idempotency_key="foreign",
        client=Annotated(),
        storage=FakeStorage(),
    )
    frames = tuple(structural_frames_from_snapshot(frozen.normalized_json))
    result = run_registered_schema_taxonomy_engine(
        replace(_engine_input("schema", "1.0.0", *frames), snapshot_id=frozen.pk)
    )
    assert [c.anchor.rule_id for c in result.candidates] == ["S-001"]


def test_legacy_rework_keeps_original_revision_format_without_mapping():
    from snapshots.orchestration import compute_job_revision
    from tests.snapshots.test_orchestration import _AddressedStorage

    user = owner()
    legacy = create_snapshot_from_cvat(
        dataset_id=42,
        scope=SnapshotScope(cvat_job_ids=(17,)),
        note="",
        created_by=user,
        idempotency_key="legacy-rework",
        client=FakeCvatClient(),
        storage=_AddressedStorage(),
        guideline_version="old-version",
        legacy_reference=True,
    )
    assert "guideline_context" not in legacy.provenance
    assert legacy.taxonomy_version.startswith("cvat-labels:")
    assert (
        compute_job_revision(
            dataset_id=42,
            cvat_job_id=17,
            client=FakeCvatClient(),
            guideline_version="old-version",
            legacy_reference=True,
        )
        == legacy.revision_sha256
    )


def test_rejected_api_import_retains_load_record():
    from guideline.models import GuidelineLoadRecord

    user = owner()
    client = APIClient()
    client.force_authenticate(user)
    response = client.post("/api/guidelines/import/", {"content": "invalid: true"}, format="json")
    assert response.status_code == 400
    assert GuidelineLoadRecord.objects.get().result == "rejected"
