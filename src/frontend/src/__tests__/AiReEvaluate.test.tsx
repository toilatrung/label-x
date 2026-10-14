import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AiReEvaluate, POLL_INTERVAL_MS, POLL_TIMEOUT_MS } from '@/components/review/AiReEvaluate';
import { ReviewEvidenceTable } from '@/components/review/ReviewEvidenceTable';
import type { AiEvidence } from '@/lib/review/workspace-api';

const evaluation = (status: string, extra: Record<string, unknown> = {}) => ({
  id: 3001, candidate_id: 501, run_id: 91, generation: 2, source: 'manual', status, reason_code: null, reasons: ['manual_recheck'],
  review_required: true, call_qwen: true, policy: {}, checkpoint_status: null, snapshot_revision: 'rev-1', requested_by_user_id: 7,
  note: 'x', vlm: null, created_at: '2026-10-14T08:30:00Z', poll_url: '/api/candidate-evaluations/3001/', ...extra,
});

const wrap = (node: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{node}</QueryClientProvider>);

type Route = (request: Request, url: URL) => Response | Promise<Response>;
let post: Route;
let poll: Route;
let requests: Request[];

beforeEach(() => {
  requests = [];
  // jsdom chưa có showModal/close của <dialog>.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) { this.open = true; };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) { this.open = false; this.dispatchEvent(new Event('close')); };
  post = () => Response.json(evaluation('pending'), { status: 202 });
  poll = () => Response.json(evaluation('running'));
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    const url = new URL(request.url);
    requests.push(request.clone());
    if (url.pathname === '/api/auth/csrf/') return new Response(null, { status: 204 });
    if (url.pathname === '/api/candidates/501/evaluations/') return post(request, url);
    if (url.pathname === '/api/candidate-evaluations/3001/') return poll(request, url);
    throw new Error(`unexpected ${url.pathname}`);
  }));
});
afterEach(() => vi.useRealTimers());

async function submit(reason = 'Nhãn xe tải có vẻ sai') {
  fireEvent.click(screen.getByRole('button', { name: 'Đánh giá lại bằng AI' }));
  const dialog = await screen.findByRole('dialog', { name: 'Đánh giá lại bằng AI' });
  fireEvent.change(within(dialog).getByLabelText('Lý do đánh giá lại *'), { target: { value: reason } });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Gửi đánh giá lại' }));
  return dialog;
}

describe('Đánh giá lại candidate bằng AI (A-4, A-5)', () => {
  it('sends reason, expected_revision and an Idempotency-Key, then polls until completed', async () => {
    let polls = 0;
    poll = () => Response.json(++polls < 2 ? evaluation('running')
      : evaluation('completed', { vlm: { state: 'checked', engine_status: 'checked', source: 'qwen', attempts: 1, class_name: 'truck', conclusion: 'confirmed', rationale: 'Thùng hàng rời.' } }));
    wrap(<AiReEvaluate candidateId={501} expectedRevision="rev-1" />);
    await submit();
    const panel = await screen.findByLabelText('Kết quả đánh giá lại');
    const sent = requests.find(r => new URL(r.url).pathname === '/api/candidates/501/evaluations/')!;
    expect(sent.method).toBe('POST');
    expect(sent.headers.get('Idempotency-Key')).toMatch(/^[0-9a-f-]{36}$/);
    expect(await sent.json()).toEqual({ reason: 'Nhãn xe tải có vẻ sai', expected_revision: 'rev-1' });
    expect(await within(panel).findByText('truck', {}, { timeout: POLL_INTERVAL_MS + 2000 })).toBeDefined();
    expect(within(panel).getByText('Hoàn tất')).toBeDefined();
    expect(within(panel).getByText('Cần người review')).toBeDefined();
    expect(within(panel).getByText('Thùng hàng rời.')).toBeDefined();
    const count = polls;
    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL_MS + 200));
    expect(polls).toBe(count);
  }, 15_000);

  it('reuses the same key when the same reason is resent after a network error', async () => {
    let attempt = 0;
    post = () => { if (++attempt === 1) throw new TypeError('network'); return Response.json(evaluation('pending'), { status: 202 }); };
    wrap(<AiReEvaluate candidateId={501} expectedRevision="rev-1" />);
    const dialog = await submit();
    expect(await within(dialog).findByText(/Không kết nối được máy chủ/)).toBeDefined();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Gửi đánh giá lại' }));
    await screen.findByLabelText('Kết quả đánh giá lại');
    const keys = requests.filter(r => new URL(r.url).pathname === '/api/candidates/501/evaluations/').map(r => r.headers.get('Idempotency-Key'));
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it.each([
    [409, { code: 'BUSINESS_RULE_UNMET', message: 'stale', details: { reason_code: 'stale_revision' } }, /revision mới hơn revision đang mở/],
    [409, { code: 'IDEMPOTENCY_KEY_REUSED', message: 'reused' }, /Mã yêu cầu đã được dùng với nội dung khác/],
    [422, { code: 'BUSINESS_RULE_UNMET', message: 'Run không bật VLM hoặc thiếu cấu hình/taxonomy; không thể đánh giá lại.' }, /Run không bật VLM/],
  ])('explains a %i answer inside the dialog', async (status, body, text) => {
    post = () => Response.json(body, { status });
    wrap(<AiReEvaluate candidateId={501} expectedRevision="rev-1" />);
    const dialog = await submit();
    expect(await within(dialog).findByText(text)).toBeDefined();
    expect(screen.queryByLabelText('Kết quả đánh giá lại')).toBeNull();
  });

  it('requires a reason before sending', async () => {
    wrap(<AiReEvaluate candidateId={501} expectedRevision="rev-1" />);
    const dialog = await submit('   ');
    expect(within(dialog).getByText('Nhập lý do đánh giá lại.')).toBeDefined();
    expect(requests).toHaveLength(0);
  });

  it('stops polling after 5 minutes, says there is no result yet and lets the user check again', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let polls = 0;
    poll = () => { polls++; return Response.json(evaluation('running')); };
    wrap(<AiReEvaluate candidateId={501} expectedRevision="rev-1" />);
    await submit();
    await screen.findByLabelText('Kết quả đánh giá lại');
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_TIMEOUT_MS + POLL_INTERVAL_MS); });
    const panel = screen.getByLabelText('Kết quả đánh giá lại');
    expect(within(panel).getByText('Chưa có kết quả')).toBeDefined();
    const stopped = polls;
    await act(async () => { await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3); });
    expect(polls).toBe(stopped);
    poll = () => { polls++; return Response.json(evaluation('failed')); };
    fireEvent.click(within(panel).getByRole('button', { name: 'Kiểm tra lại' }));
    expect(await within(panel).findByText('Failed')).toBeDefined();
    expect(polls).toBe(stopped + 1);
  });
});

describe('ReviewEvidenceTable', () => {
  const ai: AiEvidence = { issue_id: 1, candidate_id: 501, evaluation_id: 3000, generation: 1, evaluation_source: 'auto', status: 'failed',
    source: 'qwen', reason_code: 'provider_error', reasons: [], review_required: true, suggestion: null, evidence_refs: null,
    snapshot_revision: 'rev-1', poll_url: '/api/candidate-evaluations/3000/' };

  it('shows the re-evaluate button only to roles allowed by the API', () => {
    const { rerender } = wrap(<ReviewEvidenceTable evidenceList={[]} aiEvidence={[ai]} />);
    expect(screen.queryByRole('button', { name: 'Đánh giá lại bằng AI' })).toBeNull();
    rerender(<QueryClientProvider client={new QueryClient()}><ReviewEvidenceTable evidenceList={[]} aiEvidence={[ai]} canReEvaluate /></QueryClientProvider>);
    expect(screen.getByRole('button', { name: 'Đánh giá lại bằng AI' })).toBeDefined();
  });

  it('sends the run revision from the workspace AI evidence as expected_revision', async () => {
    wrap(<ReviewEvidenceTable evidenceList={[]} aiEvidence={[ai]} canReEvaluate />);
    await submit();
    await waitFor(() => expect(requests.some(r => new URL(r.url).pathname === '/api/candidates/501/evaluations/')).toBe(true));
    const sent = requests.find(r => new URL(r.url).pathname === '/api/candidates/501/evaluations/')!;
    expect((await sent.json()).expected_revision).toBe('rev-1');
  });
});
