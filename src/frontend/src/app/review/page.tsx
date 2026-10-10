'use client';

import React, { Suspense, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { AppShell } from '@/components/layout/AppShell';
import { AuthGuard } from '@/components/auth/AuthGuard';
import { canAccessReview } from '@/lib/auth/roles';
import { errorMessage } from '@/lib/api/errors';
import {
  getRankedFrames,
  reviewImageUrl,
  type DemoCandidate,
  type DemoFrame,
} from '@/lib/review/api';

const DEFAULT_DEMO_RUN_ID = 1;

const severityLabels: Record<string, string> = {
  high: 'Cao',
  medium: 'Trung bình',
  low: 'Thấp',
};

const engineStatusLabels = {
  checked: 'Đã kiểm tra',
  failed: 'Thất bại',
  not_checked: 'Chưa kiểm tra',
} as const;

function validRunId(value: string | null): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : DEFAULT_DEMO_RUN_ID;
}

function candidateForShape(candidates: DemoCandidate[], shapeId: string): DemoCandidate | undefined {
  return candidates.find((candidate) => candidate.shape_ids.includes(shapeId));
}

function FrameCanvas({ frame }: { frame: DemoFrame }) {
  return (
    <svg
      className="lx-review-canvas"
      viewBox={`0 0 ${frame.width} ${frame.height}`}
      role="img"
      aria-label={`Ảnh ${frame.file_name} với ${frame.shapes.length} box annotation`}
    >
      <rect width={frame.width} height={frame.height} fill="#252a31" />
      <image
        href={reviewImageUrl(frame.image_url)}
        width={frame.width}
        height={frame.height}
        preserveAspectRatio="xMidYMid meet"
      />
      {frame.shapes.map((shape) => {
        const [x1, y1, x2, y2] = shape.bbox;
        const candidate = candidateForShape(frame.candidates, shape.id);
        const candidateClass = candidate ? ` is-candidate is-${candidate.severity}` : '';
        return (
          <g
            key={shape.id}
            className={`lx-review-shape${candidateClass}`}
            role="group"
            aria-label={`${candidate ? 'Candidate' : 'Annotation'} ${shape.label} ${shape.id}`}
          >
            <rect x={x1} y={y1} width={Math.max(0, x2 - x1)} height={Math.max(0, y2 - y1)} />
            <text x={Math.max(0, x1)} y={Math.max(16, y1 - 7)}>
              {shape.label} #{shape.id}{candidate ? ` · ${candidate.rule_id}` : ''}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function ReviewWorkspace() {
  const searchParams = useSearchParams();
  const initialRunId = validRunId(searchParams.get('run'));
  const [runInput, setRunInput] = useState(String(initialRunId));
  const [runId, setRunId] = useState(initialRunId);
  const [selectedFrameId, setSelectedFrameId] = useState<number | null>(null);
  const frames = useQuery({
    queryKey: ['demo-review-frames', runId],
    queryFn: ({ signal }) => getRankedFrames(runId, signal),
    retry: false,
  });
  const selectedFrame = useMemo(() => {
    if (!frames.data?.items.length) return null;
    return frames.data.items.find((frame) => frame.frame_id === selectedFrameId) ?? frames.data.items[0];
  }, [frames.data, selectedFrameId]);

  function loadRun(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextRunId = validRunId(runInput);
    setRunInput(String(nextRunId));
    setSelectedFrameId(null);
    setRunId(nextRunId);
  }

  const selectedIndex = selectedFrame
    ? frames.data?.items.findIndex((frame) => frame.frame_id === selectedFrame.frame_id) ?? -1
    : -1;

  return (
    <AppShell
      activeKey="review"
      flowStep={2}
      pageHeader={(
        <div className="lx-head">
          <div className="lx-head__text">
            <h1 className="lx-h1">Review Workspace</h1>
            <p className="lx-lead">
              Frame được xếp theo rủi ro. Box nổi bật là annotation được candidate QC tham chiếu.
            </p>
          </div>
          <form className="lx-review-run" onSubmit={loadRun} aria-label="Chọn QC run">
            <label className="lx-label" htmlFor="review-run-id">QC run</label>
            <input
              id="review-run-id"
              className="lx-input lx-num"
              inputMode="numeric"
              min="1"
              type="number"
              value={runInput}
              onChange={(event) => setRunInput(event.target.value)}
            />
            <button className="lx-btn" type="submit">Tải run</button>
          </form>
        </div>
      )}
    >
      {frames.isLoading && <div className="lx-card lx-card__body">Đang tải danh sách frame…</div>}
      {frames.isError && (
        <div className="lx-callout" role="alert">
          <span className="lx-callout__text">{errorMessage(frames.error)}</span>
          <button className="lx-btn lx-btn--sm" type="button" onClick={() => frames.refetch()}>Thử lại</button>
        </div>
      )}
      {frames.data && frames.data.items.length === 0 && (
        <div className="lx-card lx-card__body">QC-{runId} chưa có frame để kiểm tra.</div>
      )}
      {frames.data && selectedFrame && (
        <>
          <section className="lx-card" aria-label="Danh sách frame theo hạng">
            <header className="lx-card__head">
              <div>
                <h2 className="lx-h2">Frame theo hạng</h2>
                <span className="lx-hint">
                  QC-{frames.data.run_id} · SNP-{frames.data.snapshot_id} · {frames.data.score_version}
                </span>
              </div>
              <div className="lx-review-engines" aria-label="Trạng thái engine">
                {frames.data.engines.map((engine) => (
                  <span
                    key={engine.engine}
                    className={`lx-badge lx-engine-status--${engine.status}`}
                    title={engineStatusLabels[engine.status]}
                  >
                    {engine.engine}: {engineStatusLabels[engine.status]}
                  </span>
                ))}
              </div>
            </header>
            <div className="lx-scroll">
              <table className="lx-table lx-review-table">
                <thead>
                  <tr><th>Hạng</th><th>Frame</th><th>Task · Job</th><th className="r">Điểm</th><th className="r">Candidate</th><th /></tr>
                </thead>
                <tbody>
                  {frames.data.items.map((frame) => (
                    <tr key={frame.frame_id} aria-selected={frame.frame_id === selectedFrame.frame_id}>
                      <td className="lx-cell__main lx-num">#{frame.rank}</td>
                      <td><div className="lx-cell__main">{frame.file_name}</div><div className="lx-cell__sub">Frame {frame.cvat.frame}</div></td>
                      <td className="lx-muted">T-{frame.cvat.task_id} · J-{frame.cvat.job_id}</td>
                      <td className="r lx-num">{frame.score.toFixed(2)}</td>
                      <td className="r"><span className={`lx-badge ${frame.candidates.length ? 'lx-badge--warning' : 'lx-badge--success'}`}>{frame.candidates.length}</span></td>
                      <td className="r"><button className="lx-btn lx-btn--sm" type="button" onClick={() => setSelectedFrameId(frame.frame_id)}>Xem frame {frame.file_name}</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {frames.data.next && <footer className="lx-card__foot">Demo hiển thị tối đa 100 frame đầu tiên của run.</footer>}
          </section>

          <div className="lx-ws lx-ws--reference lx-review-workspace">
            <section className="lx-stage" aria-label="Khung ảnh và annotation">
              <div className="lx-stage__bar">
                <span>Hạng <b className="lx-num">#{selectedFrame.rank}</b></span>
                <span>Frame <b className="lx-num">{selectedFrame.cvat.frame}</b></span>
                <span className="lx-review-stage-spacer" />
                <a className="lx-ghostbtn" href={selectedFrame.cvat.deep_link} target="_blank" rel="noreferrer">
                  Mở trong CVAT
                </a>
              </div>
              <div className="lx-stage__view"><FrameCanvas frame={selectedFrame} /></div>
              <div className="lx-stage__bar lx-review-stage-footer">
                <button
                  className="lx-ghostbtn"
                  type="button"
                  disabled={selectedIndex <= 0}
                  onClick={() => setSelectedFrameId(frames.data.items[selectedIndex - 1].frame_id)}
                >
                  ‹ Frame trước
                </button>
                <button
                  className="lx-ghostbtn"
                  type="button"
                  disabled={selectedIndex >= frames.data.items.length - 1}
                  onClick={() => setSelectedFrameId(frames.data.items[selectedIndex + 1].frame_id)}
                >
                  Frame sau ›
                </button>
                <span className="lx-review-stage-spacer" />
                <span>Đường sáng: candidate · Đường xám: annotation khác</span>
              </div>
            </section>

            <aside className="lx-ws__panel" aria-label="Chi tiết candidate">
              <div className="lx-ws__sec">
                <div className="lx-row lx-review-panel-heading">
                  <span><b className="lx-mono">{selectedFrame.file_name}</b> · {selectedFrame.width}×{selectedFrame.height}</span>
                  <span className="lx-badge lx-badge--info">Điểm {selectedFrame.score.toFixed(2)}</span>
                </div>
                <dl className="lx-kv">
                  <dt>Task · Job</dt><dd>T-{selectedFrame.cvat.task_id} · J-{selectedFrame.cvat.job_id}</dd>
                  <dt>Frame</dt><dd className="lx-num">{selectedFrame.cvat.frame}</dd>
                  <dt>Annotation</dt><dd>{selectedFrame.shapes.length} box</dd>
                  <dt>Candidate</dt><dd>{selectedFrame.candidates.length}</dd>
                </dl>
              </div>
              <div className="lx-ws__sec">
                <h2 className="lx-h2">Candidate QC</h2>
                {selectedFrame.candidates.length === 0 && <p className="lx-muted">Không có candidate trên frame này.</p>}
                <div className="lx-review-candidates">
                  {selectedFrame.candidates.map((candidate) => (
                    <article className="lx-review-candidate" key={candidate.id}>
                      <div className="lx-row lx-review-panel-heading">
                        <b className="lx-mono">{candidate.rule_id}</b>
                        <span className={`lx-badge lx-badge--${candidate.severity === 'high' ? 'danger' : 'warning'}`}>
                          {severityLabels[candidate.severity] ?? candidate.severity}
                        </span>
                      </div>
                      <p>{candidate.message}</p>
                      <div className="lx-cell__sub">{candidate.engine} · {candidate.family} · box {candidate.shape_ids.join(', ') || '—'}</div>
                    </article>
                  ))}
                </div>
              </div>
            </aside>
          </div>
        </>
      )}
    </AppShell>
  );
}

export default function ReviewPage() {
  return (
    <AuthGuard
      permissionCheck={canAccessReview}
      requiresIdentity
      requiredPermissionName="Reviewer / QA Lead / Super Admin, có liên kết CVAT"
    >
      <Suspense fallback={<div className="lx-card lx-card__body">Đang mở Review Workspace…</div>}>
        <ReviewWorkspace />
      </Suspense>
    </AuthGuard>
  );
}
