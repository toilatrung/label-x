/**
 * Dữ liệu minh họa cho Snapshot và Lịch sử snapshot, lấy từ docs/design/screens/Snapshot.dc.html và SnapshotHistory.dc.html.
 * Chỉ dùng cho phần thiết kế chưa có API (revision, seed, cấu hình kiểm tra, Quality Control Run theo Snapshot) hoặc khi không tải được Dataset.
 * TODO(backend): GET /api/datasets/{id}/revisions/ (danh sách annotation revision), seed lấy mẫu và cấu hình kiểm tra gắn với Snapshot
 *   (trường seed, config_version_id, models trên Snapshot), GET /api/snapshots/{id}/runs/ (Quality Control Run đã chạy trên Snapshot).
 * Mọi nơi dùng phải kèm SampleDataBadge và NotConnectedNotice.
 */
export const SAMPLE_SNAPSHOT_FORM = {
  dataset: 'Road Vision Urban · v1.4',
  revisions: ['a91f3c · mới nhất (2026-10-04 06:41)', '7be204 · 2026-10-02 17:10'],
  seed: '20261004',
  tasks: [
    { key: 'T-118', name: 'T-118 · Urban day', jobs: '3 job', frames: '600' },
    { key: 'T-119', name: 'T-119 · Urban night', jobs: '2 job', frames: '6,000' },
    { key: 'T-120', name: 'T-120 · Urban rain', jobs: '2 job', frames: '5,900' },
  ],
  hint: 'Hiện chọn 3 task · 7 job · 12,500 frame.',
} as const;

export const SAMPLE_IN_USE = {
  id: 'SNP-014', revision: 'a91f3c', taxonomy: 'v3', guideline: 'v1.2',
  models: 'Detector v2.3 · Classifier v1.8', config: 'v7', seed: '20261004', createdBy: 'Mocking User · 2026-10-04 06:50',
} as const;

/** Ba trường của "Snapshot đang dùng" chưa có trong Snapshot API. */
export const SAMPLE_IN_USE_EXTRA: ReadonlyArray<[string, string, boolean]> = [
  ['Mô hình độc lập', SAMPLE_IN_USE.models, false],
  ['Cấu hình kiểm tra', SAMPLE_IN_USE.config, false],
  ['Seed lấy mẫu', SAMPLE_IN_USE.seed, true],
];

export type HistoryTone = 'info' | 'success' | '';
export const SAMPLE_HISTORY_ROWS: ReadonlyArray<{
  id: string; dataset: string; revision: string; frames: string; run: string; status: string; tone: HistoryTone; selected?: boolean;
}> = [
  { id: 'SNP-014', dataset: 'Road Vision Urban · v1.4', revision: 'a91f3c', frames: '12,500', run: '#QC-091', status: 'Đang dùng', tone: 'info', selected: true },
  { id: 'SNP-013', dataset: 'Road Vision Urban · v1.4', revision: '7be204', frames: '12,500', run: '#QC-088', status: 'Đã thay thế', tone: '' },
  { id: 'SNP-012', dataset: 'Road Vision Highway · v0.9', revision: 'c40d19', frames: '5,600', run: '#QC-085', status: 'Đã khoá', tone: 'success' },
  { id: 'SNP-011', dataset: 'Road Vision Urban · v1.3', revision: 'f02a6d', frames: '11,800', run: '#QC-077', status: 'Đã khoá', tone: 'success' },
];
