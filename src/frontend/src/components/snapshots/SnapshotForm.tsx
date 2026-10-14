'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useAuth } from '@/lib/auth/auth-context';
import { getDatasetGuideline, listGuidelineVersions } from '@/lib/guidelines/config-api';
import { cursorFrom } from '@/lib/execution/api';
import { ApiRequestError } from '@/lib/api/client';
import { errorMessage } from '@/lib/api/errors';
import { postSnapshot, type CvatTask, type SnapshotCreate } from '@/lib/snapshots/api';

export function SnapshotForm({ datasetId, tasks, canCreate, onRequestLockChange }: {
  datasetId: number; tasks: CvatTask[]; canCreate: boolean;
  onRequestLockChange?: (locked: boolean) => void;
}) {
  const router = useRouter();
  const { session } = useAuth();
  const guideline = useQuery({ queryKey: ['dataset-guideline', session?.user.id, datasetId],
    queryFn: ({ signal }) => getDatasetGuideline(datasetId, signal), retry: false });
  const versions = useInfiniteQuery({ queryKey: ['snapshot-guideline-versions', session?.user.id],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => listGuidelineVersions(pageParam, signal),
    getNextPageParam: page => cursorFrom(page.next) ?? undefined,
    retry: false, enabled: canCreate });
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = versions;
  React.useEffect(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  const available = versions.data?.pages.flatMap(page => page.results).filter(item => item.taxonomy_ready) ?? [];
  const [guidelineOverride, setGuidelineOverride] = React.useState('');
  const effectiveGuideline = guidelineOverride || (guideline.data?.taxonomy_ready ? guideline.data.guideline_version : null);
  const queryClient = useQueryClient();
  const [all, setAll] = React.useState(true);
  const [taskIds, setTaskIds] = React.useState<Set<number>>(new Set());
  const [jobIds, setJobIds] = React.useState<Set<number>>(new Set());
  const [note, setNote] = React.useState('');
  const [expanded, setExpanded] = React.useState<Set<number>>(new Set());
  const [pending, setPending] = React.useState<{ body: SnapshotCreate; key: string } | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState<string | null>(null);
  const busyRef = React.useRef(false);
  const jobCount = tasks.reduce((count, task) => count + task.jobs.length, 0);
  const selectedCount = tasks.reduce((count, task) => count +
    (taskIds.has(task.cvat_task_id) ? task.jobs.length : task.jobs.filter(job => jobIds.has(job.cvat_job_id)).length), 0);
  const canSubmit = !!effectiveGuideline && canCreate && jobCount > 0 && (all || selectedCount > 0) && !busy && !pending;
  const isSelected = (task: CvatTask, job: CvatTask['jobs'][number]) =>
    all || taskIds.has(task.cvat_task_id) || jobIds.has(job.cvat_job_id);
  const selectedJobs = tasks.flatMap(task => task.jobs.filter(job => isSelected(task, job)).map(job => ({ task, job })));
  const selectedTaskCount = new Set(selectedJobs.map(({ task }) => task.cvat_task_id)).size;
  const knownFrames = (jobs: CvatTask['jobs']) => jobs.some(job => job.frame_count !== undefined)
    ? jobs.reduce((sum, job) => sum + (job.frame_count ?? 0), 0) : null;
  const frameText = (value: number | null) => value === null ? '—' : value.toLocaleString('en-US');
  const selectedFrames = knownFrames(selectedJobs.map(({ job }) => job));
  const reset = () => { setAll(true); setTaskIds(new Set()); setJobIds(new Set()); setNote(''); setGuidelineOverride(''); setFailure(null); };

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
      ...(guidelineOverride ? { guideline_version: guidelineOverride }
        : { expected_guideline_version: guideline.data!.guideline_version! }),
      scope: { cvat_task_ids: all ? [] : [...taskIds].sort((a, b) => a - b),
        cvat_job_ids: all ? [] : [...jobIds].sort((a, b) => a - b) },
      ...(note.trim() ? { note: note.trim() } : {}) };
    void send({ body, key: crypto.randomUUID() });
  }}>
    <section className="lx-card lx-card__body" aria-label="Guideline áp dụng cho Snapshot">
      {guideline.isPending && <p role="status">Đang tải Guideline của Dataset…</p>}
      {guideline.isError && <p role="alert">{errorMessage(guideline.error)}</p>}
      {versions.isError && <p role="alert">Không tải được danh sách Guideline. {errorMessage(versions.error)}</p>}
      {guideline.data?.taxonomy_ready && <p>Guideline mặc định của Dataset: <strong>{guideline.data.guideline_version}</strong> · Taxonomy: {guideline.data.taxonomy_version}. Phiên bản này được lưu cùng Snapshot.</p>}
      <div className="lx-field">
        <label className="lx-label" htmlFor="snapshot-guideline">Guideline cho Snapshot này</label>
        <select id="snapshot-guideline" className="lx-select" value={guidelineOverride} disabled={!canCreate || busy || !!pending}
          onChange={event => setGuidelineOverride(event.target.value)}>
          <option value="">{guideline.data?.taxonomy_ready ? `Dùng mặc định Dataset · ${guideline.data.guideline_version}` : 'Chọn Guideline cho Snapshot'}</option>
          {available.map(item => <option key={item.version} value={item.version}>{item.version} · {item.taxonomy_version}</option>)}
        </select>
        <p className="lx-hint">Lựa chọn này chỉ áp dụng cho Snapshot mới, không đổi mặc định của Dataset. Guideline và taxonomy được đóng băng khi Snapshot được tạo.</p>
      </div>
      {guideline.data && !guideline.data.taxonomy_ready && !guidelineOverride && <p role="alert">Dataset chưa có Guideline với taxonomy. Chọn Guideline cho Snapshot này hoặc <Link className="lx-link" href="/configuration/guidelines">cấu hình mặc định cho Dataset</Link>.</p>}
    </section>
    {!canCreate && <p className="lx-callout lx-callout--info">Bạn có quyền xem. Chỉ QA Lead hoặc Super Admin được tạo Snapshot.</p>}
    <fieldset className="lx-field lx-fieldset" disabled={!canCreate || busy || !!pending}>
      <legend className="lx-label">Phạm vi kiểm tra</legend>
      <div className="lx-card lx-card--inner"><div className="lx-scroll"><table className="lx-table">
        <thead><tr>
          <th className="lx-th--check"><input type="checkbox" className="lx-check-accent" aria-label="Chọn tất cả" checked={all}
            disabled={!jobCount} onChange={() => setAll(!all)} /></th>
          <th>Task / Job</th><th>Người thực hiện · Giai đoạn</th><th className="r">Frame</th></tr></thead>
        <tbody>{tasks.map(task => <React.Fragment key={task.cvat_task_id}>
          <tr><td><input type="checkbox" className="lx-check-accent" aria-label={`Chọn Task ${task.cvat_task_id}`} disabled={all || !task.jobs.length}
            checked={all || taskIds.has(task.cvat_task_id)} onChange={() => toggleTask(task)} /></td>
            <td className="lx-cell__main">Task {task.cvat_task_id} · {task.name}</td>
            <td className="lx-muted">{task.jobs.length ? <button type="button" className="lx-btn lx-btn--ghost lx-btn--sm" aria-expanded={expanded.has(task.cvat_task_id)}
              onClick={() => setExpanded(current => { const next = new Set(current); if (!next.delete(task.cvat_task_id)) next.add(task.cvat_task_id); return next; })}>
              {expanded.has(task.cvat_task_id) ? '▾' : '▸'} {task.jobs.length} Job</button> : '0 Job'}</td>
            <td className="r">{frameText(knownFrames(task.jobs))}</td></tr>
          {expanded.has(task.cvat_task_id) && task.jobs.map(job => <tr key={job.cvat_job_id}><td><input type="checkbox" className="lx-check-accent" aria-label={`Chọn Job ${job.cvat_job_id}`}
            disabled={all || taskIds.has(task.cvat_task_id)}
            checked={isSelected(task, job)}
            onChange={() => toggleJob(job.cvat_job_id)} /></td>
            <td>Job {job.cvat_job_id}</td><td className="lx-muted">{job.assignee_cvat_user_id ?? 'Chưa gán'} · {/* TODO(backend): CvatJob chưa có giai đoạn */}—</td><td className="r">{frameText(job.frame_count ?? null)}</td></tr>)}
        </React.Fragment>)}</tbody></table></div></div>
      <p className="lx-hint">Chọn cả Task, hoặc mở số Job của Task để chọn từng Job. {all ? `Toàn Dataset · ${tasks.length} task · ${jobCount} job · ${frameText(knownFrames(tasks.flatMap(task => task.jobs)))} frame.`
        : `Hiện chọn ${selectedTaskCount} task · ${selectedCount} job · ${frameText(selectedFrames)} frame.`}</p>
      {!jobCount && <p>Dataset chưa có Job để tạo Snapshot.</p>}
    </fieldset>
    <div className="lx-field"><label className="lx-label" htmlFor="snapshot-note">Ghi chú</label>
      <textarea id="snapshot-note" className="lx-textarea" maxLength={1000} value={note} placeholder="Ví dụ: Snapshot sau đợt sửa lỗi hình học tuần 40"
        disabled={!canCreate || !!pending} onChange={event => setNote(event.target.value)} /></div>
    {failure && <div className="lx-callout" role="alert">{failure}</div>}
    {pending && failure && <div className="lx-callout lx-callout--warning">
      Chưa rõ máy chủ đã nhận yêu cầu hay chưa. Gửi lại giữ nguyên nội dung và Idempotency-Key.
    </div>}
    <div className="lx-actions lx-actions--end">{pending && failure ? <>
      <button className="lx-btn lx-btn--primary" type="button" onClick={() => void send(pending)}>Gửi lại cùng yêu cầu</button>
      <button className="lx-btn" type="button" onClick={() => {
        if (window.confirm('Yêu cầu có thể vẫn đang chạy. Bỏ theo dõi yêu cầu này?')) {
          setPending(null); setFailure(null); onRequestLockChange?.(false);
        }
      }}>Bỏ theo dõi</button>
    </> : <>
      <button className="lx-btn" type="button" disabled={busy || !!pending} onClick={reset}>Huỷ</button>
      <button className="lx-btn lx-btn--primary" type="submit" disabled={!canSubmit}>
        {busy ? 'Đang tạo…' : 'Tạo snapshot và cấu hình →'}</button>
    </>}</div>
  </form>;
}
