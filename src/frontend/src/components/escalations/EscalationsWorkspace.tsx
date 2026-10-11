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
  { value: 'reject', label: 'Bác bỏ', note: 'Issue chuyển sang rejected.' },
  {
    value: 'guideline_gap',
    label: 'Guideline còn thiếu',
    note: 'Issue tiếp tục ở trạng thái escalated để chờ guideline mới.',
  },
];

const FAMILY_LABELS: Record<string, string> = { E1: 'Thiếu box', E2: 'Sai nhãn', E3: 'Trùng box', structural: 'Cảnh báo cấu trúc' };
const DECISION_LABELS: Record<string, string> = {
  confirm: 'Xác nhận lỗi', reject: 'Bác bỏ', uncertain: 'Chưa chắc chắn', escalate: 'Chuyển cấp trên', request_fix: 'Yêu cầu sửa',
  adjudicate_confirm: 'Phân xử: xác nhận lỗi', adjudicate_reject: 'Phân xử: bác bỏ', adjudicate_guideline_gap: 'Phân xử: guideline còn thiếu',
};
const issueCode = (id: number) => `QC-${String(id).padStart(5, '0')}`;
const familyLabel = (family: string) => FAMILY_LABELS[family] ?? family;

function makeRequestKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return `t039-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatValue(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : String(value);
}

/** Hàng 3 cột của thiết kế: Quyết định của reviewer, Bằng chứng, Hướng dẫn liên quan (dữ liệu thật từ issue). */
function EscalationSummary({ issue }: { issue: EscalationIssue }) {
  const ruleIds = [...new Set([...(issue.rule_ids ?? []), ...issue.evidence.flatMap((item) => (item.rule_id ? [item.rule_id] : []))])];
  return (
    <div className="lx-grid lx-grid--3">
      <div className="lx-stack lx-stack--tight"><span className="lx-label">Quyết định của reviewer</span>
        {issue.review_decisions.length === 0 ? <div className="lx-muted lx-text-13">Chưa có quyết định.</div> : (
          <table className="lx-table lx-table--sm"><tbody>
            {issue.review_decisions.map((decision) => (
              <tr key={decision.id}><td>User #{decision.actor_user_id}</td><td><span className="lx-badge">{DECISION_LABELS[decision.decision] ?? decision.decision}</span></td></tr>
            ))}
          </tbody></table>
        )}
      </div>
      <div className="lx-stack lx-stack--tight"><span className="lx-label">Bằng chứng</span>
        {issue.evidence.length === 0 ? <div className="lx-muted lx-text-13">Issue chưa có bằng chứng.</div> : (
          <div className="lx-muted lx-text-13">
            {issue.evidence.map((item, index) => (
              <div key={`${item.engine}:${item.rule_id ?? index}`}>
                {item.engine}: {formatValue(item.prediction_class ?? item.actual)}{item.confidence != null ? ` · ${item.confidence}` : ''}
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="lx-stack lx-stack--tight"><span className="lx-label">Hướng dẫn liên quan</span>
        <div className="lx-muted lx-text-13">
          {ruleIds.length === 0 ? 'Issue chưa gắn quy tắc.' : <>Quy tắc: <span className="lx-mono">{ruleIds.join(', ')}</span></>}
          <br /><Link className="lx-link" href="/configuration/guidelines">Tra cứu Models và Guidelines</Link>
        </div>
      </div>
    </div>
  );
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
                  <th>Confidence / Intersection over Union</th>
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
                      <div className="lx-cell__sub">Intersection over Union: {formatValue(item.iou)}</div>
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
            <span className="lx-hint">{issues.length} case</span>
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
                      <b className="lx-mono">{issueCode(issue.id)}</b>
                      <span className="lx-badge lx-badge--warning">
                        {lastEscalation?.decision === 'uncertain' ? 'Chưa chắc chắn' : 'Chuyển cấp trên'}
                      </span>
                    </div>
                    <div className="lx-cell__main lx-mt-1">{familyLabel(issue.family)} · {issue.severity || 'Chưa xếp mức'}</div>
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
            <span>Hiển thị {issues.length} case · Trang {cursors.length}</span>
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
                  <h2 className="lx-h2"><span className="lx-mono">{issueCode(selected.id)}</span> · {familyLabel(selected.family)}</h2>
                  <Link className="lx-link lx-text-13" href="/review/workspace">Mở trong Review Workspace</Link>
                </div>
                <form className="lx-card__body lx-stack" onSubmit={submitAdjudication}>
                  <EscalationSummary issue={selected} />
                  <div className="lx-hint">Backend kiểm tra role, scope, định danh và separation of duties.</div>
                  {isOwnEscalation && (
                    <div className="lx-callout" role="alert">
                      Người dùng hiện tại đã chuyển cấp issue này và không được tự phân xử.
                    </div>
                  )}
                  <fieldset className="lx-fieldset">
                    <legend className="lx-label">Kết luận phân xử</legend>
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
                      <label className="lx-label" htmlFor="adjudication-rule">Quy tắc áp dụng *</label>
                      {/* TODO(backend): danh sách quy tắc để dùng dropdown như thiết kế; hiện nhập tay kèm gợi ý từ issue */}
                      <input
                        id="adjudication-rule"
                        className="lx-input lx-mono"
                        list="adjudication-rule-options"
                        value={ruleId}
                        onChange={(event) => setRuleId(event.target.value)}
                        required
                      />
                      <datalist id="adjudication-rule-options">
                        {[...new Set([...(selected.rule_ids ?? []), ...selected.evidence.flatMap((item) => (item.rule_id ? [item.rule_id] : []))])].map((id) => <option key={id} value={id} />)}
                      </datalist>
                    </div>
                    <div className="lx-field">
                      <label className="lx-label" htmlFor="adjudication-label">Nhãn đúng</label>
                      <input
                        id="adjudication-label"
                        className="lx-input"
                        value={correctLabel}
                        onChange={(event) => setCorrectLabel(event.target.value)}
                        list="adjudication-label-options"
                        maxLength={64}
                        placeholder="Để trống nếu không đổi nhãn"
                      />
                      <datalist id="adjudication-label-options">
                        {[...new Set(selected.evidence.flatMap((item) => (item.prediction_class ? [item.prediction_class] : [])))].map((label) => <option key={label} value={label} />)}
                      </datalist>
                    </div>
                    <div className="lx-field">
                      <label className="lx-label" htmlFor="adjudication-after">Sau khi phân xử</label>
                      {/* TODO(backend): POST /api/rework/ (tạo yêu cầu sửa cho annotator sau phân xử, BLOCKER-030); trường khoá, không gọi API */}
                      <select id="adjudication-after" className="lx-select" disabled value="rework" onChange={() => undefined}>
                        <option value="rework">Tạo yêu cầu sửa cho annotator</option>
                        <option value="record">Chỉ ghi nhận quyết định</option>
                      </select>
                    </div>
                  </div>
                  <div className="lx-field">
                    <label className="lx-label" htmlFor="adjudication-reason">Lý do phân xử *</label>
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
                      <label className="lx-label" htmlFor="adjudication-override">Lý do ghi đè *</label>
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
                  <NotConnectedNotice detail={gapBlocked ? 'Thao tác "Tạo Guideline Gap" chưa được thực hiện' : 'Trường Sau khi phân xử và nút Tạo Guideline Gap chờ endpoint POST /api/rework/ và POST /api/guideline-gaps/ (BLOCKER-030)'} />
                  <div className="lx-actions lx-actions--end">
                    {/* TODO(backend): POST /api/guideline-gaps/ (BLOCKER-030); nút chặn, không gọi API giả */}
                    <button className="lx-btn" type="button" onClick={() => setGapBlocked(true)}>Tạo Guideline Gap</button>
                    <button
                      className="lx-btn lx-btn--primary"
                      type="submit"
                      disabled={mutation.isPending || isOwnEscalation}
                    >
                      {mutation.isPending ? 'Đang lưu…' : 'Lưu phân xử'}
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
