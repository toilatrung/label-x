"""Read-model regressions that do not require a database or a running CVAT server."""

from types import SimpleNamespace
from unittest.mock import Mock

from accounts.models import Role, RoleAssignment
from accounts.permissions import (
    HasRoleAndDatasetScope,
    check_anti_self_review,
    check_separation_of_duties,
    get_user_scoped_datasets,
    is_super_admin,
)
from review.serialization import frame_annotations, review_evidence
from review.services import _ineligibility_code_for_job, _reviewer_identity


def test_annotations_preserve_cvat_geometry_and_display_metadata():
    shape = {
        "source": {"kind": "shape", "id": 17},
        "label_id": 4,
        "points": [1.25, 2.5, 30.75, 40.5],
        "rotation": 25,
        "occluded": True,
        "outside": False,
        "z_order": 9,
        "attributes": [{"spec_id": 3, "value": "parked"}],
    }
    frame = SimpleNamespace(
        snapshot_frame=SimpleNamespace(shapes=[shape]),
        run=SimpleNamespace(
            snapshot=SimpleNamespace(
                provenance={
                    "guideline_context": {
                        "annotation_labels": [{"label_id": 4, "name": "car", "color": "#abcdef"}],
                    }
                }
            )
        ),
    )
    (annotation,) = frame_annotations(frame)
    assert annotation["label"] == "car" and annotation["color"] == "#abcdef"
    assert annotation["bbox"] == {"x1": 1.25, "y1": 2.5, "x2": 30.75, "y2": 40.5}
    for key in ("source", "rotation", "occluded", "outside", "z_order", "attributes"):
        assert annotation[key] == shape[key]


def test_detector_evidence_matches_review_contract_without_changing_source():
    evidence = {"engine": "detector", "prediction_bbox": [1, 2, 30, 40]}
    assert review_evidence(evidence)[0]["prediction_bbox"] == {"x1": 1, "y1": 2, "x2": 30, "y2": 40}
    assert evidence["prediction_bbox"] == [1, 2, 30, 40]


def test_global_super_admin_is_recognized_from_business_role(monkeypatch):
    query = Mock()
    query.return_value.exists.return_value = True
    monkeypatch.setattr(RoleAssignment.objects, "filter", query)
    user = SimpleNamespace(pk=17, is_authenticated=True)
    assert is_super_admin(user)
    query.assert_called_once_with(user_id=17, role=Role.SUPER_ADMIN, dataset_id__isnull=True)
    assert not is_super_admin(SimpleNamespace(is_authenticated=False))


def test_super_admin_can_review_and_approve_without_identity(monkeypatch):
    user = SimpleNamespace(pk=17, is_authenticated=True)
    request = SimpleNamespace(user=user)
    monkeypatch.setattr("accounts.permissions.is_super_admin", lambda actor: actor is user)
    monkeypatch.setattr("review.services.is_super_admin", lambda actor: actor is user)
    monkeypatch.setattr("review.services._actor", lambda req: user)
    assert _reviewer_identity(request) is None
    assert _ineligibility_code_for_job(None, SimpleNamespace(assignee_cvat_user_id=None)) is None
    check_anti_self_review(request=request, author_cvat_user_id=17)
    check_separation_of_duties(request=request, requester_user_id=17)


def test_super_admin_can_use_actions_that_list_only_other_roles(monkeypatch):
    assignment = SimpleNamespace(role=Role.SUPER_ADMIN, dataset_id=None)
    monkeypatch.setattr(RoleAssignment.objects, "filter", lambda **kwargs: [assignment])
    user = SimpleNamespace(pk=17, is_authenticated=True)
    request = SimpleNamespace(user=user, query_params={}, data={})
    view = SimpleNamespace(
        allowed_roles=(Role.ANNOTATOR,), requires_dataset=True, get_dataset_id=lambda req: 42
    )
    assert HasRoleAndDatasetScope().has_permission(request, view)
    monkeypatch.setattr("accounts.permissions.is_super_admin", lambda actor: actor is user)
    assert get_user_scoped_datasets(user, allowed_roles=(Role.ANNOTATOR,)) is None
