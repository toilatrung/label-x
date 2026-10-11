'use client';

import React, { useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { ApiRequestError } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { useAuth } from '@/lib/auth/auth-context';
import { rolesForDataset } from '@/lib/auth/roles';
import {
  adjudicateIssue,
  cursorFrom,
  getEscalations,
  type AdjudicationInput,
  type DecisionCase,
  type EscalationIssue,
} from '@/lib/escalations/api';
import { DecisionCaseLookup } from './DecisionCaseLookup';

type Outcome = AdjudicationInput['outcome'];

const OUTCOMES: { value: Outcome; label: string; note: string }[] = [
  { value: 'confirm', label: 'Xác nhận lỗi', note: 'Issue chuyển sang confirmed.' },
  { value: 'reject', label: 'Bác bỏ lỗi', note: 'Issue chuyển sang rejected.' },
  {
    value: 'guideline_gap',
    label: 'Thiếu guideline',
    note: 'Issue tiếp tục ở trạng thái escalated để chờ guideline mới.',
  },
];

function makeRequestKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `t039-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : String(value);
}

function EscalationDetail({ issue }: { issue: EscalationIssue }) {
  return (
    <div className="lx-stack">
      <section className="lx-card" aria-label={`Bằng chứng issue ${issue.id}`}>
        <header className="lx-card__head">
          <h2 className="lx-h2">Bằng chứng</h2>
          <span className="lx-hint">
            Anchor: <span className="lx-mono">{issue.anchor.kind}</span> · Policy:{' '}
            <span className="lx-mono">{issue.anchor.policy_version}</span>
          </span>
        </header>
        {issue.evidence.length === 0 ? (
          <div className="lx-card__body lx-muted">Issue chưa có evidence.</div>
        ) : (
          <div className="lx-scroll">
            <table className="lx-table" aria-label="Evidence của escalation">
              <thead>
                <tr>
                  <th>Engine / Rule</th>
                  <th>Expected / Actual</th>
                  <th>Prediction</th>
                  <th>Confidence / IoU</th>
                </tr>
              </thead>
              <tbody>
                {issue.evidence.map((item, index) => (
                  <tr key={`${item.engine}:${item.rule_id ?? index}`}>
                    <td>
                      <strong>{item.engine}</strong>
                      <div className="lx-cell__sub lx-mono">{formatValue(item.rule_id)}</div>
                    </td>
                    <td>
                      <div>{formatValue(item.expected)}</div>
                      <div className="lx-cell__sub">Thực tế: {formatValue(item.actual)}</div>
                    </td>
                    <td>
                      <div>{formatValue(item.prediction_class)}</div>
                      <div className="lx-cell__sub lx-mono">
                        {item.prediction_bbox ? JSON.stringify(item.prediction_bbox) : 'Không có bbox'}
                      </div>
                    </td>
                    <td className="lx-num">
                      {formatValue(item.confidence)}
                      <div className="lx-cell__sub">IoU: {formatValue(item.iou)}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="lx-card" aria-label={`Quyết định reviewer của issue ${issue.id}`}>
        <header className="lx-card__head">
          <h2 className="lx-h2">Quyết định từng reviewer</h2>
          <span className="lx-count">{issue.review_decisions.length} quyết định</span>
        </header>
        {issue.review_decisions.length === 0 ? (
          <div className="lx-card__body lx-muted">Chưa có quyết định reviewer.</div>
        ) : (
          <div className="lx-stack lx-card__body">
            {issue.review_decisions.map((decision) => (
              <article className="lx-decision" key={decision.id}>
                <div className="lx-row">
                  <span className="lx-badge lx-badge--info">{decision.decision}</span>
                  <strong>User #{decision.actor_user_id}</strong>
                  <span className="lx-tag">{decision.actor_role}</span>
                  <time className="lx-cell__sub" dateTime={decision.recorded_at}>
                    {new Date(decision.recorded_at).toLocaleString('vi-VN')}
                  </time>
                </div>
                <p>{decision.reason || 'Không ghi lý do.'}</p>
                <div className="lx-hint">
                  Revision <span className="lx-mono">{decision.revision}</span> · Rule{' '}
                  <span className="lx-mono">{decision.rule_ids.join(', ') || '—'}</span> · Reference{' '}
                  <span className="lx-mono">{decision.reference_version || '—'}</span> ({decision.reference_match_status})
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export function EscalationsWorkspace() {
  const { session, user, datasetId } = useAuth();
  const queryClient = useQueryClient();
  const [runDraft, setRunDraft] = useState('');
  const [runId, setRunId] = useState<number | undefined>();
  const [filterError, setFilterError] = useState<string | null>(null);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<Outcome>('confirm');
  const [ruleId, setRuleId] = useState('');
  const [correctLabel, setCorrectLabel] = useState('');
  const [reason, setReason] = useState('');
  const [overrideReason, setOverrideReason] = useState('');
  const [formError, setFormError] = useState<string | null>(null);
  const [savedCase, setSavedCase] = useState<DecisionCase | null>(null);
  const [gapBlocked, setGapBlocked] = useState(false);
  const requestRef = useRef<{ body: string; key: string } | null>(null);
  const cursor = cursors.at(-1) ?? null;

  const activeRoles = rolesForDataset(session, datasetId);
  const requiresOverride = activeRoles.includes('super_admin') && !activeRoles.includes('qa_lead');

  const listQuery = useQuery({
    queryKey: ['escalations', session?.user.id, datasetId, runId ?? null, cursor],
    queryFn: ({ signal }) => getEscalations({ runId, cursor, signal }),
    retry: false,
  });

  const nextCursor = cursorFrom(listQuery.data?.next);
  const issues = useMemo(() => listQuery.data?.results ?? [], [listQuery.data?.results]);
  const selected = useMemo(
    () => issues.find((issue) => issue.id === selectedId) ?? null,
    [issues, selectedId],
  );

  const escalatorId = useMemo(() => {
    if (!selected) return null;
    const escalations = selected.review_decisions.filter(
      (decision) => decision.decision === 'escalate' || decision.decision === 'uncertain',
    );
    return escalations.at(-1)?.actor_user_id ?? null;
  }, [selected]);
  const isOwnEscalation = escalatorId !== null && escalatorId === user?.id;

  const mutation = useMutation({
    mutationFn: ({ issueId, body, key }: { issueId: number; body: AdjudicationInput; key: string }) =>
      adjudicateIssue(issueId, body, key),
    retry: false,
    onSuccess: (decisionCase, variables) => {
      requestRef.current = null;
      setSavedCase(decisionCase);
      setFormError(null);
      void queryClient.invalidateQueries({ queryKey: ['escalations'] });
      void queryClient.invalidateQueries({ queryKey: ['decision-cases'] });
      if (variables.body.outcome !== 'guideline_gap') setSelectedId(null);
    },
  });

  const selectIssue = (issue: EscalationIssue) => {
    setSelectedId(issue.id);
    setOutcome('confirm');
    setRuleId(issue.rule_ids?.[0] ?? issue.evidence.find((item) => item.rule_id)?.rule_id ?? '');
    setCorrectLabel('');
    setReason('');
    setOverrideReason('');
    setFormError(null);
    setSavedCase(null);
    setGapBlocked(false);
    mutation.reset();
    requestRef.current = null;
  };

  const applyRunFilter = (event: React.FormEvent) => {
    event.preventDefault();
    const value = runDraft.trim();
    if (value && !/^[1-9]\d*$/.test(value)) {
      setFilterError('Run ID phải là số nguyên dương.');
      return;
    }
    setFilterError(null);
    setRunId(value ? Number(value) : undefined);
    setCursors([null]);
    setSelectedId(null);
  };

  const submitAdjudication = (event: React.FormEvent) => {
    event.preventDefault();
    if (!selected) return;
    const cleanRule = ruleId.trim();
    const cleanReason = reason.trim();
    const cleanOverride = overrideReason.trim();
    if (!cleanRule || !cleanReason) {
      setFormError('Rule ID và lý do là bắt buộc.');
      return;
    }
    if (requiresOverride && !cleanOverride) {
      setFormError('Super Admin phải nhập lý do dùng quyền ghi đè.');
      return;
    }
    if (isOwnEscalation) {
      setFormError('Người chuyển cấp không được tự phân xử issue này.');
      return;
    }

    const body: AdjudicationInput = {
      outcome,
      rule_id: cleanRule,
      reason: cleanReason,
      ...(correctLabel.trim() ? { correct_label: correctLabel.trim() } : {}),
      ...(cleanOverride ? { override_reason: cleanOverride } : {}),
    };
    const fingerprint = JSON.stringify(body);
    if (!requestRef.current || requestRef.current.body !== fingerprint) {
      requestRef.current = { body: fingerprint, key: makeRequestKey() };
    }
    setFormError(null);
    mutation.mutate({ issueId: selected.id, body, key: requestRef.current.key });
  };

  const mutationCode = mutation.error instanceof ApiRequestError ? mutation.error.detail?.code : undefined;

  return (
    <div className="lx-stack">
      <div className="lx-cols">
        <section className="lx-card lx-side--list" aria-label="Danh sách escalation" aria-busy={listQuery.isFetching}>
          <div className="lx-card__head">
            <h2 className="lx-h2">Chờ phân xử</h2>
            <span className="lx-hint">Trang {cursors.length}</span>
          </div>
          <form className="lx-toolbar" onSubmit={applyRunFilter}>
            <div className="lx-field lx-escalation-run-filter">
              <label className="lx-label" htmlFor="escalation-run">Lọc theo Quality Control Run ID</label>
              <input
                id="escalation-run"
                className="lx-input lx-mono"
                inputMode="numeric"
                value={runDraft}
                onChange={(event) => setRunDraft(event.target.value)}
                placeholder="Tất cả run trong scope"
              />
            </div>
            <button className="lx-btn lx-btn--primary" type="submit">Áp dụng</button>
            {runId && (
              <button
                className="lx-btn"
                type="button"
                onClick={() => {
                  setRunDraft('');
                  setRunId(undefined);
                  setCursors([null]);
                  setSelectedId(null);
                }}
              >
                Xoá bộ lọc
              </button>
            )}
            {filterError && <span className="lx-hint is-bad" role="alert">{filterError}</span>}
          </form>

          {listQuery.isPending ? (
            <div className="lx-card__body lx-muted" role="status">Đang tải danh sách escalation…</div>
          ) : listQuery.isError ? (
            <div className="lx-card__body">
              <div className="lx-callout" role="alert">
                <div className="lx-callout__text">
                  <strong>Không tải được danh sách escalation.</strong>
                  <div>{errorMessage(listQuery.error)}</div>
                </div>
                <button className="lx-btn lx-btn--sm" type="button" onClick={() => listQuery.refetch()}>
                  Thử lại
                </button>
              </div>
            </div>
          ) : issues.length === 0 ? (
            <div className="lx-card__body lx-review-empty">
              {runId ? `Không có escalation trong Run #${runId}.` : 'Không có issue nào đang chờ phân xử.'}
            </div>
          ) : (
            <ul className="lx-list" aria-label="Issue đang chờ phân xử">
              {issues.map((issue) => {
                const lastEscalation = issue.review_decisions
                  .filter((decision) => decision.decision === 'escalate' || decision.decision === 'uncertain')
                  .at(-1);
                return (
                  <li key={issue.id} aria-current={selected?.id === issue.id ? 'true' : undefined}>
                    <div className="lx-row lx-row--between">
                      <b className="lx-mono">#{issue.id}</b>
                      <span className="lx-badge lx-badge--warning">
                        {lastEscalation?.decision === 'uncertain' ? 'Chưa chắc chắn' : 'Chuyển cấp trên'}
                      </span>
                    </div>
                    <div className="lx-cell__main lx-mt-1">{issue.family} · {issue.severity || 'Chưa xếp mức'}</div>
                    <div className="lx-cell__sub">
                      {issue.origin} · {issue.state} · Rule {issue.rule_ids?.join(', ') || '—'} · {issue.evidence.length} bằng chứng · {issue.review_decisions.length} quyết định
                    </div>
                    <button className="lx-btn lx-btn--sm lx-mt-1" type="button" onClick={() => selectIssue(issue)}>
                      {selected?.id === issue.id ? 'Đang mở' : 'Mở phân xử'}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <footer className="lx-card__foot">
            <span>{issues.length} issue trên trang hiện tại.</span>
            <nav className="lx-pager" aria-label="Phân trang escalation">
              <button
                className="lx-btn lx-btn--sm"
                type="button"
                disabled={cursors.length === 1 || listQuery.isFetching}
                onClick={() => {
                  setCursors((current) => current.slice(0, -1));
                  setSelectedId(null);
                }}
              >
                Trang trước
              </button>
              <button
                className="lx-btn lx-btn--sm"
                type="button"
                disabled={!nextCursor || listQuery.isFetching}
                onClick={() => {
                  if (nextCursor) setCursors((current) => [...current, nextCursor]);
                  setSelectedId(null);
                }}
              >
                Trang sau
              </button>
            </nav>
          </footer>
        </section>

        <div className="lx-main lx-stack">
          {savedCase && (
            <div className="lx-callout lx-callout--info" role="status">
              <div className="lx-callout__text">
                <strong>Đã lưu Decision Case #{savedCase.id}</strong> · Issue #{savedCase.issue_id} ·{' '}
                <span className="lx-mono">{savedCase.case_version}</span>
              </div>
            </div>
          )}

          {!selected && (
            <section className="lx-card" aria-label="Chi tiết phân xử">
              <div className="lx-card__body lx-muted">Chọn một issue ở danh sách bên trái để xem bằng chứng và phân xử.</div>
            </section>
          )}

          {selected && (
            <>
              <section className="lx-card" aria-label={`Form phân xử issue ${selected.id}`}>
                <div className="lx-card__head">
                  <h2 className="lx-h2"><span className="lx-mono">#{selected.id}</span> · Phân xử Issue #{selected.id}</h2>
                  <Link className="lx-link lx-text-13" href="/review/workspace">Mở trong Review Workspace</Link>
                </div>
                <form className="lx-card__body lx-stack" onSubmit={submitAdjudication}>
                  <div className="lx-hint">Backend kiểm tra role, scope, định danh và separation of duties.</div>
                  {isOwnEscalation && (
                    <div className="lx-callout" role="alert">
                      Người dùng hiện tại đã chuyển cấp issue này và không được tự phân xử.
                    </div>
                  )}
                  <fieldset className="lx-fieldset">
                    <legend className="lx-label">Kết luận</legend>
                    <div className="lx-choices">
                      {OUTCOMES.map((option) => (
                        <label className="lx-choice" key={option.value} title={option.note}>
                          <input
                            type="radio"
                            name="outcome"
                            value={option.value}
                            checked={outcome === option.value}
                            onChange={() => setOutcome(option.value)}
                          />
                          <span>{option.label}</span>
                        </label>
                      ))}
                    </div>
                    <div className="lx-hint">{OUTCOMES.find((option) => option.value === outcome)?.note}</div>
                  </fieldset>
                  <div className="lx-grid lx-grid--3">
                    <div className="lx-field">
                      <label className="lx-label" htmlFor="adjudication-rule">Rule ID *</label>
                      <input
                        id="adjudication-rule"
                        className="lx-input lx-mono"
                        value={ruleId}
                        onChange={(event) => setRuleId(event.target.value)}
                        required
                      />
                    </div>
                    <div className="lx-field">
                      <label className="lx-label" htmlFor="adjudication-label">Nhãn đúng</label>
                      <input
                        id="adjudication-label"
                        className="lx-input"
                        value={correctLabel}
                        onChange={(event) => setCorrectLabel(event.target.value)}
                        maxLength={64}
                        placeholder="Để trống nếu không đổi nhãn"
                      />
                    </div>
                  </div>
                  <div className="lx-field">
                    <label className="lx-label" htmlFor="adjudication-reason">Lý do *</label>
                    <textarea
                      id="adjudication-reason"
                      className="lx-textarea"
                      value={reason}
                      onChange={(event) => setReason(event.target.value)}
                      placeholder="Nêu căn cứ để các case tương tự có thể tham chiếu."
                      required
                    />
                  </div>
                  {requiresOverride && (
                    <div className="lx-field">
                      <label className="lx-label" htmlFor="adjudication-override">Lý do override *</label>
                      <textarea
                        id="adjudication-override"
                        className="lx-textarea"
                        value={overrideReason}
                        onChange={(event) => setOverrideReason(event.target.value)}
                        required
                      />
                    </div>
                  )}
                  {formError && <div className="lx-callout" role="alert">{formError}</div>}
                  {mutation.isError && (
                    <div className="lx-callout" role="alert">
                      <div className="lx-callout__text">
                        <strong>Không thể lưu phân xử{mutationCode ? ` (${mutationCode})` : ''}.</strong>
                        <div>{errorMessage(mutation.error)}</div>
                      </div>
                    </div>
                  )}
                  {gapBlocked && <NotConnectedNotice detail="Tạo Guideline Gap chờ endpoint POST /api/guideline-gaps/ (BLOCKER-030)" />}
                  <div className="lx-actions lx-actions--end">
                    {/* TODO(backend): POST /api/guideline-gaps/ (BLOCKER-030); nút chặn, không gọi API giả */}
                    <button className="lx-btn" type="button" onClick={() => setGapBlocked(true)}>Tạo Guideline Gap</button>
                    <button
                      className="lx-btn lx-btn--primary"
                      type="submit"
                      disabled={mutation.isPending || isOwnEscalation}
                    >
                      {mutation.isPending ? 'Đang lưu…' : 'Lưu kết luận phân xử'}
                    </button>
                  </div>
                </form>
              </section>
              <EscalationDetail issue={selected} />
            </>
          )}
        </div>
      </div>

      <DecisionCaseLookup initialIssueId={selected?.id ?? savedCase?.issue_id} />
    </div>
  );
}
