'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/auth/auth-context';
import { getTasks, type Dataset, type CvatTask } from '@/lib/snapshots/api';
import type { Run } from '@/lib/execution/api';
import { errorMessage } from '@/lib/api/errors';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';

interface QualitySummaryProps {
  currentDataset?: Dataset | null;
  selectedRun?: Run | null;
  selectedTaskScope?: string | null;
  onTaskScopeChange?: (task: string | null) => void;
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

  const [reportNotice, setReportNotice] = useState<{ owner: string | null; message: string } | null>(null);
  const [gateNotice, setGateNotice] = useState<{ owner: string | null; message: string } | null>(null);
  const [taskState, setTaskState] = useState<{
    owner: string | null;
    tasks: CvatTask[];
    error: string | null;
  }>({ owner: null, tasks: [], error: null });
  const [isTasksLoading, setIsTasksLoading] = useState(false);
  const [tasksRetryNonce, setTasksRetryNonce] = useState(0);
  const tasksGen = React.useRef(0);

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
  const effectiveReportNotice = reportNotice?.owner === ownerKey ? reportNotice.message : null;
  const effectiveGateNotice = gateNotice?.owner === ownerKey ? gateNotice.message : null;

  if (datasetId === null || !currentDataset) {
    return (
      <div className="lx-card" style={{ padding: 'var(--space-6)', textAlign: 'center' }}>
        <h2 className="lx-h2">Chưa chọn Dataset</h2>
        <p className="lx-lead" style={{ marginTop: 'var(--space-2)' }}>
          Vui lòng chọn một Dataset từ Quality Control Home để xem Quality Summary.
        </p>
        <div style={{ marginTop: 'var(--space-4)' }}>
          <Link href="/" className="lx-btn lx-btn--primary">
            Về Quality Control Home
          </Link>
        </div>
      </div>
    );
  }

  const datasetDisplayName = currentDataset.name;
  const runDisplay = selectedRun
    ? `#${selectedRun.id} · ${selectedRun.status ? selectedRun.status.toUpperCase() : '—'}`
    : '—';

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
          <button
            type="button"
            className="lx-btn"
            onClick={() =>
              setReportNotice({
                owner: ownerKey,
                message: 'Xem Quality Report',
              })
            }
          >
            Xem Quality Report
          </button>
          <Link className="lx-btn lx-btn--primary" href="/review">
            Vào Review Center →
          </Link>
        </div>
      </div>

      {effectiveReportNotice && (
        <div role="status" aria-live="polite">
          <NotConnectedNotice detail={effectiveReportNotice} />
        </div>
      )}

      {/* Neutral Quality Gate callout */}
      <div className="lx-callout">
        <span className="lx-badge">Quality Gate: —</span>
        <span className="lx-callout__text">
          Chưa có dữ liệu đánh giá Quality Gate cho Dataset này.
        </span>
        <button
          type="button"
          className="lx-btn lx-btn--sm"
          onClick={() =>
            setGateNotice({
              owner: ownerKey,
              message: 'Xem Quality Gate',
            })
          }
        >
          Xem Quality Gate
        </button>
      </div>

      {effectiveGateNotice && (
        <div role="status" aria-live="polite">
          <NotConnectedNotice detail={effectiveGateNotice} />
        </div>
      )}

      {/* 4 Metric cards */}
      <div className="lx-grid lx-grid--4">
        <div className="lx-metric">
          <span className="lx-metric__k">Frame trong phạm vi</span>
          <span className="lx-metric__v">—</span>
          <span className="lx-metric__n">—</span>
        </div>
        <div className="lx-metric">
          <span className="lx-metric__k">Coverage</span>
          <span className="lx-metric__v">—</span>
          <div className="lx-progress" role="img" aria-label="Coverage: —">
            <i style={{ width: '0%' }} />
          </div>
          <span className="lx-metric__n">Ngưỡng yêu cầu: —</span>
        </div>
        <div className="lx-metric">
          <span className="lx-metric__k">Candidate issue</span>
          <span className="lx-metric__v">—</span>
          <span className="lx-metric__n">—</span>
        </div>
        <div className="lx-metric">
          <span className="lx-metric__k">Lỗi đã xác nhận</span>
          <span className="lx-metric__v">—</span>
          <span className="lx-metric__n">—</span>
        </div>
      </div>

      {/* Row 1: Engine Status & Review Volume */}
      <div className="lx-cols">
        <section className="lx-card lx-main">
          <div className="lx-card__head">
            <h2 className="lx-h2">Trạng thái từng engine</h2>
            <Link className="lx-link" href="/analysis/history" style={{ fontSize: '13px', marginLeft: 'auto' }}>
              Xem Execution History
            </Link>
          </div>
          <div style={{ padding: '0 var(--space-4) var(--space-2)' }}>
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
                <tr>
                  <td className="lx-cell__main">Schema / Taxonomy</td>
                  <td>—</td>
                  <td className="r">—</td>
                  <td className="lx-muted">—</td>
                </tr>
                <tr>
                  <td className="lx-cell__main">Geometry</td>
                  <td>—</td>
                  <td className="r">—</td>
                  <td className="lx-muted">—</td>
                </tr>
                <tr>
                  <td className="lx-cell__main">Duplicate / Overlap</td>
                  <td>—</td>
                  <td className="r">—</td>
                  <td className="lx-muted">—</td>
                </tr>
                <tr>
                  <td className="lx-cell__main">Mô hình độc lập</td>
                  <td>—</td>
                  <td className="r">—</td>
                  <td className="lx-muted">—</td>
                </tr>
                <tr>
                  <td className="lx-cell__main">Mô hình thị giác – ngôn ngữ</td>
                  <td>—</td>
                  <td className="r">—</td>
                  <td className="lx-muted">—</td>
                </tr>
                <tr>
                  <td className="lx-cell__main">Metric</td>
                  <td>—</td>
                  <td className="r">—</td>
                  <td className="lx-muted">—</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section className="lx-card lx-side">
          <div className="lx-card__head">
            <h2 className="lx-h2">Khối lượng review</h2>
            <Link className="lx-link" href="/review" style={{ fontSize: '13px', marginLeft: 'auto' }}>
              Mở hàng đợi
            </Link>
          </div>
          <div style={{ padding: '0 var(--space-4) var(--space-2)' }}>
            <NotConnectedNotice detail="Tổng hợp khối lượng review" />
          </div>
          <div className="lx-card__body lx-stack" style={{ gap: '14px' }}>
            <div className="lx-stack" style={{ gap: '6px' }}>
              <div className="lx-row" style={{ justifyContent: 'space-between' }}>
                <span>Ưu tiên theo rủi ro</span>
                <b className="lx-num">—</b>
              </div>
              <div className="lx-progress" role="img" aria-label="Ưu tiên theo rủi ro: —">
                <i style={{ width: '0%' }} />
              </div>
              <span className="lx-hint">—</span>
            </div>
            <div className="lx-stack" style={{ gap: '6px' }}>
              <div className="lx-row" style={{ justifyContent: 'space-between' }}>
                <span>Kiểm tra ngẫu nhiên</span>
                <b className="lx-num">—</b>
              </div>
              <div className="lx-progress" role="img" aria-label="Kiểm tra ngẫu nhiên: —">
                <i style={{ width: '0%' }} />
              </div>
              <span className="lx-hint">—</span>
            </div>
            <div className="lx-stack" style={{ gap: '6px' }}>
              <div className="lx-row" style={{ justifyContent: 'space-between' }}>
                <span>Chưa chắc chắn / Chuyển cấp trên</span>
                <b className="lx-num">—</b>
              </div>
              <div className="lx-progress" role="img" aria-label="Chưa chắc chắn / Chuyển cấp trên: —">
                <i style={{ width: '0%' }} />
              </div>
              <span className="lx-hint">Chờ phân xử tại Escalations</span>
            </div>
            <div className="lx-row" style={{ justifyContent: 'space-between', paddingTop: '4px', borderTop: '1px solid var(--border)' }}>
              <span className="lx-muted">Đã xử lý</span>
              <b className="lx-num">—</b>
            </div>
          </div>
        </section>
      </div>

      {/* Row 2: Tasks & Candidate by Error Type */}
      <div className="lx-cols">
        <section className="lx-card lx-main">
          <div className="lx-card__head">
            <h2 className="lx-h2">Theo Task</h2>
            <span className="lx-hint">Chọn một dòng để đặt Phạm vi cho toàn module</span>
          </div>
          <div style={{ padding: '0 var(--space-4) var(--space-2)' }}>
            <NotConnectedNotice detail="Thống kê chất lượng theo từng Task" />
          </div>
          <div className="lx-scroll">
            <table className="lx-table" style={{ minWidth: '640px' }}>
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
                {isTasksLoading ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', color: 'var(--ink-muted)', padding: 'var(--space-4)' }}>
                      Đang tải danh sách Task…
                    </td>
                  </tr>
                ) : visibleTasksError ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', color: 'var(--danger)', padding: 'var(--space-4)' }}>
                      <div style={{ marginBottom: 'var(--space-2)' }}>{visibleTasksError}</div>
                      <button
                        type="button"
                        className="lx-btn lx-btn--sm"
                        onClick={handleRetryTasks}
                      >
                        Thử lại
                      </button>
                    </td>
                  </tr>
                ) : visibleTasks.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'center', color: 'var(--ink-muted)', padding: 'var(--space-4)' }}>
                      Chưa có dữ liệu Task cho Dataset này
                    </td>
                  </tr>
                ) : (
                  visibleTasks.map((task) => {
                    const taskLabel = `Task #${task.cvat_task_id}${task.name ? ` · ${task.name}` : ''}`;
                    const isSelected =
                      selectedTaskScope === taskLabel ||
                      selectedTaskScope === `Task #${task.cvat_task_id}`;
                    return (
                      <tr
                        key={task.cvat_task_id}
                        role="row"
                        tabIndex={0}
                        aria-selected={isSelected}
                        className={isSelected ? 'is-selected' : undefined}
                        style={{ cursor: 'pointer' }}
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
                          {task.jobs && task.jobs.length > 0 && (
                            <div className="lx-cell__sub">
                              Jobs: {task.jobs.map((j) => `#${j.cvat_job_id}`).join(', ')}
                            </div>
                          )}
                        </td>
                        <td className="r">{task.jobs?.length ?? '—'}</td>
                        <td className="r">—</td>
                        <td className="r">—</td>
                        <td className="r">—</td>
                        <td className="r">—</td>
                        <td>—</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="lx-card lx-side">
          <div className="lx-card__head">
            <h2 className="lx-h2">Candidate theo loại lỗi</h2>
          </div>
          <div style={{ padding: '0 var(--space-4) var(--space-2)' }}>
            <NotConnectedNotice detail="Phân loại candidate issue theo lỗi" />
          </div>
          <div className="lx-card__body lx-stack" style={{ gap: '12px' }}>
            <div className="lx-bar">
              <span>Sai nhãn</span>
              <div className="lx-bar__t"><i style={{ width: '0%' }}></i></div>
              <span className="lx-bar__n">—</span>
            </div>
            <div className="lx-bar">
              <span>Hình học</span>
              <div className="lx-bar__t"><i style={{ width: '0%' }}></i></div>
              <span className="lx-bar__n">—</span>
            </div>
            <div className="lx-bar">
              <span>Trùng / chồng lấn</span>
              <div className="lx-bar__t"><i style={{ width: '0%' }}></i></div>
              <span className="lx-bar__n">—</span>
            </div>
            <div className="lx-bar">
              <span>Thiếu object</span>
              <div className="lx-bar__t"><i style={{ width: '0%' }}></i></div>
              <span className="lx-bar__n">—</span>
            </div>
            <div className="lx-bar">
              <span>Thuộc tính / Track</span>
              <div className="lx-bar__t"><i style={{ width: '0%' }}></i></div>
              <span className="lx-bar__n">—</span>
            </div>
          </div>
        </section>
      </div>
    </>
  );
}
