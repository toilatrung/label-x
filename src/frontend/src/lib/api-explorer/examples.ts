export const session = {
  user: { id: 7, username: 'qa.lead', full_name: 'QA Lead' },
  roles: [{ role: 'qa_lead', dataset_id: 12 }],
  identity_mapping: { status: 'mapped', cvat_user_id: 41 },
};

export const snapshot = {
  id: 14, dataset_id: 14, display_id: 'SNP-014', status: 'locked', revision_hash: 'a91f3c',
  guideline_version: 'v1.2', taxonomy_version: 'v3', frame_count: 12500, seed: 20261004,
  config_version_id: 7, models: ['Detector v2.3', 'Classifier v1.8'], created_by_name: 'Mocking User',
  created_at: '2026-10-04T06:50:00Z', out_of_scope_shapes: 3,
};

export const configVersion = {
  id: 7, name: 'Road Vision Urban v7', status: 'published', engines: {
    schema: { enabled: true, label: 'Schema / Taxonomy', note: 'Taxonomy v3 · thuộc tính bắt buộc theo từng lớp' },
    geometry: { enabled: true, label: 'Geometry', tolerance_px: 2, minimum_area: 24 },
    duplicate: { enabled: true, label: 'Duplicate / Overlap', iou_threshold: 0.85 },
    detector: { enabled: true, label: 'Mô hình độc lập', model: 'Detector v2.3', confidence_threshold: 0.6 },
    vision_language: { enabled: true, label: 'Mô hình thị giác – ngôn ngữ', max_candidates: 400 },
    metric: { enabled: false, label: 'Metric', reason: 'Chưa có Ground Truth' },
  },
  thresholds: { coverage: 0.95, open_critical_issues: 0, residual_error_rate: 0.05, reviewer_agreement: 0.9, verified_rework: 1 },
  sampling: { random_rate: 0.008, random_minimum: 100, risk_rate: 0.008, seed_mode: 'generated_and_persisted' },
  models: { detector: 'v2.3', classifier: 'v1.8' }, created_by: 7, created_at: '2026-10-04T06:45:00Z',
  published_at: '2026-10-04T06:47:00Z',
};

export const run = {
  id: 91, display_id: 'QC-091', snapshot_id: 14, config_version_id: 7, status: 'partial', is_final: true,
  created_at: '2026-10-04T06:58:00Z',
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
