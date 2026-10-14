import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { QualityControlHome } from '@/components/overview/QualityControlHome';
import { QualitySummary } from '@/components/overview/QualitySummary';
import { TopBar } from '@/components/layout/TopBar';
import Home from '@/app/page';
import { AuthProvider, useAuth } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';
import type { Dataset } from '@/lib/snapshots/api';

const mockPush = vi.fn();
let currentSearchParam = '';

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(currentSearchParam),
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
}));

/* Số liệu mẫu cũ của API Explorer không được xuất hiện như dữ liệu thật. */
const FORBIDDEN_SAMPLE_TEXT = /92\.4%|QC-091|Road Vision Highway$|12,500|Urban day/;

const datasetsPage1: Dataset[] = [
  { id: 1, name: 'labelx-dev', cvat_project_id: 1, taxonomy_version: 'v1.4', guideline_version: 'v1.2' },
  { id: 2, name: 'labelx-drift-probe', cvat_project_id: 2, taxonomy_version: null, guideline_version: null },
];
const datasetsPage2: Dataset[] = [
  { id: 3, name: 'Parking Lot Real', cvat_project_id: 37, taxonomy_version: null, guideline_version: null },
];

// Shape lấy từ backend thật (dataset 1, run 107) ngày 2026-10-13.
const tasksByDataset: Record<number, unknown[]> = {
  1: [{ cvat_task_id: 4, name: 'cavat_test', jobs: [
    { cvat_job_id: 4, assignee_cvat_user_id: 1, updated_date: '2026-10-12T17:22:56Z', frame_count: 1 },
    { cvat_job_id: 9, assignee_cvat_user_id: null, updated_date: '2026-10-12T17:22:56Z', frame_count: 587 },
  ] }],
  2: [{ cvat_task_id: 7, name: 'drift', jobs: [{ cvat_job_id: 11, assignee_cvat_user_id: null, updated_date: null, frame_count: 30 }] }],
  3: [],
};

const run107 = {
  id: 107, snapshot_id: 3, config_version_id: 2, seed: 20261010, status: 'completed', is_final: false,
  origin_run_id: null, score_version: 'score_v0', model_artifact: null,
  engines: [{ engine: 'duplicate', status: 'checked', reason: 'not_applicable', failed_units: 0 }],
  created_by: 16, created_at: '2026-10-11T18:54:41+07:00', finished_at: '2026-10-11T18:55:45+07:00',
};
const run111 = { ...run107, id: 111, snapshot_id: 47, status: 'partial', created_at: '2026-10-11T21:30:55+07:00' };
// GET /api/datasets/summary/ (MBE-06) quyết định run mới nhất và số issue đang mở.
const summaries = [
  { dataset_id: 1, name: 'labelx-dev', snapshot_count: 11, latest_snapshot_id: 3, latest_run_id: 107, open_issue_count: 5, reviewed_ratio: 0 },
  { dataset_id: 2, name: 'labelx-drift-probe', snapshot_count: 3, latest_snapshot_id: 47, latest_run_id: 111, open_issue_count: 0, reviewed_ratio: 0 },
  { dataset_id: 3, name: 'Parking Lot Real', snapshot_count: 0, latest_snapshot_id: null, latest_run_id: null, open_issue_count: 0, reviewed_ratio: null },
];
const metrics107 = { run_id: 107, status: 'completed', frames_total: 588, frames_reviewed: 7, issues_total: 12,
  issues_by_family: { E3: 12 }, issues_by_state: { pending_review: 3, confirmed: 4, fix_pending: 2, resolved: 1, rejected: 2 }, reviewed_ratio: 0.012 };
const engines107 = { run_id: 107, engines: [
  { engine: 'duplicate', status: 'checked', units_total: 588, units_failed: 0, candidates: 163, duration_ms: 75 },
  { engine: 'schema', status: 'not_checked', units_total: 0, units_failed: 0, candidates: 0, duration_ms: null },
] };
const tasksQuality107 = { next: null, previous: null, results: [{ cvat_task_id: 4, name: 'cavat_test', frames: 588, issues: 12, issue_rate: 0.02, reviewed_ratio: 0.012 }] };
const categories107 = { run_id: 107, total: 163, categories: [{ family: 'E3', count: 150, share: 0.92 }, { family: 'E2', count: 13, share: 0.08 }] };

const gateFailed = {
  run_id: 107, source_run_id: 107, source_reason: 'no_valid_final', status: 'failed',
  conditions: [
    { name: 'coverage', status: 'failed', observed: 0.6620689655172414, threshold: 1.0, waiver_id: null, reason: 'no_valid_final' },
    { name: 'open_critical_issues', status: 'passed', observed: 0, threshold: 0, waiver_id: null, reason: null },
    { name: 'rework_verified', status: 'passed', observed: 1, threshold: 1, waiver_id: null, reason: null },
  ],
};
const gatePassed = { ...gateFailed, run_id: 111, status: 'passed', conditions: [
  { name: 'coverage', status: 'passed', observed: 0.99, threshold: 0.95, waiver_id: null, reason: null },
  { name: 'open_critical_issues', status: 'passed', observed: 2, threshold: 0, waiver_id: null, reason: null },
] };

const ledger107 = [
  { engine: 'duplicate', status: 'checked', required: true, unit: 'frame', total: 588, eligible: 576, excluded: 12,
    applicability_version: '1.0.0', completed: 576, failed: 0, pending: 0, not_checked: 12, not_checked_reasons: { not_applicable: 12 }, coverage: 1.0 },
  { engine: 'schema', status: 'not_checked', required: true, unit: 'frame', total: 588, eligible: 588, excluded: 0,
    applicability_version: '1.0.0', completed: 0, failed: 0, pending: 0, not_checked: 588, not_checked_reasons: { no_reference: 588 }, coverage: 0.0 },
];

type Handler = (url: URL, req: Request) => Response | Promise<Response> | undefined;

function setupMockEnv(options: {
  datasets?: (req: Request) => Response | Promise<Response>;
  sessionDatasetId?: number;
  extra?: Handler;
} = {}) {
  const authApi = installMockAuthApi();
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  const fetchSpy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : new Request(input, init);
    const url = new URL(req.url, 'http://localhost');
    calls.push(url.pathname + url.search);
    const extraRes = options.extra ? await options.extra(url, req) : undefined;
    if (extraRes) return extraRes;
    const path = url.pathname;
    if (path === '/api/datasets/') {
      return options.datasets ? options.datasets(req) : Response.json({ next: null, previous: null, results: datasetsPage1 });
    }
    let m = path.match(/^\/api\/datasets\/(\d+)\/tasks\/$/);
    if (m) return Response.json(tasksByDataset[Number(m[1])] ?? []);
    if (path === '/api/datasets/summary/') return Response.json({ next: null, previous: null, results: summaries });
    m = path.match(/^\/api\/runs\/(\d+)\/(gate|ledger|candidates|metrics|engines|tasks-quality|candidate-categories|review-volume)?\/?$/);
    if (m) {
      const id = Number(m[1]);
      if (m[2] === 'review-volume') return Response.json({ run_id: id, granularity: url.searchParams.get('granularity'), points: [] });
      if (m[2] === 'metrics') return Response.json({ ...metrics107, run_id: id });
      if (m[2] === 'engines') return Response.json({ ...engines107, run_id: id });
      if (m[2] === 'tasks-quality') return Response.json(tasksQuality107);
      if (m[2] === 'candidate-categories') return Response.json({ ...categories107, run_id: id });
      if (m[2] === 'gate') return Response.json(id === 111 ? gatePassed : { ...gateFailed, run_id: id });
      if (m[2] === 'ledger') return Response.json(ledger107);
      if (m[2] === 'candidates') return Response.json({ next: 'http://localhost/api/runs/107/candidates/?cursor=x', previous: null, raw_count: null, dedup_count: 163, results: [] });
      return Response.json(id === 111 ? run111 : run107);
    }
    m = path.match(/^\/api\/queues\/(risk|random)\/$/);
    if (m) {
      return Response.json(m[1] === 'risk'
        ? { name: 'risk', run_id: 107, total: 588, counts: { unreviewed: 580, in_review: 2, incomplete: 0, reviewed: 4, awaiting_followup: 1, completed: 1 } }
        : { name: 'random', run_id: 107, total: 59, counts: { unreviewed: 59, in_review: 0, incomplete: 0, reviewed: 0, awaiting_followup: 0, completed: 0 } });
    }
    if (path === '/api/escalations/') return Response.json({ next: null, previous: null, results: [] });
    if (path === '/api/rework/') {
      return Response.json({ next: null, previous: null, results: [], counts: { fix_pending: 4, recheck_pending: 1, resolved: 0, reopened: 0 } });
    }
    if (path === '/api/auth/session/' && options.sessionDatasetId !== undefined) {
      return Response.json({
        user: { id: 4, username: 'reviewer', display_name: 'Người kiểm tra mẫu' },
        roles: [{ role: 'reviewer', dataset_id: options.sessionDatasetId }],
        identity_mapping: { status: 'mapped', cvat_user_id: 104 },
      });
    }
    return originalFetch(req);
  });
  vi.stubGlobal('fetch', fetchSpy);
  return { authApi, fetchSpy, calls };
}

function renderWithProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (node: React.ReactElement) => (
    <QueryClientProvider client={client}><AuthProvider>{node}</AuthProvider></QueryClientProvider>
  );
  const result = render(wrap(ui));
  return { ...result, rerender: (node: React.ReactElement) => result.rerender(wrap(node)) };
}

const dataset1: Dataset = datasetsPage1[0];

describe('Overview: Quality Control Home và Quality Summary dùng dữ liệu thật', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentSearchParam = '';
  });

  describe('Quality Control Home', () => {
    it('hiển thị task/job/frame, run gần nhất, coverage và gate thật từ API cho từng dòng', async () => {
      const { authApi, calls } = setupMockEnv();
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);

      const row = (await screen.findByText('labelx-dev')).closest('tr')!;
      await waitFor(() => expect(within(row).getByText('66.2%')).toBeDefined());
      const cells = row.querySelectorAll('td');
      expect(cells[1].textContent).toBe('1 / 2');
      expect(cells[2].textContent).toBe('588');
      expect(within(row).getByText('#107')).toBeDefined();
      expect(within(row).getByText('Completed')).toBeDefined();
      expect(cells[5].textContent).toBe('5');
      expect(within(row).getByText('Blocked')).toBeDefined();

      const row2 = screen.getByText('labelx-drift-probe').closest('tr')!;
      await waitFor(() => expect(within(row2).getByText('Đạt')).toBeDefined());
      expect(within(row2).getByText('99.0%')).toBeDefined();

      expect(calls.filter((c) => c === '/api/datasets/summary/')).toHaveLength(1);
      expect(calls.some((c) => c.startsWith('/api/runs/?'))).toBe(false);
      expect(calls).toContain('/api/runs/107/');
      expect(calls).toContain('/api/runs/107/gate/');
      expect(calls).toContain('/api/datasets/1/tasks/');
      expect(document.body.textContent).not.toMatch(FORBIDDEN_SAMPLE_TEXT);
      expect(screen.getByText('2 / 2 dataset')).toBeDefined();
    });

    it('Dataset chưa có run: hiện trạng thái thật và nút tạo snapshot đầu tiên', async () => {
      const onDatasetSelect = vi.fn();
      const { authApi } = setupMockEnv({ datasets: () => Response.json({ next: null, previous: null, results: datasetsPage2 }) });
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome onDatasetSelect={onDatasetSelect} />);

      const row = (await screen.findByText('Parking Lot Real')).closest('tr')!;
      expect(await within(row).findByText('Chưa có Quality Control Run')).toBeDefined();
      expect(within(row).getByText('Not checked')).toBeDefined();
      fireEvent.click(within(row).getByRole('button', { name: 'Tạo snapshot đầu tiên' }));
      expect(onDatasetSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 3 }));
      expect(mockPush).toHaveBeenCalledWith('/analysis');
    });

    it('lỗi tải danh sách: không hiển thị dữ liệu mẫu, có Thử lại tải lại thật', async () => {
      let call = 0;
      const { authApi } = setupMockEnv({ datasets: () => (++call === 1
        ? Response.json({ detail: 'Database unavailable' }, { status: 500 })
        : Response.json({ next: null, previous: null, results: datasetsPage1 })) });
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);

      expect(await screen.findByText(/Không thể tải danh sách Dataset/)).toBeDefined();
      expect(document.querySelector('tbody')).toBeNull();
      expect(document.body.textContent).not.toMatch(FORBIDDEN_SAMPLE_TEXT);
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
      expect(await screen.findByText('labelx-dev')).toBeDefined();
    });

    it('danh sách rỗng: trạng thái trống thật', async () => {
      const { authApi } = setupMockEnv({ datasets: () => Response.json({ next: null, previous: null, results: [] }) });
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);
      expect(await screen.findByText(/Chưa có Dataset nào trong phạm vi quyền của bạn/)).toBeDefined();
      expect(screen.getByText('0 / 0 dataset')).toBeDefined();
    });

    it('lỗi số liệu của một dòng có Thử lại riêng cho dòng đó', async () => {
      let gateCalls = 0;
      const { authApi } = setupMockEnv({ extra: (url) => {
        if (url.pathname === '/api/runs/107/gate/' && ++gateCalls === 1) return Response.json({ detail: 'boom' }, { status: 500 });
        return undefined;
      } });
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);

      const row = (await screen.findByText('labelx-dev')).closest('tr')!;
      expect(await within(row).findByText('Không tải được số liệu.')).toBeDefined();
      fireEvent.click(within(row).getByRole('button', { name: 'Thử lại' }));
      await waitFor(() => expect(within(row).getByText('66.2%')).toBeDefined());
      expect(within(row).queryByText('Không tải được số liệu.')).toBeNull();
    });

    it('tách kích hoạt dòng khỏi nút hành động trong dòng', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);
      await screen.findByText('labelx-dev');

      const rows = screen.getAllByRole('row');
      fireEvent.keyDown(rows[1], { key: 'Enter' });
      expect(rows[1].getAttribute('aria-selected')).toBe('true');

      const actions = await screen.findAllByLabelText('Tiếp tục làm việc với Dataset này');
      fireEvent.click(actions[0]);
      expect(mockPush).toHaveBeenCalledWith('/?view=summary');
      fireEvent.keyDown(actions[1], { key: ' ' });
      expect(rows[2].getAttribute('aria-selected')).toBeNull();
    });

    it('không gắn guideline/taxonomy version thành tag version Dataset; caption đồng bộ không bịa', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);
      const row = (await screen.findByText('labelx-dev')).closest('tr')!;
      expect(row.querySelector('.lx-tag')).toBeNull();
      expect(screen.getByText('Đồng bộ CVAT —')).toBeDefined();
      expect(screen.queryByText('Đồng bộ CVAT 2 phút trước')).toBeNull();
      expect(screen.getByText('Quality Control Run gần nhất')).toBeDefined();
    });
  });

  describe('Search và phân trang', () => {
    it('tự quét trang sau khi người dùng gõ trước khi trang 1 về', async () => {
      let release: () => void;
      const gate = new Promise<void>((resolve) => { release = resolve; });
      const { authApi } = setupMockEnv({ datasets: async (req) => {
        if (!new URL(req.url).searchParams.get('cursor')) {
          await gate;
          return Response.json({ next: 'http://localhost/api/datasets/?cursor=page2', previous: null, results: datasetsPage1 });
        }
        return Response.json({ next: null, previous: null, results: datasetsPage2 });
      } });
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);
      fireEvent.change(screen.getByRole('searchbox', { name: 'Tìm dataset' }), { target: { value: 'Parking' } });
      release!();
      expect(await screen.findByText('Parking Lot Real')).toBeDefined();
    });

    it('phát hiện cursor lặp', async () => {
      const { authApi } = setupMockEnv({ datasets: (req) => Response.json({
        next: 'http://localhost/api/datasets/?cursor=loop', previous: null,
        results: new URL(req.url).searchParams.get('cursor') ? datasetsPage2 : datasetsPage1,
      }) });
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);
      fireEvent.change(await screen.findByRole('searchbox', { name: 'Tìm dataset' }), { target: { value: 'Nonexistent' } });
      expect(await screen.findByText(/Phát hiện vòng lặp phân trang từ server/)).toBeDefined();
    });

    it('Thử lại tải trang sau lỗi phân trang, giữ trang trước', async () => {
      let fail = true;
      const { authApi } = setupMockEnv({ datasets: (req) => {
        if (!new URL(req.url).searchParams.get('cursor')) {
          return Response.json({ next: 'http://localhost/api/datasets/?cursor=page2', previous: null, results: datasetsPage1 });
        }
        return fail ? Response.json({ detail: 'timeout' }, { status: 504 }) : Response.json({ next: null, previous: null, results: datasetsPage2 });
      } });
      await authApi.signIn('admin');
      renderWithProviders(<QualityControlHome />);
      fireEvent.click(await screen.findByRole('button', { name: 'Tải thêm dataset' }));
      expect(await screen.findByText(/Không thể tải thêm trang/)).toBeDefined();
      fail = false;
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại tải trang' }));
      expect(await screen.findByText('Parking Lot Real')).toBeDefined();
      expect(screen.getByText('labelx-dev')).toBeDefined();
    });
  });

  describe('Quality Summary', () => {
    it('ghép run, gate, ledger, candidate, hàng đợi, escalation, rework và task từ API thật', async () => {
      const { authApi, calls } = setupMockEnv();
      await authApi.signIn('reviewer');
      renderWithProviders(<QualitySummary currentDataset={dataset1} />);

      expect(await screen.findByText(/Tình trạng kiểm tra của labelx-dev · Quality Control Run #107 · Snapshot SNP-003\./)).toBeDefined();
      expect(await screen.findByText('Release blocked')).toBeDefined();
      expect(await screen.findByText('Coverage 66.2% chưa đạt ngưỡng 100.0% · 0 lỗi nghiêm trọng chưa đóng · 4 yêu cầu sửa chờ xử lý.')).toBeDefined();
      expect(screen.getByText('Ngưỡng yêu cầu 100.0%')).toBeDefined();
      expect(await screen.findByText('163')).toBeDefined();
      expect(screen.getByText('Sau khi gộp trùng; server chưa trả số bản ghi thô')).toBeDefined();
      // Lỗi đã xác nhận = confirmed + fix_pending + resolved (không tính pending_review, rejected).
      const confirmedMetric = screen.getByText('Lỗi đã xác nhận').closest('.lx-metric')!;
      expect(confirmedMetric.querySelector('.lx-metric__v')!.textContent).toBe('7');
      const frameMetric = screen.getByText('Frame trong phạm vi').closest('.lx-metric')!;
      expect(frameMetric.querySelector('.lx-metric__v')!.textContent).toBe('588');
      expect(screen.getByText('2 job · 1 task trong CVAT')).toBeDefined();

      // Engine từ ledger, kèm cảnh báo đơn vị bị loại khỏi mẫu số.
      expect(await screen.findByText('Duplicate / Overlap')).toBeDefined();
      expect(screen.getByText('Schema / Taxonomy')).toBeDefined();
      expect(screen.getByText(/^163 candidate issue · 576 \/ 576 frame hoàn tất/)).toBeDefined();
      expect(screen.getByText(/12 frame loại khỏi mẫu số \(12 ngoài phạm vi áp dụng; applicability 1\.0\.0\)/)).toBeDefined();
      expect(screen.getByText(/chưa kiểm tra: 588 chưa có Ground Truth/)).toBeDefined();

      // Khối lượng review từ /api/queues/{risk,random}/ và /api/escalations/.
      expect(await screen.findByText('Đã review 6 / 588')).toBeDefined();
      expect(screen.getByText('Đã review 0 / 59')).toBeDefined();
      expect(screen.getByText('Đã xử lý').parentElement!.textContent).toBe('Đã xử lý7');

      // Theo Task từ runs/{id}/tasks-quality/, Job ghép từ datasets/{id}/tasks/.
      const taskRow = await screen.findByRole('row', { name: /T-4 · cavat_test/ });
      const cells = taskRow.querySelectorAll('td');
      expect(cells[1].textContent).toBe('2');
      expect(cells[2].textContent).toBe('588');
      await waitFor(() => expect(within(taskRow).getByText('Job 4 – 9 · 12 issue · đã review 1.2%')).toBeDefined());

      // Candidate theo loại lỗi từ candidate-categories.
      const categoryCard = screen.getByText('Candidate theo loại lỗi').closest('section')!;
      expect(within(categoryCard).getByText('Trùng / chồng lấn')).toBeDefined();
      expect(within(categoryCard).getByText('150')).toBeDefined();
      expect(within(categoryCard).getByText('Sai nhãn')).toBeDefined();

      // Chỉ còn một vùng chưa có API (cột theo Task), cảnh báo đúng nguyên văn.
      expect(screen.getAllByText(/Chức năng vẫn chưa được kết nối với server/)).toHaveLength(1);
      expect(document.body.textContent).not.toMatch(FORBIDDEN_SAMPLE_TEXT);
      expect(screen.queryByText('124')).toBeNull();
      expect(screen.queryByText('Dữ liệu minh họa')).toBeNull();
      expect(screen.queryByText(/NaN/)).toBeNull();

      expect(calls).toEqual(expect.arrayContaining([
        '/api/datasets/summary/', '/api/runs/107/', '/api/runs/107/metrics/', '/api/runs/107/engines/',
        '/api/runs/107/tasks-quality/', '/api/runs/107/candidate-categories/', '/api/runs/107/gate/', '/api/runs/107/ledger/',
        '/api/runs/107/candidates/?page_size=1', '/api/queues/risk/?run_id=107', '/api/queues/random/?run_id=107',
        '/api/escalations/?run=107', '/api/rework/?dataset_id=1', '/api/datasets/1/tasks/',
      ]));
    });

    it('tasks-quality 502 (CVAT không còn task của snapshot): hiện lỗi + Thử lại, không fallback', async () => {
      let tqCalls = 0;
      const { authApi } = setupMockEnv({ extra: (url) => (url.pathname === '/api/runs/107/tasks-quality/' && ++tqCalls === 1
        ? Response.json({ code: 'BUSINESS_RULE_UNMET', message: 'CVAT không còn task của snapshot.', details: {} }, { status: 502 }) : undefined) });
      await authApi.signIn('reviewer');
      renderWithProviders(<QualitySummary currentDataset={dataset1} />);
      const card = (await screen.findByText(/Không tải được chất lượng theo Task/)).closest('section')!;
      expect(within(card).queryByRole('row')).toBeNull();
      fireEvent.click(within(card).getByRole('button', { name: 'Thử lại' }));
      expect(await within(card).findByRole('row', { name: /T-4 · cavat_test/ })).toBeDefined();
      expect(tqCalls).toBe(2);
    });

    it('lỗi ledger hiện Thử lại và tải lại được', async () => {
      let ledgerCalls = 0;
      const { authApi } = setupMockEnv({ extra: (url) => (url.pathname === '/api/runs/107/ledger/' && ++ledgerCalls === 1
        ? Response.json({ detail: 'boom' }, { status: 500 }) : undefined) });
      await authApi.signIn('reviewer');
      renderWithProviders(<QualitySummary currentDataset={dataset1} />);

      expect(await screen.findByText(/Không tải được trạng thái engine/)).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
      expect(await screen.findByText('Duplicate / Overlap')).toBeDefined();
      expect(ledgerCalls).toBe(2);
    });

    it('escalation 403 hiển thị thiếu quyền, không chặn các vùng khác', async () => {
      const { authApi } = setupMockEnv({ extra: (url) => (url.pathname === '/api/escalations/'
        ? Response.json({ code: 'FORBIDDEN', message: 'no' }, { status: 403 }) : undefined) });
      await authApi.signIn('reviewer');
      renderWithProviders(<QualitySummary currentDataset={dataset1} />);
      expect(await screen.findByText('Không có quyền xem trong phạm vi này')).toBeDefined();
      expect(await screen.findByText('Đã review 6 / 588')).toBeDefined();
    });

    it('run chưa có hàng đợi (404 "Run chưa có queue đã lưu") là trạng thái trống, không phải lỗi', async () => {
      const { authApi } = setupMockEnv({ extra: (url) => (url.pathname.startsWith('/api/queues/')
        ? Response.json({ code: 'NOT_FOUND', message: 'Run chưa có queue đã lưu.' }, { status: 404 }) : undefined) });
      await authApi.signIn('reviewer');
      renderWithProviders(<QualitySummary currentDataset={dataset1} />);
      expect(await screen.findAllByText('Run chưa có hàng đợi review')).toHaveLength(2);
      expect(screen.queryByText('Không tải được.')).toBeNull();
      const processed = screen.getByText('Đã xử lý').parentElement!;
      expect(processed.textContent).toBe('Đã xử lý7');
    });

    it('Dataset chưa có run: trạng thái rỗng thật, không gọi API theo run', async () => {
      const { authApi, calls } = setupMockEnv();
      await authApi.signIn('admin');
      renderWithProviders(<QualitySummary currentDataset={datasetsPage2[0]} />);
      expect(await screen.findByText(/Dataset chưa có Quality Control Run nào/)).toBeDefined();
      expect(screen.getByRole('link', { name: 'Tạo snapshot đầu tiên' }).getAttribute('href')).toBe('/analysis');
      expect(screen.getByText(/Dataset chưa có Task nào được đồng bộ từ CVAT/)).toBeDefined();
      expect(calls.some((c) => /\/api\/runs\/\d+\//.test(c) || c.startsWith('/api/queues/'))).toBe(false);
      expect(document.body.textContent).not.toMatch(FORBIDDEN_SAMPLE_TEXT);
    });

    it('lỗi tải run gần nhất có Thử lại', async () => {
      let runCalls = 0;
      const { authApi } = setupMockEnv({ extra: (url) => (url.pathname === '/api/datasets/summary/' && ++runCalls === 1
        ? Response.json({ detail: 'down' }, { status: 503 }) : undefined) });
      await authApi.signIn('admin');
      renderWithProviders(<QualitySummary currentDataset={dataset1} />);
      expect(await screen.findByText(/Không tải được Quality Control Run/)).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
      expect(await screen.findByText(/Quality Control Run #107/)).toBeDefined();
    });

    it('chưa chọn Dataset: trạng thái rỗng, giữ liên kết thật', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');
      renderWithProviders(<QualitySummary currentDataset={null} />);
      expect(screen.getByText('Chưa có Dataset trong ngữ cảnh làm việc.')).toBeDefined();
      expect(screen.getByRole('link', { name: 'Xem Quality Report' }).getAttribute('href')).toBe('/reports');
      expect(screen.getByRole('link', { name: 'Vào Review Center →' }).getAttribute('href')).toBe('/review');
      expect(document.body.textContent).not.toMatch(FORBIDDEN_SAMPLE_TEXT);
    });

    it('liên kết Quality Gate, Execution History, hàng đợi là Link thật', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');
      renderWithProviders(<QualitySummary currentDataset={dataset1} />);
      expect((await screen.findByRole('link', { name: 'Xem Quality Gate' })).getAttribute('href')).toBe('/reports/gate');
      expect(screen.getByRole('link', { name: 'Xem Execution History' }).getAttribute('href')).toBe('/analysis/history');
      expect(screen.getByRole('link', { name: 'Mở hàng đợi' }).getAttribute('href')).toBe('/review');
    });

    it('chọn task bằng bàn phím đặt phạm vi', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');
      const onScopeChange = vi.fn();
      const { rerender } = renderWithProviders(
        <QualitySummary currentDataset={dataset1} selectedTaskScope={null} onTaskScopeChange={onScopeChange} />,
      );
      await screen.findByText(/12 issue · đã review/);
      const taskRow = screen.getByRole('row', { name: /T-4 · cavat_test/ });
      expect(taskRow.getAttribute('aria-selected')).toBe('false');
      fireEvent.keyDown(taskRow, { key: 'Enter' });
      expect(onScopeChange).toHaveBeenCalledWith('T-4 · cavat_test');
      rerender(<QualitySummary currentDataset={dataset1} selectedTaskScope="T-4 · cavat_test" onTaskScopeChange={onScopeChange} />);
      expect(screen.getByRole('row', { name: /T-4 · cavat_test/ }).getAttribute('aria-selected')).toBe('true');
    });
  });

  describe('Trang / (xác minh Dataset và context bar)', () => {
    it('context bar dùng run và snapshot thật, không dùng id mẫu', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');
      renderWithProviders(<Home />);
      expect(await screen.findByText(/Tình trạng kiểm tra của labelx-dev/)).toBeDefined();
      expect(await screen.findByText('#107 · Completed')).toBeDefined();
      expect(screen.getByText('SNP-003')).toBeDefined();
      expect(document.body.textContent).not.toMatch(/QC-0|SNP-014/);
    });

    it('tìm Dataset ở trang 2 mà không bịa danh tính', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv({ sessionDatasetId: 3, datasets: (req) => (new URL(req.url).searchParams.get('cursor')
        ? Response.json({ next: null, previous: null, results: datasetsPage2 })
        : Response.json({ next: 'http://localhost/api/datasets/?cursor=page2', previous: null, results: datasetsPage1 })) });
      await authApi.signIn('reviewer');
      renderWithProviders(<Home />);
      expect(await screen.findByText(/Tình trạng kiểm tra của Parking Lot Real/)).toBeDefined();
    });

    it('Dataset bị thu hồi: báo không khả dụng và Summary rỗng', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv({ datasets: () => Response.json({ next: null, previous: null, results: [{ id: 100, name: 'Other', cvat_project_id: 99 }] }) });
      await authApi.signIn('reviewer');
      renderWithProviders(<Home />);
      expect(await screen.findByRole('heading', { level: 2, name: 'Dataset không khả dụng' })).toBeDefined();
      expect(screen.getByText('Chưa có Dataset trong ngữ cảnh làm việc.')).toBeDefined();
      expect(document.body.textContent).not.toMatch(FORBIDDEN_SAMPLE_TEXT);
    });

    it('lỗi xác minh Dataset có Thử lại', async () => {
      currentSearchParam = 'view=summary';
      let call = 0;
      const { authApi } = setupMockEnv({ datasets: () => (++call === 1
        ? Response.json({ error: 'Server error' }, { status: 500 })
        : Response.json({ next: null, previous: null, results: datasetsPage1 })) });
      await authApi.signIn('reviewer');
      renderWithProviders(<Home />);
      expect(await screen.findByRole('heading', { level: 2, name: 'Lỗi kiểm tra quyền Dataset' })).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: 'Thử lại' }));
      expect(await screen.findByText(/Tình trạng kiểm tra của labelx-dev/)).toBeDefined();
    });

    it('hiện thông báo đang xác minh khi vào thẳng Summary', async () => {
      currentSearchParam = 'view=summary';
      let resolve: (value: Response) => void;
      const delayed = new Promise<Response>((r) => { resolve = r; });
      const { authApi } = setupMockEnv({ datasets: () => delayed });
      await authApi.signIn('reviewer');
      renderWithProviders(<Home />);
      expect(await screen.findByText(/Đang xác minh thông tin Dataset #1/)).toBeDefined();
      resolve!(Response.json({ next: null, previous: null, results: datasetsPage1 }));
      expect(await screen.findByText(/Tình trạng kiểm tra của labelx-dev/)).toBeDefined();
    });

    it('đổi người dùng trong cây đang mount: bỏ Dataset cũ, về trạng thái rỗng thật', async () => {
      currentSearchParam = 'view=summary';
      const { authApi } = setupMockEnv();
      await authApi.signIn('reviewer');
      function Harness() {
        const { login, user } = useAuth();
        return <div><Home />{user?.username === 'reviewer' && (
          <button type="button" onClick={() => void login({ username: 'admin', password: 'password123' })}>Chuyển sang admin</button>
        )}</div>;
      }
      renderWithProviders(<Harness />);
      expect(await screen.findByText(/Tình trạng kiểm tra của labelx-dev/)).toBeDefined();
      fireEvent.click(screen.getByRole('button', { name: 'Chuyển sang admin' }));
      await waitFor(() => expect(screen.queryByText(/Tình trạng kiểm tra của labelx-dev/)).toBeNull());
      expect(screen.getByText('Chưa có Dataset trong ngữ cảnh làm việc.')).toBeDefined();
    });
  });

  describe('TopBar', () => {
    it('menu Overview dẫn tới Quality Control Home và Quality Summary', async () => {
      const { authApi } = setupMockEnv();
      await authApi.signIn('admin');
      renderWithProviders(<TopBar activeKey="overview" />);
      fireEvent.click(screen.getByRole('button', { name: 'Overview' }));
      expect(screen.getByRole('menuitem', { name: /Quality Control Home/ }).getAttribute('href')).toBe('/');
      expect(screen.getByRole('menuitem', { name: /Quality Summary/ }).getAttribute('href')).toBe('/?view=summary');
    });
  });
});
