import pytest
from django.utils import timezone
from orchestration.models import CandidateRecord, ShardCommit, LedgerUnit
from runs.models import QCRun, EngineResult
from review.models import Issue, ReworkRequest
from review.finalization_service import build_final_run, operational_run
from tests.review.test_queue_lease import client, next_url
from tests.review.test_rework import create_request, changed_snapshot
from tests.review.test_finalization import _resolved_scope

pytest_plugins = ['tests.review.test_queue_lease', 'tests.review.test_rework']

@pytest.fixture(autouse=True)
def isolated_dispatch(settings):
    settings.ORCHESTRATION_AUTO_DISPATCH = False
    settings.FINAL_RUN_AUTO_DISPATCH = False

@pytest.mark.django_db
def test_queue_exposes_real_holder_after_claim(world):
    api = client(world['reviewer'])
    grant = api.post(next_url(), {'run_id': world['run'].pk}, format='json')
    assert grant.status_code == 200
    response = api.get(f"/api/runs/{world['run'].pk}/ranking/?queue=risk")
    print('QUEUE_AFTER_CLAIM', response.data)
    assert response.data['results'][0]['review_state'] == 'in_review'
    assert response.data['results'][0]['lease_holder_user_id'] == world['reviewer'].pk

@pytest.mark.django_db
def test_queue_in_review_filter_finds_claimed_frame(world):
    api = client(world['reviewer'])
    assert api.post(next_url(), {'run_id': world['run'].pk}, format='json').status_code == 200
    response = api.get(f"/api/runs/{world['run'].pk}/ranking/?queue=risk&review_state=in_review")
    print('FILTER_IN_REVIEW', response.data)
    assert len(response.data['results']) == 1

@pytest.mark.django_db
def test_verify_failure_can_be_submitted_again(confirmed, world, monkeypatch):
    created = create_request(confirmed, world)
    assert created.status_code == 201
    rework = ReworkRequest.objects.get(pk=created.data['id'])
    snapshot = changed_snapshot(world)
    run = QCRun.objects.create(snapshot=snapshot, config_version=world['run'].config_version,
        seed=1, status=QCRun.Status.COMPLETED, origin_run=world['run'], dataset_id=42,
        scope_hash=snapshot.revision_sha256, created_by=world['author'])
    monkeypatch.setattr('review.rework_service._build_recheck_artifacts', lambda **kwargs: (snapshot, run))
    submitted = client(world['author']).post(f'/api/rework/{rework.pk}/submitted/', {'cvat_revision': snapshot.revision_sha256}, format='json')
    assert submitted.status_code == 202
    failed = client(world['other']).post(f'/api/rework/{rework.pk}/verify/', {'passed': False, 'revision': snapshot.revision_sha256, 'reason': 'still wrong'}, format='json')
    assert failed.status_code == 200
    retry = client(world['author']).post(f'/api/rework/{rework.pk}/submitted/', {'cvat_revision': '9'*64}, format='json')
    recreate = create_request(confirmed, world)
    print('AFTER_VERIFY_FAIL', 'submit', retry.status_code, retry.data, 'create', recreate.status_code, recreate.data)
    assert retry.status_code == 202 or recreate.status_code == 201

@pytest.mark.django_db
def test_new_final_candidate_blocks_operational_source(world, monkeypatch):
    issue, fixed, verification = _resolved_scope(world)
    monkeypatch.setattr('review.finalization_service.create_snapshot_from_cvat', lambda **kwargs: fixed)
    final, _ = build_final_run(origin_run_id=world['run'].pk, actor=world['other'])
    final.engine_results.all().delete()
    EngineResult.objects.create(run=final, engine='geometry', status='checked', required=True,
        eligible_units=1, completed_units=1, failed_units=0, not_checked_units=0)
    LedgerUnit.objects.create(run=final, engine='geometry', kind='frame', cvat_task_id=200, frame_number=0, outcome='completed')
    shard = ShardCommit.objects.create(run=final, idempotency_key='new-final-candidate', snapshot_id=fixed.pk,
        engine='geometry', engine_version='1', shard_index=0, output_sha256='a'*64)
    candidate = CandidateRecord.objects.create(run=final, dedup_key='b'*64, shard=shard, engine='geometry', engine_version='1',
        family='E2', cvat_task_id=200, frame_number=0, anchor={'kind':'manual_region','objects':[]},
        policy_version='anchor-v1', evidence={'rule_id':'TEST'}, evidence_sha256='c'*64)
    final.status = QCRun.Status.COMPLETED
    final.finished_at = timezone.now()
    final.save(update_fields=['status','finished_at'])
    selected = operational_run(world['run'])
    print('NEW_FINAL_CANDIDATE', candidate.pk, 'issues', Issue.objects.filter(candidate=candidate).count(), 'selected', selected.pk, 'origin', world['run'].pk)
    assert selected.pk == world['run'].pk

@pytest.mark.django_db
def test_verify_pass_does_not_complete_frame_before_final_run(confirmed, world, monkeypatch):
    created = create_request(confirmed, world)
    assert created.status_code == 201
    rework = ReworkRequest.objects.get(pk=created.data['id'])
    snapshot = changed_snapshot(world)
    run = QCRun.objects.create(snapshot=snapshot, config_version=world['run'].config_version,
        seed=1, status=QCRun.Status.COMPLETED, origin_run=world['run'], dataset_id=42,
        scope_hash=snapshot.revision_sha256, created_by=world['author'])
    monkeypatch.setattr('review.rework_service._build_recheck_artifacts', lambda **kwargs: (snapshot, run))
    assert client(world['author']).post(f'/api/rework/{rework.pk}/submitted/', {'cvat_revision': snapshot.revision_sha256}, format='json').status_code == 202
    response = client(world['other']).post(f'/api/rework/{rework.pk}/verify/', {'passed': True, 'revision': snapshot.revision_sha256}, format='json')
    assert response.status_code == 200
    confirmed.frame_review.refresh_from_db()
    print('VERIFY_PASS_FRAME', confirmed.frame_review.state, 'final_runs', QCRun.objects.filter(is_final=True).count())
    assert confirmed.frame_review.state != 'completed'
