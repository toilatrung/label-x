export const session = {
  user: { id: 7, username: 'qa.lead', full_name: 'QA Lead' },
  roles: [{ role: 'qa_lead', dataset_id: 12 }],
  identity_mapping: { status: 'mapped', cvat_user_id: 41 },
};

export const snapshot = {
  id: 18, dataset_id: 12, status: 'locked', revision_hash: 'sha256:91c4…8fa2',
  guideline_version: 'bdd100k-v1', taxonomy_version: '2026.10', out_of_scope_shapes: 3,
};

export const configVersion = {
  id: 4, name: 'BDD100K baseline', status: 'published', engines: { geometry: { enabled: true } },
  thresholds: { risk: 0.72 }, models: {}, created_by: 7, created_at: '2026-10-12T02:15:00Z',
  published_at: '2026-10-12T02:20:00Z',
};

export const run = {
  id: 31, snapshot_id: 18, config_version_id: 4, status: 'completed', is_final: true,
  created_at: '2026-10-12T03:00:00Z',
};

export const issue = {
  id: 902, frame_id: 3301, origin: 'engine', family: 'geometry', severity: 'major',
  status: 'confirmed', description: 'Bounding box vượt biên ảnh', review_decisions: [],
};

export const rework = {
  id: 73, issue_id: 902, annotator_user_id: 28, status: 'fix_pending',
  original_revision: 'sha256:91c4…8fa2', submitted_revision: null,
  due_at: '2026-10-15T10:00:00Z', cvat_deep_link: 'http://localhost:8080/tasks/19/jobs/44',
};

export const reference = {
  id: 9, snapshot_id: 18, gt_checksum: 'sha256:5f2a…c811', mapping_version: 'bdd100k-v1',
  matching_threshold: 0.5, minimum_area: 16, algorithm_version: 'match-v1', status: 'draft',
  created_by: 7, locked_by: null, locked_at: null,
};

export const evaluation = {
  id: 14, status: 'queued', snapshot_id: 18, run_id: 31, reference_id: 9,
  score_version: 'score-v0', parameters: { minimum_sample: 100 }, metrics: null,
  leakage_check: 'not_checked', created_by: 7, created_at: '2026-10-12T04:00:00Z',
};

export const waiver = {
  id: 6, run_id: 31, condition: 'coverage', reason: 'Detector bảo trì',
  evidence: 'OPS-241', expires_at: '2026-10-20T00:00:00Z', requested_by: 12,
  approved_by: null, status: 'pending',
};
