'use client';

import React from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth/auth-context';
import { hasDatasetPermission } from '@/lib/auth/roles';
import { useTasks } from '@/lib/snapshots/queries';
import { safeCvatUrl } from '@/lib/snapshots/api';
import { errorMessage } from '@/lib/api/errors';

const STAGES: Record<string, string> = { annotation: 'Gán nhãn', validation: 'Kiểm tra', acceptance: 'Nghiệm thu' };
const STATES: Record<string, string> = { new: 'Mới', in_progress: 'Đang thực hiện', rejected: 'Bị từ chối', completed: 'Hoàn tất' };

/** CVAT jobs are visible before a snapshot or QC run exists. */
export function CvatJobsPanel() {
  const { session, datasetId } = useAuth();
  const jobs = useTasks(session?.user.id, datasetId, datasetId !== null);
  const [search, setSearch] = React.useState('');
  if (datasetId === null) return null;
  const rows = (jobs.data ?? []).flatMap(task => task.jobs.map(job => ({ task, job })));
  const visible = rows.filter(({ task, job }) => `${task.name} ${task.cvat_task_id} ${job.cvat_job_id} ${job.assignee_name ?? ''}`
    .toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const canPrepare = hasDatasetPermission(session, datasetId, role => role === 'qa_lead' || role === 'super_admin');
  return <section className="lx-card" aria-label="Job từ CVAT">
    <div className="lx-card__head lx-row lx-row--between">
      <h2 className="lx-h2">Job từ CVAT <span className="lx-hint">({rows.length})</span></h2>
      <button type="button" className="lx-btn lx-btn--sm" disabled={jobs.isFetching} onClick={() => void jobs.refetch()}>
        {jobs.isFetching ? 'Đang tải…' : 'Làm mới từ CVAT'}
      </button>
    </div>
    <div className="lx-card__body lx-stack">
      <p className="lx-muted">Các job hiện có trên CVAT, gồm cả job chưa chạy kiểm tra trong LabelX.</p>
      <input className="lx-input" aria-label="Tìm Task hoặc Job CVAT" placeholder="Tìm Task, Job hoặc người thực hiện…"
        value={search} onChange={event => setSearch(event.target.value)} />
      {jobs.isPending && <p role="status">Đang tải Job từ CVAT…</p>}
      {jobs.isError && <p role="alert">{errorMessage(jobs.error)}</p>}
      {jobs.isSuccess && !rows.length && <p className="lx-muted">Dataset này chưa có Job trên CVAT.</p>}
      {!!rows.length && <div className="lx-scroll"><table className="lx-table"><thead><tr>
        <th>Job</th><th>Task</th><th>Người thực hiện</th><th>Giai đoạn</th><th>Trạng thái CVAT</th><th>Thao tác</th>
      </tr></thead><tbody>{visible.map(({ task, job }) => {
        const url = safeCvatUrl(job.cvat_url);
        return <tr key={job.cvat_job_id}>
          <td>Job #{job.cvat_job_id}</td><td>{task.name} · #{task.cvat_task_id}</td>
          <td>{job.assignee_name || (job.assignee_cvat_user_id ? `CVAT #${job.assignee_cvat_user_id}` : 'Chưa gán')}</td>
          <td>{job.stage ? STAGES[job.stage] ?? job.stage : '—'}</td>
          <td>{job.state ? STATES[job.state] ?? job.state : '—'}</td>
          <td><div className="lx-row lx-gap-2">
            {url && <a href={url} target="_blank" rel="noopener noreferrer">Mở CVAT ↗</a>}
            {canPrepare && <Link href={`/analysis?jobId=${job.cvat_job_id}`}>Tạo snapshot cho Job</Link>}
          </div></td>
        </tr>;
      })}</tbody></table></div>}
      {!!rows.length && !visible.length && <p className="lx-muted">Không có Job khớp tìm kiếm.</p>}
    </div>
  </section>;
}
