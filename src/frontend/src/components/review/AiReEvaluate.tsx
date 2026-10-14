'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { errorMessage } from '@/lib/api/errors';
import {
  MAX_EVALUATION_REASON,
  TERMINAL_EVALUATION_STATUSES,
  evaluateCandidate,
  evaluationErrorMessage,
  getCandidateEvaluation,
  type CandidateEvaluation,
} from '@/lib/review/evaluation-api';

/** Hỏi lại kết quả mỗi 3 giây, dừng sau 5 phút (BLOCKER-034, C6). */
export const POLL_INTERVAL_MS = 3_000;
export const POLL_TIMEOUT_MS = 5 * 60_000;

const STATUS: Record<string, { label: string; tone: string }> = {
  pending: { label: 'Đang chờ', tone: '' },
  running: { label: 'Đang chạy', tone: 'lx-badge--info' },
  completed: { label: 'Hoàn tất', tone: 'lx-badge--success' },
  failed: { label: 'Failed', tone: 'lx-badge--danger' },
  cancelled: { label: 'Đã huỷ', tone: 'lx-badge--warning' },
};
const CONCLUSION: Record<string, string> = { confirmed: 'xác nhận', uncertain: 'chưa chắc chắn' };

interface Props {
  candidateId: number;
  /** Revision Snapshot của run, gửi làm expected_revision để backend chặn revision cũ (409). */
  expectedRevision: string;
}

interface AiReEvaluateProps extends Props {
  /** Lần đánh giá mới nhất từ Candidate.latest_evaluation (B-4): hiện trạng thái ngay khi tải lại trang. */
  latestEvaluationId?: number | null;
}

/** Nút "Đánh giá lại bằng AI" (POST /api/candidates/{id}/evaluations/) và theo dõi kết quả (GET /api/candidate-evaluations/{id}/). */
export function AiReEvaluate({ candidateId, expectedRevision, latestEvaluationId = null }: AiReEvaluateProps) {
  const [open, setOpen] = React.useState(false);
  const [accepted, setAccepted] = React.useState<CandidateEvaluation | null>(null);
  const [pollStart, setPollStart] = React.useState(0);
  const [timedOut, setTimedOut] = React.useState(false);

  const trackedId = accepted?.id ?? latestEvaluationId;
  const evaluation = useQuery({
    queryKey: ['candidate-evaluation', trackedId, pollStart],
    enabled: trackedId !== null && !timedOut,
    queryFn: ({ signal }) => getCandidateEvaluation(trackedId!, signal),
    initialData: pollStart === 0 ? accepted ?? undefined : undefined,
    initialDataUpdatedAt: 0,
    refetchInterval: query => TERMINAL_EVALUATION_STATUSES.includes(query.state.data?.status ?? '') ? false : POLL_INTERVAL_MS,
    retry: false,
  });
  const current = evaluation.data ?? accepted;
  const finished = TERMINAL_EVALUATION_STATUSES.includes(current?.status ?? '');

  React.useEffect(() => {
    if (trackedId === null || finished || timedOut) return;
    const timer = window.setTimeout(() => setTimedOut(true), POLL_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, [trackedId, finished, timedOut, pollStart]);

  const checkAgain = () => { setTimedOut(false); setPollStart(Date.now()); };
  const status = current ? STATUS[current.status] : undefined;

  return <div className="lx-stack lx-gap-1">
    <div><button type="button" className="lx-btn lx-btn--sm" onClick={() => setOpen(true)}
      disabled={!!current && !finished && !timedOut}>Đánh giá lại bằng AI</button></div>
    {current && <div className="lx-stack lx-gap-1" aria-live="polite" aria-label="Kết quả đánh giá lại">
      {timedOut && !finished ? <div className="lx-row lx-gap-2 lx-items-center">
        <span className="lx-subtle">Chưa có kết quả</span>
        <button type="button" className="lx-btn lx-btn--sm" onClick={checkAgain}>Kiểm tra lại</button>
      </div> : <div className="lx-row lx-gap-2 lx-items-center">
        <span className="lx-subtle">Lần đánh giá #{current.generation}</span>
        {status && <span className={`lx-badge ${status.tone}`.trim()}>{status.label}</span>}
        {current.status === 'completed' && current.vlm?.class_name && <span>đề xuất <b>{current.vlm.class_name}</b>
          {current.vlm.conclusion ? ` · ${CONCLUSION[current.vlm.conclusion] ?? current.vlm.conclusion}` : ''}</span>}
        {current.status === 'completed' && !current.vlm && <span className="lx-subtle">không cần mô hình thị giác – ngôn ngữ</span>}
        {finished && current.review_required && <span className="lx-badge lx-badge--warning">Cần người review</span>}
      </div>}
      {evaluation.isError && <span className="lx-subtle lx-text-11" role="alert">{errorMessage(evaluation.error)}</span>}
      {finished && current.vlm?.rationale && <div className="lx-subtle lx-text-11">{current.vlm.rationale}</div>}
      {finished && current.reasons.length > 0 && <div className="lx-subtle lx-text-11">Lý do định tuyến: <span className="lx-mono">{current.reasons.join(', ')}</span></div>}
    </div>}
    {open && <AiReEvaluateModal candidateId={candidateId} expectedRevision={expectedRevision}
      onClose={() => setOpen(false)} onAccepted={result => { setAccepted(result); setTimedOut(false); setPollStart(0); }} />}
  </div>;
}

function AiReEvaluateModal({ candidateId, expectedRevision, onClose, onAccepted }: Props & {
  onClose: () => void;
  onAccepted: (evaluation: CandidateEvaluation) => void;
}) {
  const dialog = React.useRef<HTMLDialogElement>(null);
  const opener = React.useRef<HTMLElement | null>(null);
  const field = React.useRef<HTMLTextAreaElement>(null);
  const [reason, setReason] = React.useState('');
  const [pending, setPending] = React.useState<{ reason: string; key: string } | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [tried, setTried] = React.useState(false);

  React.useEffect(() => {
    if (!opener.current && document.activeElement instanceof HTMLElement) opener.current = document.activeElement;
    dialog.current?.showModal();
    field.current?.focus();
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setTried(true);
    const text = reason.trim();
    if (!text) return field.current?.focus();
    // Gửi lại cùng lý do (ví dụ sau lỗi mạng) dùng lại key: backend trả evaluation đã tạo, không tạo lượt mới.
    const request = pending?.reason === text ? pending : { reason: text, key: crypto.randomUUID() };
    setPending(request);
    setBusy(true); setError(null);
    try {
      onAccepted(await evaluateCandidate(candidateId, { reason: request.reason, expected_revision: expectedRevision }, request.key));
      dialog.current?.close();
    } catch (err) {
      setError(evaluationErrorMessage(err, errorMessage(err)));
    } finally { setBusy(false); }
  }

  const invalid = tried && !reason.trim();
  return (
    <dialog ref={dialog} className="lx-gap-dialog" aria-labelledby="ai-reevaluate-title" aria-describedby="ai-reevaluate-description"
      onClose={() => { onClose(); requestAnimationFrame(() => opener.current?.focus()); }}
      onClick={event => { if (event.target === dialog.current && !busy) dialog.current?.close(); }}>
      <div className="lx-gap">
        <header className="lx-gap__head">
          <div>
            <h2 id="ai-reevaluate-title">Đánh giá lại bằng AI</h2>
            <p id="ai-reevaluate-description">Tạo một lượt đánh giá mới cho candidate này. Kết quả chỉ là đề xuất của AI, không thay quyết định của người review. Lượt đánh giá cũ được giữ nguyên.</p>
          </div>
          <button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" disabled={busy} onClick={() => dialog.current?.close()}>×</button>
        </header>
        <form className="lx-gap__body" noValidate onSubmit={submit}>
          <div className="lx-gap__fields">
            <div className="lx-field">
              <label className="lx-label" htmlFor="ai-reevaluate-reason">Lý do đánh giá lại *</label>
              <textarea ref={field} className="lx-textarea" id="ai-reevaluate-reason" rows={3} maxLength={MAX_EVALUATION_REASON} value={reason}
                onChange={event => setReason(event.target.value)} aria-invalid={invalid}
                aria-describedby={invalid ? 'ai-reevaluate-reason-error' : 'ai-reevaluate-reason-hint'} />
              {invalid ? <span id="ai-reevaluate-reason-error" className="lx-gap__error">Nhập lý do đánh giá lại.</span>
                : <span id="ai-reevaluate-reason-hint" className="lx-hint">Chỉ ghi vào nhật ký kiểm toán, không gửi vào prompt. Tối đa {MAX_EVALUATION_REASON} ký tự.</span>}
            </div>
          </div>
          {error && <div className="lx-gap__notice" role="alert"><strong>Không gửi được yêu cầu đánh giá lại.</strong> {error}</div>}
          <div className="lx-gap__actions">
            <button type="button" className="lx-btn" disabled={busy} onClick={() => dialog.current?.close()}>Hủy</button>
            <button type="submit" className="lx-btn lx-btn--primary" disabled={busy}>{busy ? 'Đang gửi…' : 'Gửi đánh giá lại'}</button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
