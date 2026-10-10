'use client';

import React from 'react';
import Link from 'next/link';
import { safeCvatUrl, snapshotStatus, type Snapshot } from '@/lib/snapshots/api';

function JobRow({ job, drift }: { job: Snapshot['jobs'][number]; drift: boolean }) {
  const [frameIndex, setFrameIndex] = React.useState(0);
  const safeIndex = job.frames.length > 0 ? Math.min(Math.max(0, frameIndex), job.frames.length - 1) : 0;
  const frame = job.frames[safeIndex];
  const jobUrl = safeCvatUrl(job.cvat_url);
  const frameUrl = frame ? safeCvatUrl(frame.cvat_url) : null;


  return <tr>
    <td>Job #{job.cvat_job_id}{drift && <span className="lx-badge lx-badge--danger">Drift</span>}</td>
    <td>Task #{job.cvat_task_id}</td>
    <td>{job.assignee_user_id === null ? 'Chưa gán' : `User #${job.assignee_user_id}`}</td>
    <td className="lx-mono" style={{ overflowWrap: 'anywhere' }}>{job.job_hash || 'Chưa có'}</td>
    <td>{jobUrl ? <a href={jobUrl} target="_blank" rel="noopener noreferrer">Mở Job CVAT</a> : 'Liên kết không hợp lệ'}</td>
    <td>{job.frames.length > 0 ? <div className="lx-row">
      <select className="lx-select" aria-label={`Frame Job ${job.cvat_job_id}`} value={safeIndex}
        onChange={event => setFrameIndex(Number(event.target.value))}>
        {job.frames.map((item, index) => <option key={item.frame_index} value={index}>
          Frame {item.frame_index} · {item.file_name}</option>)}
      </select>
      {frameUrl && <a href={frameUrl} target="_blank" rel="noopener noreferrer">Mở Frame</a>}
    </div> : '—'}</td>
  </tr>;
}

export function SnapshotDetail({ item }: { item: Snapshot }) {
  const drift = item.drift_jobs.length > 0;
  return <section className="lx-card" aria-label="Chi tiết Snapshot">
    <div className="lx-card__head"><h2 className="lx-h2">SNP-{item.id}</h2>
      <span className={`lx-badge lx-badge--${item.status === 'locked' ? 'success' : item.status === 'failed' ? 'danger' : 'info'}`}>
        {snapshotStatus(item.status)}</span></div>
    <div className="lx-card__body lx-stack">
      <dl className="lx-kv">
        <dt>Dataset</dt><dd>#{item.dataset_id}</dd>
        <dt>Hash tổng</dt><dd className="lx-mono" style={{ overflowWrap: 'anywhere' }}>{item.revision_hash || 'Chưa có'}</dd>
        <dt>Snapshot cha</dt><dd>{item.parent_snapshot_id ? <Link href={`/analysis?snapshotId=${item.parent_snapshot_id}`}>
          SNP-{item.parent_snapshot_id}</Link> : 'Không có'}</dd>
        <dt>Shape bị bỏ qua</dt><dd>{item.out_of_scope_shapes ?? 'Chưa có dữ liệu'}</dd>
        <dt>Taxonomy</dt><dd>{item.taxonomy_version || '—'}</dd>
        <dt>Guideline</dt><dd>{item.guideline_version || '—'}</dd>
        <dt>Tạo lúc</dt><dd>{item.created_at}</dd>
        <dt>Khóa lúc</dt><dd>{item.locked_at || 'Chưa khóa'}</dd>
      </dl>
      <div className={`lx-callout lx-callout--${drift ? 'warning' : 'info'}`} role="status">
        {drift ? `Job có drift: ${item.drift_jobs.join(', ')}` : item.status === 'locked' ?
          'Không phát hiện drift.' : item.status === 'failed' && item.failure_reason === 'drift_detected' ?
          'Backend báo drift nhưng chưa trả danh sách Job.' : 'Chưa có kết quả kiểm drift.'}
      </div>
      {item.status === 'failed' && <div className="lx-callout" role="alert">
        {item.failure_reason === 'drift_detected' ? 'Annotation đã đổi trong lúc export; Snapshot không được khóa.' :
          'Snapshot thất bại khi export.'}</div>}
      <div className="lx-scroll"><table className="lx-table"><caption>Job trong Snapshot</caption>
        <thead><tr><th>Job</th><th>Task</th><th>Người thực hiện</th><th>Hash</th><th>CVAT</th><th>Frame</th></tr></thead>
        <tbody>{item.jobs.map(job => <JobRow key={`${item.id}:${job.cvat_job_id}`} job={job} drift={item.drift_jobs.includes(job.cvat_job_id)} />)}</tbody>
      </table></div>
      {!item.jobs.length && <p className="lx-muted">Chưa có Job trong Snapshot.</p>}
    </div>
  </section>;
}
