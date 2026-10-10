'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { ApiRequestError } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { postSnapshot, type CvatTask, type SnapshotCreate } from '@/lib/snapshots/api';

export function SnapshotForm({ datasetId, tasks, canCreate, onRequestLockChange }: {
  datasetId: number; tasks: CvatTask[]; canCreate: boolean;
  onRequestLockChange?: (locked: boolean) => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [all, setAll] = React.useState(false);
  const [taskIds, setTaskIds] = React.useState<Set<number>>(new Set());
  const [jobIds, setJobIds] = React.useState<Set<number>>(new Set());
  const [note, setNote] = React.useState('');
  const [pending, setPending] = React.useState<{ body: SnapshotCreate; key: string } | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<string | null>(null);
  const busyRef = React.useRef(false);
  const jobCount = tasks.reduce((count, task) => count + task.jobs.length, 0);
  const selectedCount = tasks.reduce((count, task) => count +
    (taskIds.has(task.cvat_task_id) ? task.jobs.length : task.jobs.filter(job => jobIds.has(job.cvat_job_id)).length), 0);
  const canSubmit = canCreate && jobCount > 0 && (all || selectedCount > 0) && !busy && !pending;

  React.useEffect(() => {
    if (!pending) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const navigate = (event: MouseEvent) => {
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest('a[href]');
      if (!link) return;
      if (!window.confirm('Yêu cầu tạo Snapshot có thể vẫn đang chạy. Rời màn này?')) {
        event.preventDefault(); event.stopPropagation(); return;
      }
      onRequestLockChange?.(false);
    };
    window.addEventListener('beforeunload', warn);
    document.addEventListener('click', navigate, true);
    return () => { window.removeEventListener('beforeunload', warn); document.removeEventListener('click', navigate, true); };
  }, [pending, onRequestLockChange]);

  async function send(request: { body: SnapshotCreate; key: string }) {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); setPending(request); setFailure(null);
    onRequestLockChange?.(true);
    try {
      const accepted = await postSnapshot(request.body, request.key);
      setPending(null);
      onRequestLockChange?.(false);
      void queryClient.invalidateQueries({ queryKey: ['snapshot-history'] });
      router.push(`/analysis?snapshotId=${accepted.id}`);
    } catch (error) {
      if (error instanceof ApiRequestError && [400, 403, 409].includes(error.status)) {
        setPending(null); onRequestLockChange?.(false);
      }
      setFailure(errorMessage(error));
    } finally { busyRef.current = false; setBusy(false); }
  }

  function toggleTask(task: CvatTask) {
    const nextTasks = new Set(taskIds);
    const nextJobs = new Set(jobIds);
    if (nextTasks.has(task.cvat_task_id)) nextTasks.delete(task.cvat_task_id);
    else { nextTasks.add(task.cvat_task_id); task.jobs.forEach(job => nextJobs.delete(job.cvat_job_id)); }
    setTaskIds(nextTasks); setJobIds(nextJobs);
  }

  function toggleJob(jobId: number) {
    const next = new Set(jobIds);
    if (next.has(jobId)) next.delete(jobId); else next.add(jobId);
    setJobIds(next);
  }

  return <form className="lx-stack" onSubmit={event => {
    event.preventDefault();
    if (!canSubmit) return;
    const body: SnapshotCreate = { dataset_id: datasetId,
      scope: { cvat_task_ids: all ? [] : [...taskIds].sort((a, b) => a - b),
        cvat_job_ids: all ? [] : [...jobIds].sort((a, b) => a - b) },
      ...(note.trim() ? { note: note.trim() } : {}) };
    void send({ body, key: crypto.randomUUID() });
  }}>
    {!canCreate && <p className="lx-callout lx-callout--info">Bạn có quyền xem. Chỉ QA Lead hoặc Super Admin được tạo Snapshot.</p>}
    <fieldset className="lx-field" disabled={!canCreate || busy || !!pending}>
      <legend className="lx-label">Phạm vi Snapshot</legend>
      <div className="lx-row">
        <label><input type="radio" name="scope" checked={!all} onChange={() => setAll(false)} /> Chọn Task / Job</label>
        <label><input type="radio" name="scope" checked={all} onChange={() => setAll(true)} /> Toàn Dataset</label>
      </div>
      <div className="lx-scroll"><table className="lx-table"><thead><tr><th>Chọn</th><th>Task / Job</th><th>Người thực hiện</th><th>Frame</th></tr></thead>
        <tbody>{tasks.map(task => <React.Fragment key={task.cvat_task_id}>
          <tr><td><input type="checkbox" aria-label={`Chọn Task ${task.cvat_task_id}`} disabled={all || !task.jobs.length}
            checked={all || taskIds.has(task.cvat_task_id)} onChange={() => toggleTask(task)} /></td>
            <td>Task {task.cvat_task_id} · {task.name}</td><td>{task.jobs.length} Job</td><td>—</td></tr>
          {task.jobs.map(job => <tr key={job.cvat_job_id}><td><input type="checkbox" aria-label={`Chọn Job ${job.cvat_job_id}`}
            disabled={all || taskIds.has(task.cvat_task_id)}
            checked={all || taskIds.has(task.cvat_task_id) || jobIds.has(job.cvat_job_id)}
            onChange={() => toggleJob(job.cvat_job_id)} /></td>
            <td>Job {job.cvat_job_id}</td><td>{job.assignee_cvat_user_id ?? 'Chưa gán'}</td><td>{job.frame_count ?? '—'}</td></tr>)}
        </React.Fragment>)}</tbody></table></div>
      <p className="lx-hint">{all ? `Toàn Dataset · ${jobCount} Job` : `Đã chọn ${selectedCount} Job`}</p>
      {!jobCount && <p>Dataset chưa có Job để tạo Snapshot.</p>}
    </fieldset>
    <div className="lx-field"><label className="lx-label" htmlFor="snapshot-note">Ghi chú</label>
      <textarea id="snapshot-note" className="lx-textarea" maxLength={1000} value={note}
        disabled={!canCreate || !!pending} onChange={event => setNote(event.target.value)} /></div>
    {failure && <div className="lx-callout" role="alert">{failure}</div>}
    {pending && failure && <div className="lx-callout lx-callout--warning">
      Chưa rõ máy chủ đã nhận yêu cầu hay chưa. Gửi lại giữ nguyên nội dung và Idempotency-Key.
    </div>}
    <div className="lx-actions">{pending && failure ? <>
      <button className="lx-btn lx-btn--primary" type="button" onClick={() => void send(pending)}>Gửi lại cùng yêu cầu</button>
      <button className="lx-btn" type="button" onClick={() => {
        if (window.confirm('Yêu cầu có thể vẫn đang chạy. Bỏ theo dõi yêu cầu này?')) {
          setPending(null); setFailure(null); onRequestLockChange?.(false);
        }
      }}>Bỏ theo dõi</button>
    </> : <button className="lx-btn lx-btn--primary" type="submit" disabled={!canSubmit}>
      {busy ? 'Đang tạo…' : 'Tạo Snapshot'}</button>}</div>
  </form>;
}
