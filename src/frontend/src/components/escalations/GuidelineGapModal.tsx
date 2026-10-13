'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ApiRequestError } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { useAuth } from '@/lib/auth/auth-context';
import {
  createGuidelineGap,
  getGuidelineRules,
  makeIdempotencyKey,
  type GuidelineGap,
  type GuidelineGapInput,
} from '@/lib/escalations/api';

/** Contract GuidelineGapCreate chỉ có `description`; phần lý do được ghép vào sau nhãn này để không mất dữ liệu. */
export const GAP_REASON_LABEL = 'Lý do / bằng chứng:';

export function gapDescription(content: string, reason: string): string {
  return `${content}\n\n${GAP_REASON_LABEL} ${reason}`;
}

export function splitGapDescription(description: string): { content: string; reason: string | null } {
  const marker = `\n\n${GAP_REASON_LABEL} `;
  const at = description.indexOf(marker);
  if (at < 0) return { content: description, reason: null };
  return { content: description.slice(0, at), reason: description.slice(at + marker.length) };
}

interface Props {
  onClose: () => void;
  onCreated: (gap: GuidelineGap) => void;
  issueId?: number;
  initialRule?: string;
}

export function GuidelineGapModal({ onClose, onCreated, issueId, initialRule = '' }: Props) {
  const { session, datasetId } = useAuth();
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const ruleField = useRef<HTMLSelectElement>(null);
  const contentField = useRef<HTMLTextAreaElement>(null);
  const reasonField = useRef<HTMLTextAreaElement>(null);
  const requestRef = useRef<{ body: string; key: string } | null>(null);
  const [rule, setRule] = useState(initialRule);
  const [content, setContent] = useState('');
  const [reason, setReason] = useState('');
  const [tried, setTried] = useState(false);

  const rulesQuery = useQuery({
    queryKey: ['guideline-rules', session?.user.id, 'latest'],
    queryFn: ({ signal }) => getGuidelineRules(signal),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const rules = rulesQuery.data ?? [];
  const guidelineVersion = rules[0]?.guideline_version;

  const mutation = useMutation({
    mutationFn: ({ body, key }: { body: GuidelineGapInput; key: string }) => createGuidelineGap(body, key),
    retry: false,
    onSuccess: (gap) => {
      requestRef.current = null;
      onCreated(gap);
    },
  });

  useEffect(() => {
    if (!opener.current && document.activeElement instanceof HTMLElement) opener.current = document.activeElement;
    dialog.current?.showModal();
    ruleField.current?.focus();
  }, []);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (mutation.isPending) return;
    setTried(true);
    if (!rule) return ruleField.current?.focus();
    if (!content.trim()) return contentField.current?.focus();
    if (!reason.trim()) return reasonField.current?.focus();
    const body: GuidelineGapInput = {
      rule_id: rule,
      description: gapDescription(content.trim(), reason.trim()),
      ...(issueId ? { issue_id: issueId } : {}),
    };
    // Gửi lại cùng nội dung (ví dụ sau lỗi mạng) dùng lại key để backend trả về gap đã tạo, không tạo trùng.
    const fingerprint = JSON.stringify(body);
    if (!requestRef.current || requestRef.current.body !== fingerprint) {
      requestRef.current = { body: fingerprint, key: makeIdempotencyKey() };
    }
    mutation.mutate({ body, key: requestRef.current.key });
  };

  const mutationCode = mutation.error instanceof ApiRequestError ? mutation.error.detail?.code : undefined;
  const ruleIds = rules.map((item) => item.rule_id);

  return (
    <dialog ref={dialog} className="lx-gap-dialog" aria-labelledby="guideline-gap-title"
      aria-describedby="guideline-gap-description" onClose={() => { onClose(); requestAnimationFrame(() => opener.current?.focus()); }}
      onClick={(event) => { if (event.target === dialog.current) dialog.current?.close(); }}>
      <div className="lx-gap">
        <header className="lx-gap__head">
          <div>
            <h2 id="guideline-gap-title">Tạo Guideline Gap</h2>
            <p id="guideline-gap-description">Ghi nhận phần hướng dẫn còn thiếu để nhóm phụ trách xem xét.</p>
          </div>
          <button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" onClick={() => dialog.current?.close()}>×</button>
        </header>
        <form className="lx-gap__body" noValidate onSubmit={submit}>
          <div className="lx-gap__context"><strong>Ngữ cảnh:</strong>{' '}
            {datasetId !== null ? `Dataset #${datasetId} · ` : ''}Guideline {guidelineVersion ?? (rulesQuery.isPending ? '…' : '—')}<br />
            {issueId && <><strong>Issue liên quan:</strong> QC-{String(issueId).padStart(5, '0')} · Quy tắc {initialRule || '—'}<br /></>}
          </div>
          <div className="lx-gap__fields">
            <div className="lx-field">
              <label className="lx-label" htmlFor="gap-rule">Quy tắc liên quan *</label>
              <select ref={ruleField} id="gap-rule" className="lx-select" value={rule} onChange={(event) => setRule(event.target.value)} aria-invalid={tried && !rule} aria-describedby={tried && !rule ? 'gap-rule-error' : undefined}>
                <option value="">{rulesQuery.isPending ? 'Đang tải quy tắc…' : 'Chọn quy tắc'}</option>
                {initialRule && !ruleIds.includes(initialRule) && <option value={initialRule}>{initialRule}</option>}
                {rules.map((item) => (
                  <option key={item.rule_id} value={item.rule_id}>{item.rule_id} · {item.section}</option>
                ))}
              </select>
              {tried && !rule && <span id="gap-rule-error" className="lx-gap__error">Chọn quy tắc liên quan.</span>}
              {rulesQuery.isError && (
                <span className="lx-gap__error" role="alert">
                  Không tải được danh sách quy tắc. {errorMessage(rulesQuery.error)}{' '}
                  <button type="button" className="lx-btn lx-btn--sm" onClick={() => rulesQuery.refetch()}>Thử lại</button>
                </span>
              )}
            </div>
            <div className="lx-field">
              <label className="lx-label" htmlFor="gap-content">Nội dung hướng dẫn còn thiếu *</label>
              <textarea ref={contentField} id="gap-content" className="lx-textarea" value={content} onChange={(event) => setContent(event.target.value)} aria-invalid={tried && !content.trim()} aria-describedby={tried && !content.trim() ? 'gap-content-error' : undefined} placeholder="Ví dụ: Chưa rõ xe buýt mini chở hàng thuộc nhãn nào." />
              {tried && !content.trim() && <span id="gap-content-error" className="lx-gap__error">Mô tả nội dung còn thiếu.</span>}
            </div>
            <div className="lx-field">
              <label className="lx-label" htmlFor="gap-reason">Lý do / bằng chứng *</label>
              <textarea ref={reasonField} id="gap-reason" className="lx-textarea" value={reason} onChange={(event) => setReason(event.target.value)} aria-invalid={tried && !reason.trim()} aria-describedby={tried && !reason.trim() ? 'gap-reason-error' : undefined} placeholder="Nêu tình huống, quyết định còn mâu thuẫn hoặc Case liên quan." />
              {tried && !reason.trim() && <span id="gap-reason-error" className="lx-gap__error">Nhập lý do hoặc bằng chứng.</span>}
            </div>
          </div>
          {mutation.isError && (
            <div className="lx-gap__notice" role="alert">
              <strong>Không tạo được Guideline Gap{mutationCode ? ` (${mutationCode})` : ''}.</strong>{' '}
              {errorMessage(mutation.error)}
            </div>
          )}
          <div className="lx-gap__actions">
            <button type="button" className="lx-btn" onClick={() => dialog.current?.close()}>Hủy</button>
            <button type="submit" className="lx-btn lx-btn--primary" disabled={mutation.isPending}>
              {mutation.isPending ? 'Đang tạo…' : 'Tạo Guideline Gap'}
            </button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
