'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth/auth-context';
import { getTasks, type Dataset, type CvatTask } from '@/lib/snapshots/api';
import type { Run } from '@/lib/execution/api';
import { errorMessage } from '@/lib/api/errors';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';
import {
  ILLUSTRATIVE_METRICS,
  ILLUSTRATIVE_ENGINES,
  ILLUSTRATIVE_REVIEW_QUEUES,
  ILLUSTRATIVE_TASKS,
  ILLUSTRATIVE_CANDIDATE_CATEGORIES,
} from '@/lib/overview/sample-data';

interface QualitySummaryProps {
  currentDataset?: Dataset | null;
  selectedRun?: Run | null;
  selectedTaskScope?: string | null;
  onTaskScopeChange?: (task: string | null) => void;
}

function realFrames(task: { jobs?: { frame_count?: number }[] }): string | null {
  const jobs = task.jobs ?? [];
  return jobs.some((job) => job.frame_count !== undefined)
    ? jobs.reduce((sum, job) => sum + (job.frame_count ?? 0), 0).toLocaleString('en-US') : null;
}

export function QualitySummary({
  currentDataset,
  selectedRun,
  selectedTaskScope,
  onTaskScopeChange,
}: QualitySummaryProps) {
  const { user, datasetId } = useAuth();
  const currentUserId = user?.id ?? null;
  const ownerKey =
    currentUserId !== null && currentDataset?.id
      ? `${currentUserId}:${currentDataset.id}`
      : null;

  const [taskState, setTaskState] = useState<{
    owner: string | null;
    tasks: CvatTask[];
    error: string | null;
  }>({ owner: null, tasks: [], error: null });
  const [isTasksLoading, setIsTasksLoading] = useState(false);
  const [tasksRetryNonce, setTasksRetryNonce] = useState(0);
  const tasksGen = React.useRef(0);

  // Local task scope for illustrative preview (when no backend dataset is selected)
  const [previewTaskScope, setPreviewTaskScope] = useState<string | null>(null);

  const handleRetryTasks = React.useCallback(() => {
    setTasksRetryNonce((prev) => prev + 1);
  }, []);

  useEffect(() => {
    if (!currentDataset?.id || currentUserId === null) {
      Promise.resolve().then(() => {
        setTaskState({ owner: null, tasks: [], error: null });
        setIsTasksLoading(false);
      });
      return;
    }
    const currentOwner = `${currentUserId}:${currentDataset.id}`;
    const gen = ++tasksGen.current;
    let active = true;

    Promise.resolve().then(() => {
      if (active && gen === tasksGen.current) {
        setIsTasksLoading(true);
        setTaskState((prev) =>
          prev.owner === currentOwner
            ? { ...prev, error: null }
            : { owner: null, tasks: [], error: null }
        );
      }
    });

    getTasks(currentDataset.id)
      .then((t) => {
        if (!active || gen !== tasksGen.current) return;
        setTaskState({ owner: currentOwner, tasks: t ?? [], error: null });
        setIsTasksLoading(false);
      })
      .catch((err: unknown) => {
        if (!active || gen !== tasksGen.current) return;
        setTaskState({
          owner: currentOwner,
          tasks: [],
          error: errorMessage(err) || 'Không thể tải danh sách Task',
        });
        setIsTasksLoading(false);
      });

    return () => {
      active = false;
    };
  }, [currentDataset?.id, currentUserId, tasksRetryNonce]);

  const visibleTasks = taskState.owner === ownerKey ? taskState.tasks : [];
  const visibleTasksError = taskState.owner === ownerKey ? taskState.error : null;

  // Determine whether we are rendering genuine backend data or illustrative fallback preview
  const isRealDataset = Boolean(currentDataset && datasetId !== null);
  const datasetDisplayName = currentDataset ? currentDataset.name : 'Road Vision Urban v1.4';
  const runDisplay = selectedRun
    ? `#${selectedRun.id} · ${selectedRun.status ? selectedRun.status.toUpperCase() : '—'}`
    : isRealDataset
    ? '—'
    : '#QC-091';

  return (
    <>
      {/* Header */}
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Quality Summary</h1>
          <p className="lx-lead">
            Tình trạng kiểm tra của {datasetDisplayName} · Quality Control Run: {runDisplay}. Coverage thấp và lỗi nghiêm trọng luôn hiển thị riêng, không gộp vào một điểm chất lượng duy nhất.
          </p>
        </div>
        <div className="lx-actions">
          {/* F-2: Real navigation links to existing routes */}
          <Link className="lx-btn" href="/reports">
            Xem Quality Report
          </Link>
          <Link className="lx-btn lx-btn--primary" href="/review">
            Vào Review Center →
          </Link>
        </div>
      </div>

      {/* Quality Gate callout */}
      {/* TODO(backend): Nối GET /api/runs/{id}/gate/ (runs_gate đã có sẵn trong OpenAPI contract; pending wiring chi tiết cho Quality Summary callout) */}
      <div className="lx-notice-banner lx-row">
        <SampleDataBadge />
        <NotConnectedNotice
          detail={
            isRealDataset
              ? 'Cổng phát hành (Quality Gate) trong Quality Summary'
              : 'Chưa có Dataset nào được chọn từ server; đang hiển thị bản xem trước theo thiết kế chuẩn'
          }
        />
      </div>
      <div className="lx-callout">
        <span className="lx-badge lx-badge--danger">Release blocked</span>
        <span className="lx-callout__text">
          Coverage 92.4% chưa đạt ngưỡng 95% · 3 lỗi nghiêm trọng chưa đóng · 12 yêu cầu sửa chờ xử lý.
        </span>
        {/* F-2: Real navigation link to Quality Gate */}
        <Link className="lx-btn lx-btn--sm" href="/reports/gate">
          Xem Quality Gate
        </Link>
      </div>

      {/* 4 Metric cards */}
      {/* TODO(backend): Đề xuất endpoint tổng hợp GET /api/runs/{id}/metrics/ để lấy Frame, Coverage, Candidate issue, Lỗi đã xác nhận (chưa có trong backend contract) */}
      <div className="lx-grid lx-grid--4">
        {ILLUSTRATIVE_METRICS.map((metric) => (
          <div className="lx-metric" key={metric.key}>
            <span className="lx-metric__k">{metric.key}</span>
            <span className={`lx-metric__v${metric.isWarn ? ' is-warn' : ''}`}>
              {metric.value}
            </span>
            {metric.progressPct !== undefined && (
              <div className="lx-progress lx-progress--warn" role="img" aria-label={`Coverage ${metric.value}`}>
                <i className="lx-w-pct-92" />
              </div>
            )}
            <span className={`lx-metric__n${metric.isBad ? ' is-bad' : ''}`}>
              {metric.note}
            </span>
          </div>
        ))}
      </div>

      {/* Row 1: Engine Status & Review Volume */}
      <div className="lx-cols">
        {/* Section: Engine Status */}
        {/* TODO(backend): Đề xuất endpoint tổng hợp GET /api/runs/{id}/engines/ để lấy trạng thái từng engine (chưa có trong backend contract) */}
        <section className="lx-card lx-main">
          <div className="lx-card__head">
            <h2 className="lx-h2">Trạng thái từng engine</h2>
            <Link className="lx-link lx-link-sm" href="/analysis/history">
              Xem Execution History
            </Link>
          </div>
          <div className="lx-notice-banner lx-row">
            <SampleDataBadge />
            <NotConnectedNotice detail="Tổng hợp trạng thái từng engine" />
          </div>
          <div className="lx-scroll">
            <table className="lx-table">
              <thead>
                <tr>
                  <th>Engine</th>
                  <th>Trạng thái</th>
                  <th className="r">Coverage</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {ILLUSTRATIVE_ENGINES.map((engine) => (
                  <tr key={engine.name}>
                    <td className="lx-cell__main">{engine.name}</td>
                    <td>
                      <span className={`lx-badge${engine.badgeTone ? ` lx-badge--${engine.badgeTone}` : ''}`}>
                        {engine.status}
                      </span>
                    </td>
                    <td className={`r${engine.coverage === '—' ? ' lx-subtle' : ''}`}>
                      {engine.coverage}
                    </td>
                    <td className="lx-muted">{engine.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Section: Review Volume */}
        {/* TODO(backend): Đề xuất endpoint tổng hợp GET /api/runs/{id}/review-volume/ để lấy khối lượng review (chưa có trong backend contract) */}
        <section className="lx-card lx-side">
          <div className="lx-card__head">
            <h2 className="lx-h2">Khối lượng review</h2>
            <Link className="lx-link lx-link-sm" href="/review">
              Mở hàng đợi
            </Link>
          </div>
          <div className="lx-notice-banner lx-row">
            <SampleDataBadge />
            <NotConnectedNotice detail="Tổng hợp khối lượng review" />
          </div>
          <div className="lx-card__body lx-stack lx-stack--14">
            {ILLUSTRATIVE_REVIEW_QUEUES.map((item) => (
              <div className="lx-stack lx-stack--tight" key={item.label}>
                <div className="lx-row lx-row--between">
                  <span>{item.label}</span>
                  <b className="lx-num">{item.count}</b>
                </div>
                <div className="lx-progress" role="img" aria-label={`${item.label}: ${item.count}`}>
                  <i className={item.widthClass} />
                </div>
                <span className="lx-hint">{item.hint}</span>
              </div>
            ))}
            <div className="lx-row lx-row--between lx-row--border-top lx-pt-1">
              <span className="lx-muted">Đã xử lý</span>
              <b className="lx-num">242</b>
            </div>
          </div>
        </section>
      </div>

      {/* Row 2: Tasks & Candidate by Error Type */}
      <div className="lx-cols">
        {/* Section: By Task */}
        {/* TODO(backend): Đề xuất endpoint tổng hợp GET /api/runs/{id}/tasks-quality/ để lấy thống kê chất lượng theo từng Task (chưa có trong backend contract) */}
        <section className="lx-card lx-main">
          <div className="lx-card__head">
            <h2 className="lx-h2">Theo Task</h2>
            <span className="lx-hint">Chọn một dòng để đặt Phạm vi cho toàn module</span>
          </div>
          <div className="lx-notice-banner lx-row">
            <SampleDataBadge />
            <NotConnectedNotice
              detail={
                isRealDataset
                  ? 'Task, Job và Frame lấy từ server; Coverage, Candidate, Đã xác nhận và Gate là dữ liệu minh họa'
                  : 'Thống kê chất lượng theo từng Task'
              }
            />
          </div>
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-640">
              <thead>
                <tr>
                  <th>Task</th>
                  <th className="r">Job</th>
                  <th className="r">Frame</th>
                  <th className="r">Coverage</th>
                  <th className="r">Candidate</th>
                  <th className="r">Đã xác nhận</th>
                  <th>Gate</th>
                </tr>
              </thead>
              <tbody>
                {isRealDataset && isTasksLoading ? (
                  <tr>
                    <td colSpan={7} className="lx-state--table-muted">
                      Đang tải danh sách Task từ server…
                    </td>
                  </tr>
                ) : isRealDataset && visibleTasksError ? (
                  <tr>
                    <td colSpan={7} className="lx-state--table-danger">
                      <div className="lx-mb-2">{visibleTasksError}</div>
                      <button
                        type="button"
                        className="lx-btn lx-btn--sm"
                        onClick={handleRetryTasks}
                      >
                        Thử lại
                      </button>
                    </td>
                  </tr>
                ) : isRealDataset && visibleTasks.length > 0 ? (
                  visibleTasks.map((task, idx) => {
                    const taskLabel = `Task #${task.cvat_task_id}${task.name ? ` · ${task.name}` : ''}`;
                    const isSelected =
                      selectedTaskScope === taskLabel ||
                      selectedTaskScope === `Task #${task.cvat_task_id}`;
                    const illus = ILLUSTRATIVE_TASKS[idx % ILLUSTRATIVE_TASKS.length];
                    return (
                      <tr
                        key={task.cvat_task_id}
                        role="row"
                        tabIndex={0}
                        aria-selected={isSelected}
                        className={`lx-tr--clickable${isSelected ? ' is-selected' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onTaskScopeChange?.(taskLabel);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            e.stopPropagation();
                            onTaskScopeChange?.(taskLabel);
                          }
                        }}
                      >
                        <td>
                          <div className="lx-cell__main">{taskLabel}</div>
                          {task.jobs && task.jobs.length > 0 ? (
                            <div className="lx-cell__sub">
                              Jobs: {task.jobs.map((j) => `#${j.cvat_job_id}`).join(', ')}
                            </div>
                          ) : null}
                        </td>
                        <td className="r">{task.jobs?.length ?? '—'}</td>
                        <td className="r">{realFrames(task) ?? '—'}</td>
                        <td className={`r lx-muted${illus.isWarnCoverage ? ' is-warn' : ''}`}>{illus.coverage}</td>
                        <td className="r lx-muted">{illus.candidates}</td>
                        <td className="r lx-muted">{illus.confirmed}</td>
                        <td>
                          <span className={`lx-badge lx-badge--${illus.gateTone}`}>
                            {illus.gate}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  // Canonical illustrative tasks fallback (1:1 with Dashboard.dc.html)
                  ILLUSTRATIVE_TASKS.map((task) => {
                    const isSelected =
                      previewTaskScope === task.name ||
                      (!isRealDataset && !previewTaskScope && task.id === 'T-118');
                    return (
                      <tr
                        key={task.id}
                        role="row"
                        tabIndex={0}
                        aria-selected={isSelected}
                        className={`lx-tr--clickable${isSelected ? ' is-selected' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setPreviewTaskScope(task.name);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            e.stopPropagation();
                            setPreviewTaskScope(task.name);
                          }
                        }}
                      >
                        <td>
                          <div className="lx-cell__main">{task.name}</div>
                          <div className="lx-cell__sub">{task.sub}</div>
                        </td>
                        <td className="r">{task.jobs}</td>
                        <td className="r">{task.frames}</td>
                        <td className={`r${task.isWarnCoverage ? ' is-warn' : ''}`}>{task.coverage}</td>
                        <td className="r">{task.candidates}</td>
                        <td className="r">{task.confirmed}</td>
                        <td>
                          <span className={`lx-badge lx-badge--${task.gateTone}`}>
                            {task.gate}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Section: Candidate by Error Type */}
        {/* TODO(backend): Đề xuất endpoint tổng hợp GET /api/runs/{id}/candidate-categories/ để lấy phân loại candidate theo lỗi (chưa có trong backend contract) */}
        <section className="lx-card lx-side">
          <div className="lx-card__head">
            <h2 className="lx-h2">Candidate theo loại lỗi</h2>
          </div>
          <div className="lx-notice-banner lx-row">
            <SampleDataBadge />
            <NotConnectedNotice detail="Phân loại candidate issue theo lỗi" />
          </div>
          <div className="lx-card__body lx-stack lx-stack--12">
            {ILLUSTRATIVE_CANDIDATE_CATEGORIES.map((item) => (
              <div className="lx-bar" key={item.label}>
                <span>{item.label}</span>
                <div className="lx-bar__t">
                  <i className={item.widthClass} />
                </div>
                <span className="lx-bar__n">{item.count}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </>
  );
}
