/**
 * Canonical illustrative data for FE-01 Quality Control Home & Summary.
 * Sourced 1:1 from canonical design specifications:
 * - docs/design/screens/Main.dc.html
 * - docs/design/screens/Dashboard.dc.html
 *
 * NOTE: These fixtures are strictly read-only illustrative data used when backend
 * aggregation endpoints are not yet available or in no-backend preview mode.
 * Fixture IDs MUST NEVER enter auth dataset state or be sent in API mutation requests.
 */

export interface IllustrativeHomeDataset {
  id: string;
  name: string;
  version?: string;
  cvatProjectId?: number;
  subLabel?: string;
  tasksJobs: string;
  frames: string;
  qcRun: string;
  qcRunStatus?: string | null;
  qcRunTone?: 'success' | 'warning' | 'danger' | 'info' | null;
  qcRunTime?: string;
  coverage: string;
  openIssues: string;
  gate: string;
  gateTone?: 'success' | 'warning' | 'danger' | 'info' | null;
  actionHref: string;
  actionTip: string;
}

export const ILLUSTRATIVE_HOME_DATASETS: IllustrativeHomeDataset[] = [
  {
    id: 'road-vision-urban-v14',
    name: 'Road Vision Urban',
    version: 'v1.4',
    cvatProjectId: 31,
    tasksJobs: '3 / 7',
    frames: '12,500',
    qcRun: '#QC-091',
    qcRunStatus: 'Partial',
    qcRunTone: 'warning',
    qcRunTime: '2026-10-04 06:58',
    coverage: '92.4%',
    openIssues: '192',
    gate: 'Blocked',
    gateTone: 'danger',
    actionHref: '/?view=summary',
    actionTip: 'Tiếp tục làm việc với Dataset này',
  },
  {
    id: 'road-vision-urban-v13',
    name: 'Road Vision Urban',
    version: 'v1.3',
    cvatProjectId: 31,
    subLabel: 'CVAT project #31 · chỉ xem',
    tasksJobs: '2 / 3',
    frames: '11,800',
    qcRun: '#QC-077',
    qcRunStatus: 'Checked',
    qcRunTone: 'success',
    qcRunTime: '2026-09-10 08:30',
    coverage: '97.2%',
    openIssues: '0',
    gate: 'Released',
    gateTone: 'success',
    actionHref: '/reports/releases',
    actionTip: 'Xem lịch sử phát hành',
  },
  {
    id: 'road-vision-highway-v09',
    name: 'Road Vision Highway',
    version: 'v0.9',
    cvatProjectId: 34,
    tasksJobs: '2 / 3',
    frames: '5,600',
    qcRun: '#QC-085',
    qcRunStatus: 'Checked',
    qcRunTone: 'success',
    qcRunTime: '2026-09-30 14:20',
    coverage: '98.9%',
    openIssues: '6',
    gate: 'Ready · chờ duyệt',
    gateTone: 'warning',
    actionHref: '/?view=summary',
    actionTip: 'Mở Dataset này',
  },
  {
    id: 'parking-lot-v03',
    name: 'Parking Lot',
    version: 'v0.3',
    cvatProjectId: 37,
    tasksJobs: '1 / 2',
    frames: '3,000',
    qcRun: 'Chưa có Quality Control Run',
    qcRunStatus: null,
    qcRunTone: null,
    coverage: '—',
    openIssues: '—',
    gate: 'Not checked',
    gateTone: null,
    actionHref: '/analysis',
    actionTip: 'Tạo snapshot đầu tiên',
  },
];

export interface IllustrativeMetric {
  key: string;
  value: string;
  note: string;
  isWarn?: boolean;
  isBad?: boolean;
  progressPct?: number;
}

export const ILLUSTRATIVE_METRICS: IllustrativeMetric[] = [
  {
    key: 'Frame trong phạm vi',
    value: '12,500',
    note: '48,912 object · 7 job',
  },
  {
    key: 'Coverage',
    value: '92.4%',
    note: 'Ngưỡng yêu cầu 95%',
    isWarn: true,
    progressPct: 92.4,
  },
  {
    key: 'Candidate issue',
    value: '384',
    note: '512 bản ghi thô → 384 sau khi gộp trùng',
  },
  {
    key: 'Lỗi đã xác nhận',
    value: '126',
    note: '3 lỗi nghiêm trọng chưa đóng',
    isBad: true,
  },
];

export interface IllustrativeEngine {
  name: string;
  status: string;
  badgeTone?: 'success' | 'info' | 'warning' | 'danger' | null;
  coverage: string;
  note: string;
}

export const ILLUSTRATIVE_ENGINES: IllustrativeEngine[] = [
  {
    name: 'Schema / Taxonomy',
    status: 'Checked',
    badgeTone: 'success',
    coverage: '100%',
    note: 'Không phát hiện lỗi cấu trúc',
  },
  {
    name: 'Geometry',
    status: 'Issue found',
    badgeTone: 'info',
    coverage: '98.2%',
    note: '74 candidate issue',
  },
  {
    name: 'Duplicate / Overlap',
    status: 'Issue found',
    badgeTone: 'info',
    coverage: '98.2%',
    note: '41 candidate issue',
  },
  {
    name: 'Mô hình độc lập',
    status: 'Partial',
    badgeTone: 'warning',
    coverage: '86.7%',
    note: 'Job 2273, 2274 chưa chạy hết',
  },
  {
    name: 'Mô hình thị giác – ngôn ngữ',
    status: 'Failed',
    badgeTone: 'danger',
    coverage: '0%',
    note: 'Hết thời gian chờ · có thể chạy lại',
  },
  {
    name: 'Metric',
    status: 'Not checked',
    badgeTone: null,
    coverage: '—',
    note: 'Chưa có Ground Truth cho phạm vi này',
  },
];

export interface IllustrativeReviewQueue {
  label: string;
  count: string;
  widthClass: string;
  hint: string;
}

export const ILLUSTRATIVE_REVIEW_QUEUES: IllustrativeReviewQueue[] = [
  {
    label: 'Ưu tiên theo rủi ro',
    count: '124',
    widthClass: 'lx-w-pct-38',
    hint: 'Đã review 47 / 124',
  },
  {
    label: 'Kiểm tra ngẫu nhiên',
    count: '50',
    widthClass: 'lx-w-pct-20',
    hint: 'Đã review 10 / 50',
  },
  {
    label: 'Chưa chắc chắn / Chuyển cấp trên',
    count: '18',
    widthClass: 'lx-w-pct-0',
    hint: 'Chờ phân xử tại Escalations',
  },
];

export interface IllustrativeTask {
  id: string;
  name: string;
  sub: string;
  jobs: string;
  frames: string;
  coverage: string;
  isWarnCoverage?: boolean;
  candidates: string;
  confirmed: string;
  gate: string;
  gateTone: 'success' | 'warning' | 'danger';
}

export const ILLUSTRATIVE_TASKS: IllustrativeTask[] = [
  {
    id: 'T-118',
    name: 'T-118 · Urban day',
    sub: 'Job 2270 – 2272',
    jobs: '3',
    frames: '600',
    coverage: '98.0%',
    candidates: '65',
    confirmed: '21',
    gate: 'Đạt',
    gateTone: 'success',
  },
  {
    id: 'T-119',
    name: 'T-119 · Urban night',
    sub: 'Job 2273 – 2274',
    jobs: '2',
    frames: '6,000',
    coverage: '86.7%',
    isWarnCoverage: true,
    candidates: '208',
    confirmed: '69',
    gate: 'Blocked',
    gateTone: 'danger',
  },
  {
    id: 'T-120',
    name: 'T-120 · Urban rain',
    sub: 'Job 2275 – 2276',
    jobs: '2',
    frames: '5,900',
    coverage: '97.6%',
    candidates: '111',
    confirmed: '36',
    gate: 'Partial',
    gateTone: 'warning',
  },
];

export interface IllustrativeCandidateCategory {
  label: string;
  widthClass: string;
  count: string;
}

export const ILLUSTRATIVE_CANDIDATE_CATEGORIES: IllustrativeCandidateCategory[] = [
  { label: 'Sai nhãn', widthClass: 'lx-w-pct-100', count: '142' },
  { label: 'Hình học', widthClass: 'lx-w-pct-52', count: '74' },
  { label: 'Trùng / chồng lấn', widthClass: 'lx-w-pct-29', count: '41' },
  { label: 'Thiếu object', widthClass: 'lx-w-pct-85', count: '121' },
  { label: 'Thuộc tính / Track', widthClass: 'lx-w-pct-4', count: '6' },
];
