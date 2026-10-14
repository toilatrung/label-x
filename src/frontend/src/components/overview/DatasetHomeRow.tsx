'use client';

import React from 'react';
import type { Dataset } from '@/lib/snapshots/api';
import { runStatusLabel } from '@/lib/execution/api';
import { formatCount, formatDateTime } from '@/lib/format';
import {
  gateBadge,
  gateCondition,
  percentText,
  runStatusTone,
  taskFrameCount,
  useDatasetSummaries,
  useDatasetTasks,
  useRunDetail,
  useRunGate,
} from '@/lib/overview/api';

interface DatasetHomeRowProps {
  dataset: Dataset;
  isSelected: boolean;
  onSelect: (dataset: Dataset) => void;
  onOpen: (dataset: Dataset, href: string) => void;
}

const ArrowIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="lx-ico-16">
    <path d="M3 8h10M9 4l4 4-4 4" />
  </svg>
);

const PlusIcon = () => (
  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="lx-ico-16">
    <path d="M8 3v10M3 8h10" />
  </svg>
);

/**
 * Một dòng Dataset ở Quality Control Home (Main.dc.html). Chỉ dòng đang hiển thị mới tải chi tiết:
 * - Task / Job / Frame: GET /api/datasets/{id}/tasks/
 * - Run gần nhất (latest_run_id) và Issue đang mở (open_issue_count): GET /api/datasets/summary/ (một lần cho cả bảng)
 * - Trạng thái, thời điểm run: GET /api/runs/{id}/
 * - Coverage, Gate: GET /api/runs/{id}/gate/
 */
export function DatasetHomeRow({ dataset, isSelected, onSelect, onOpen }: DatasetHomeRowProps) {
  const tasks = useDatasetTasks(dataset.id);
  const summaries = useDatasetSummaries();
  const summary = summaries.data?.find((row) => row.dataset_id === dataset.id);
  const runId = summary?.latest_run_id ?? null;
  const runQuery = useRunDetail(runId);
  const run = runQuery.data ?? null;
  const gate = useRunGate(runId);
  const runPending = summaries.isPending || (runId !== null && runQuery.isPending);

  const failed = [tasks, summaries, runQuery, gate].filter((query) => query.isError);
  const retry = (event: React.MouseEvent) => {
    event.stopPropagation();
    failed.forEach((query) => void query.refetch());
  };

  const taskList = tasks.data;
  const jobCount = taskList?.reduce((sum, task) => sum + task.jobs.length, 0);
  const frameCount = taskList?.reduce((sum, task) => sum + taskFrameCount(task), 0);
  const coverage = gateCondition(gate.data, 'coverage');
  const badge = gateBadge(gate.data?.status);
  const noRun = summaries.isSuccess && runId === null;
  const action = noRun
    ? { href: '/analysis', tip: 'Tạo snapshot đầu tiên', icon: <PlusIcon /> }
    : { href: '/?view=summary', tip: 'Tiếp tục làm việc với Dataset này', icon: <ArrowIcon /> };
  const pending = <span className="lx-subtle">…</span>;

  return (
    <tr
      aria-selected={isSelected ? 'true' : undefined}
      onClick={() => onSelect(dataset)}
      className="lx-tr--clickable"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          onSelect(dataset);
        }
      }}
    >
      <td>
        <div className="lx-cell__main">
          {dataset.name}
          {isSelected && <span className="lx-hint"> · Đang chọn</span>}
        </div>
        <div className="lx-cell__sub">CVAT project #{dataset.cvat_project_id}</div>
      </td>
      <td className="r">
        {tasks.isPending ? pending : taskList ? `${taskList.length} / ${jobCount}` : '—'}
      </td>
      <td className="r">{tasks.isPending ? pending : taskList ? formatCount(frameCount) : '—'}</td>
      <td>
        {runPending ? pending : run ? (
          <>
            <span className="lx-mono">#{run.id}</span>{' '}
            <span className={`lx-badge${runStatusTone(run.status) ? ` lx-badge--${runStatusTone(run.status)}` : ''}`}>
              {runStatusLabel[run.status] ?? run.status}
            </span>
            <div className="lx-cell__sub">{formatDateTime(run.created_at)}</div>
          </>
        ) : noRun ? (
          <span className="lx-subtle">Chưa có Quality Control Run</span>
        ) : <span className="lx-subtle">—</span>}
        {failed.length > 0 && (
          <div className="lx-cell__sub" role="alert">
            <span className="lx-text-danger">Không tải được số liệu.</span>{' '}
            <button type="button" className="lx-btn lx-btn--sm" onClick={retry}>Thử lại</button>
          </div>
        )}
      </td>
      <td className={`r${noRun ? ' lx-subtle' : ''}`}>
        {runId !== null && gate.isPending ? pending : percentText(coverage?.observed)}
      </td>
      <td className={`r${noRun ? ' lx-subtle' : ''}`}>
        {summaries.isPending ? pending : summary && !noRun ? formatCount(summary.open_issue_count) : '—'}
      </td>
      <td>
        {runId !== null && gate.isPending ? pending : (
          <span className={`lx-badge${badge.tone ? ` lx-badge--${badge.tone}` : ''}`}>{badge.label}</span>
        )}
      </td>
      <td className="r">
        <button
          type="button"
          className="lx-iconbtn"
          data-tip={action.tip}
          aria-label={action.tip}
          onClick={(event) => {
            event.stopPropagation();
            onOpen(dataset, action.href);
          }}
          onKeyDown={(event) => event.stopPropagation()}
        >
          {action.icon}
        </button>
      </td>
    </tr>
  );
}
