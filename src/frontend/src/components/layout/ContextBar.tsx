'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { ROLE_LABELS, canAccessAnalysis } from '@/lib/auth/roles';
import { isMockAuth } from '@/lib/auth/config';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import {
  getDatasets,
  getTasks,
  getSnapshot,
  cursorFrom,
  type Dataset,
  type CvatTask,
  type Snapshot,
} from '@/lib/snapshots/api';
import { listRuns, type Run } from '@/lib/execution/api';
import { errorMessage } from '@/lib/api/errors';

export interface ContextBarProps {
  datasetName?: string;
  dataset?: string;
  datasetIdOverride?: number;
  snapshotName?: string;
  currentSnapshot?: string;
  isReadOnly?: boolean;
  guidelineVersion?: string;
  taxonomyVersion?: string;
  activeRun?: string;
  scopeName?: string;
  onScopeChange?: (scope: string) => void;
  isOverview?: boolean;
  onDatasetSelect?: (dataset: Dataset) => void;
  onRunSelect?: (run: Run | null) => void;
  selectedRun?: Run | null;
  openMenuId?: string | null;
  onOpenMenuChange?: (id: string | null) => void;
}

export function ContextBar({
  datasetName,
  dataset,
  datasetIdOverride,
  snapshotName,
  currentSnapshot,
  isReadOnly = false,
  guidelineVersion = '—',
  taxonomyVersion = '—',
  activeRun = '—',
  scopeName = 'Toàn dataset',
  onScopeChange,
  isOverview = false,
  onDatasetSelect,
  onRunSelect,
  selectedRun: selectedRunProp,
  openMenuId,
  onOpenMenuChange,
}: ContextBarProps) {
  const { user, datasetId, setDatasetId, hasPermission } = useAuth();
  const currentUserId = user?.id ?? null;
  const roleLabel = user?.role ? ROLE_LABELS[user.role] : 'Chưa có quyền trong phạm vi này';

  const isControlled = openMenuId !== undefined;
  const [internalOpenMenu, setInternalOpenMenu] = useState<string | null>(null);
  const currentOpenMenu = isControlled ? openMenuId : internalOpenMenu;

  const setMenu = useCallback(
    (menu: string | null) => {
      if (onOpenMenuChange) onOpenMenuChange(menu);
      if (!isControlled) setInternalOpenMenu(menu);
    },
    [isControlled, onOpenMenuChange]
  );

  const toggleMenu = (key: 'ds' | 'run' | 'scope') => {
    setMenu(currentOpenMenu === `ctx:${key}` ? null : `ctx:${key}`);
  };

  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const triggerRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const effectiveDatasetId = datasetIdOverride ?? datasetId;
  const effectiveDatasetName = datasetName ?? dataset;
  const effectiveSnapshot = snapshotName ?? currentSnapshot ?? '—';
  const hasDataset = effectiveDatasetId !== null;

  const runKey =
    currentUserId !== null && effectiveDatasetId !== null
      ? `${currentUserId}:${effectiveDatasetId}`
      : null;

  const isRunControlled = selectedRunProp !== undefined;
  const [internalSelectedRun, setInternalSelectedRun] = useState<{
    ownerKey: string | null;
    run: Run | null;
  }>({ ownerKey: null, run: null });
  const effectiveRun = isRunControlled
    ? selectedRunProp
    : internalSelectedRun?.ownerKey === runKey
    ? internalSelectedRun?.run
    : null;

  // Real dataset state
  const [datasetList, setDatasetList] = useState<Dataset[]>([]);
  const [datasetsNextCursor, setDatasetsNextCursor] = useState<string | undefined>(undefined);
  const [isDatasetsLoading, setIsDatasetsLoading] = useState(false);
  const [isLoadingMoreDatasets, setIsLoadingMoreDatasets] = useState(false);
  const [datasetsError, setDatasetsError] = useState<string | null>(null);
  const [datasetsLoadedUser, setDatasetsLoadedUser] = useState<number | null>(null);
  const [datasetsRetryNonce, setDatasetsRetryNonce] = useState(0);
  const datasetsGen = useRef(0);
  const inFlightDatasetsRef = useRef(false);
  const seenDatasetCursorsRef = useRef<Set<string>>(new Set());

  // Real run state
  const [runList, setRunList] = useState<Run[]>([]);
  const [runsNextCursor, setRunsNextCursor] = useState<string | undefined>(undefined);
  const [isRunsLoading, setIsRunsLoading] = useState(false);
  const [isLoadingMoreRuns, setIsLoadingMoreRuns] = useState(false);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [runsLoadedKey, setRunsLoadedKey] = useState<string | null>(null);
  const [runsRetryNonce, setRunsRetryNonce] = useState(0);
  const runsGen = useRef(0);
  const inFlightRunsRef = useRef(false);
  const seenRunCursorsRef = useRef<Set<string>>(new Set());

  // Real task state
  const [taskList, setTaskList] = useState<CvatTask[]>([]);
  const [isTasksLoading, setIsTasksLoading] = useState(false);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [tasksLoadedKey, setTasksLoadedKey] = useState<string | null>(null);
  const [tasksRetryNonce, setTasksRetryNonce] = useState(0);
  const tasksGen = useRef(0);
  const inFlightTasksRef = useRef(false);

  // Current snapshot identity and owner key strictly scoped to user and dataset
  const currentSnapshotId = effectiveRun?.snapshot_id ?? null;
  const snapshotOwnerKey =
    currentUserId !== null && effectiveDatasetId !== null && currentSnapshotId !== null
      ? `${currentUserId}:${effectiveDatasetId}:${currentSnapshotId}`
      : null;

  // Snapshot record state (for status check) strictly bound to owner key
  const [snapshotRecordState, setSnapshotRecordState] = useState<{
    key: string | null;
    snapshot: Snapshot | null;
  }>({ key: null, snapshot: null });

  // Informational or not-connected notice strictly bound to user and dataset
  const noticeOwnerKey =
    currentUserId !== null
      ? `${currentUserId}:${effectiveDatasetId ?? 'none'}`
      : null;

  const [notice, setNotice] = useState<{
    ownerKey: string | null;
    type: 'info' | 'not-connected';
    message: string;
  } | null>(null);
  const effectiveNotice =
    notice?.ownerKey !== null && notice?.ownerKey === noticeOwnerKey
      ? notice
      : null;

  // Invalidate all owned state when auth user changes
  useEffect(() => {
    datasetsGen.current++;
    inFlightDatasetsRef.current = false;
    seenDatasetCursorsRef.current = new Set();
    runsGen.current++;
    inFlightRunsRef.current = false;
    seenRunCursorsRef.current = new Set();
    tasksGen.current++;
    inFlightTasksRef.current = false;

    Promise.resolve().then(() => {
      setDatasetList([]);
      setDatasetsNextCursor(undefined);
      setIsDatasetsLoading(false);
      setIsLoadingMoreDatasets(false);
      setDatasetsError(null);
      setDatasetsLoadedUser(null);

      setRunList([]);
      setRunsNextCursor(undefined);
      setIsRunsLoading(false);
      setIsLoadingMoreRuns(false);
      setRunsError(null);
      setRunsLoadedKey(null);
      if (!isRunControlled) setInternalSelectedRun({ ownerKey: null, run: null });

      setTaskList([]);
      setIsTasksLoading(false);
      setTasksError(null);
      setTasksLoadedKey(null);

      setSnapshotRecordState({ key: null, snapshot: null });
      setNotice(null);
    });
  }, [currentUserId, isRunControlled]);

  // Invalidate runs and tasks when dataset changes
  useEffect(() => {
    runsGen.current++;
    inFlightRunsRef.current = false;
    seenRunCursorsRef.current = new Set();
    tasksGen.current++;
    inFlightTasksRef.current = false;

    Promise.resolve().then(() => {
      setRunList([]);
      setRunsNextCursor(undefined);
      setIsRunsLoading(false);
      setIsLoadingMoreRuns(false);
      setRunsError(null);
      setRunsLoadedKey(null);
      if (!isRunControlled) setInternalSelectedRun({ ownerKey: null, run: null });

      setTaskList([]);
      setIsTasksLoading(false);
      setTasksError(null);
      setTasksLoadedKey(null);

      setSnapshotRecordState({ key: null, snapshot: null });
      setNotice(null);
    });
  }, [effectiveDatasetId, isRunControlled]);

  // Fetch datasets when dataset picker opens
  useEffect(() => {
    if (currentOpenMenu !== 'ctx:ds' || !isOverview || currentUserId === null) return;
    if (datasetsLoadedUser === currentUserId || inFlightDatasetsRef.current) return;

    inFlightDatasetsRef.current = true;
    const gen = ++datasetsGen.current;
    setIsDatasetsLoading(true);
    setDatasetsError(null);

    getDatasets()
      .then((page) => {
        if (gen !== datasetsGen.current) return;
        setDatasetList(page.results ?? []);
        setDatasetsNextCursor(cursorFrom(page.next));
        setDatasetsLoadedUser(currentUserId);
        setIsDatasetsLoading(false);
        inFlightDatasetsRef.current = false;
      })
      .catch((err: unknown) => {
        if (gen !== datasetsGen.current) return;
        setDatasetsError(errorMessage(err) || 'Không thể tải danh sách Dataset');
        setDatasetsLoadedUser(currentUserId);
        setIsDatasetsLoading(false);
        inFlightDatasetsRef.current = false;
      });
  }, [currentOpenMenu, isOverview, currentUserId, datasetsLoadedUser, datasetsRetryNonce]);

  const handleLoadMoreDatasets = useCallback(async () => {
    if (!datasetsNextCursor || isLoadingMoreDatasets || inFlightDatasetsRef.current) return;
    if (seenDatasetCursorsRef.current.has(datasetsNextCursor)) {
      setDatasetsError('Phát hiện vòng lặp phân trang từ server khi tải thêm Dataset.');
      return;
    }
    inFlightDatasetsRef.current = true;
    setIsLoadingMoreDatasets(true);
    setDatasetsError(null);
    const targetCursor = datasetsNextCursor;
    const gen = datasetsGen.current;
    try {
      const page = await getDatasets(targetCursor);
      if (gen !== datasetsGen.current) return;
      seenDatasetCursorsRef.current.add(targetCursor);
      const newItems = page.results ?? [];
      setDatasetList((prev) => {
        const existingIds = new Set(prev.map((d) => d.id));
        const added = newItems.filter((d) => !existingIds.has(d.id));
        return [...prev, ...added];
      });
      const next = cursorFrom(page.next);
      if (next && (seenDatasetCursorsRef.current.has(next) || next === targetCursor)) {
        setDatasetsError('Phát hiện vòng lặp phân trang từ server khi tải thêm Dataset.');
        setDatasetsNextCursor(undefined);
      } else {
        setDatasetsNextCursor(next);
      }
    } catch (err: unknown) {
      if (gen !== datasetsGen.current) return;
      setDatasetsError(`Lỗi tải thêm: ${errorMessage(err)}`);
    } finally {
      if (gen === datasetsGen.current) {
        setIsLoadingMoreDatasets(false);
        inFlightDatasetsRef.current = false;
      }
    }
  }, [datasetsNextCursor, isLoadingMoreDatasets]);

  const canAccessRuns = hasPermission(canAccessAnalysis);

  useEffect(() => {
    if (currentOpenMenu !== 'ctx:run' || !isOverview || !runKey || !effectiveDatasetId) return;
    if (!canAccessRuns) return;
    if (runsLoadedKey === runKey || inFlightRunsRef.current) return;

    inFlightRunsRef.current = true;
    const gen = ++runsGen.current;
    setIsRunsLoading(true);
    setRunsError(null);

    listRuns(effectiveDatasetId, null)
      .then((page) => {
        if (gen !== runsGen.current) return;
        setRunList(page.results ?? []);
        setRunsNextCursor(cursorFrom(page.next));
        setRunsLoadedKey(runKey);
        setIsRunsLoading(false);
        inFlightRunsRef.current = false;
      })
      .catch((err: unknown) => {
        if (gen !== runsGen.current) return;
        setRunsError(errorMessage(err) || 'Không thể tải danh sách QC Run');
        setRunsLoadedKey(runKey);
        setIsRunsLoading(false);
        inFlightRunsRef.current = false;
      });
  }, [
    currentOpenMenu,
    isOverview,
    runKey,
    effectiveDatasetId,
    canAccessRuns,
    runsLoadedKey,
    runsRetryNonce,
  ]);

  const handleLoadMoreRuns = useCallback(async () => {
    if (!runsNextCursor || !effectiveDatasetId || isLoadingMoreRuns || inFlightRunsRef.current)
      return;
    if (seenRunCursorsRef.current.has(runsNextCursor)) {
      setRunsError('Phát hiện vòng lặp phân trang từ server khi tải thêm QC Run.');
      return;
    }
    inFlightRunsRef.current = true;
    setIsLoadingMoreRuns(true);
    setRunsError(null);
    const targetCursor = runsNextCursor;
    const gen = runsGen.current;
    try {
      const page = await listRuns(effectiveDatasetId, targetCursor);
      if (gen !== runsGen.current) return;
      seenRunCursorsRef.current.add(targetCursor);
      const newItems = page.results ?? [];
      setRunList((prev) => {
        const existingIds = new Set(prev.map((r) => r.id));
        const added = newItems.filter((r) => !existingIds.has(r.id));
        return [...prev, ...added];
      });
      const next = cursorFrom(page.next);
      if (next && (seenRunCursorsRef.current.has(next) || next === targetCursor)) {
        setRunsError('Phát hiện vòng lặp phân trang từ server khi tải thêm QC Run.');
        setRunsNextCursor(undefined);
      } else {
        setRunsNextCursor(next);
      }
    } catch (err: unknown) {
      if (gen !== runsGen.current) return;
      setRunsError(`Lỗi tải thêm: ${errorMessage(err)}`);
    } finally {
      if (gen === runsGen.current) {
        setIsLoadingMoreRuns(false);
        inFlightRunsRef.current = false;
      }
    }
  }, [runsNextCursor, effectiveDatasetId, isLoadingMoreRuns]);

  // Fetch tasks when scope picker opens
  const taskKey =
    currentUserId !== null && effectiveDatasetId !== null
      ? `${currentUserId}:${effectiveDatasetId}`
      : null;

  useEffect(() => {
    if (currentOpenMenu !== 'ctx:scope' || !isOverview || !taskKey || !effectiveDatasetId) return;
    if (tasksLoadedKey === taskKey || inFlightTasksRef.current) return;

    inFlightTasksRef.current = true;
    const gen = ++tasksGen.current;
    setIsTasksLoading(true);
    setTasksError(null);

    getTasks(effectiveDatasetId)
      .then((tasks) => {
        if (gen !== tasksGen.current) return;
        setTaskList(tasks ?? []);
        setTasksLoadedKey(taskKey);
        setIsTasksLoading(false);
        inFlightTasksRef.current = false;
      })
      .catch((err: unknown) => {
        if (gen !== tasksGen.current) return;
        setTasksError(errorMessage(err) || 'Không thể tải danh sách Task');
        setTasksLoadedKey(taskKey);
        setIsTasksLoading(false);
        inFlightTasksRef.current = false;
      });
  }, [currentOpenMenu, isOverview, taskKey, effectiveDatasetId, tasksLoadedKey, tasksRetryNonce]);

  // Inspect snapshot status when a run with snapshot_id is selected
  useEffect(() => {
    if (!snapshotOwnerKey || !currentSnapshotId) {
      Promise.resolve().then(() => {
        setSnapshotRecordState({ key: null, snapshot: null });
      });
      return;
    }

    let active = true;
    Promise.resolve().then(() => {
      if (active) {
        setSnapshotRecordState({ key: null, snapshot: null });
      }
    });

    getSnapshot(currentSnapshotId)
      .then((snap) => {
        if (!active) return;
        setSnapshotRecordState({ key: snapshotOwnerKey, snapshot: snap });
      })
      .catch(() => {
        if (!active) return;
        setSnapshotRecordState({ key: null, snapshot: null });
      });

    return () => {
      active = false;
    };
  }, [snapshotOwnerKey, currentSnapshotId]);

  // Focus first menuitem when a menu opens
  useEffect(() => {
    if (currentOpenMenu && currentOpenMenu.startsWith('ctx:')) {
      const timer = requestAnimationFrame(() => {
        if (menuRef.current) {
          const items = menuRef.current.querySelectorAll<HTMLElement>(
            '[role="menuitem"]:not([disabled])'
          );
          if (items.length > 0) {
            items[0].focus();
          }
        }
      });
      return () => cancelAnimationFrame(timer);
    }
  }, [currentOpenMenu]);

  // Handle outside mousedown and Escape listeners when context menu is open
  useEffect(() => {
    const isContextOpen = isControlled
      ? currentOpenMenu?.startsWith('ctx:')
      : !!internalOpenMenu;
    if (!isContextOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setMenu(null);
      }
    }

    function handleDocumentEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        const triggerKey = currentOpenMenu?.replace('ctx:', '');
        setMenu(null);
        if (triggerKey) triggerRefs.current[triggerKey]?.focus();
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleDocumentEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleDocumentEscape);
    };
  }, [isControlled, currentOpenMenu, internalOpenMenu, setMenu]);

  // Scoped menu keyboard navigation
  const handleMenuKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End', 'Escape'].includes(e.key)) return;

      if (e.key === 'Escape') {
        e.preventDefault();
        const triggerKey = currentOpenMenu?.replace('ctx:', '');
        setMenu(null);
        if (triggerKey) triggerRefs.current[triggerKey]?.focus();
        return;
      }

      const items = Array.from(
        e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not([disabled])')
      );
      if (items.length === 0) return;

      const currentIndex = items.findIndex((item) => item === document.activeElement);

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const nextIndex = currentIndex < 0 ? 0 : (currentIndex + 1) % items.length;
        items[nextIndex].focus();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prevIndex = currentIndex <= 0 ? items.length - 1 : currentIndex - 1;
        items[prevIndex].focus();
      } else if (e.key === 'Home') {
        e.preventDefault();
        items[0].focus();
      } else if (e.key === 'End') {
        e.preventDefault();
        items[items.length - 1].focus();
      }
    },
    [currentOpenMenu, setMenu]
  );

  // For other modules (default shared static context bar matching baseline)
  if (!isOverview) {
    const displayedDatasetBaseline = !hasDataset
      ? 'Chưa chọn'
      : effectiveDatasetName ??
        `${isMockAuth ? 'Dataset mẫu' : 'Dataset'} #${datasetIdOverride ?? datasetId}`;
    const displayedSnapshotBaseline =
      effectiveSnapshot === '—' ? 'Chưa chọn' : effectiveSnapshot;
    const displayedRunBaseline = activeRun === '—' ? 'Chưa chọn' : activeRun;

    return (
      <div className="lx-ctxbar" aria-label="Ngữ cảnh làm việc">
        <div className="lx-row lx-context-items">
          <div className="lx-chip lx-chip--static">
            <span className="lx-chip__k">Dataset:</span>
            <span className="lx-chip__v">{displayedDatasetBaseline}</span>
            {isReadOnly && <span className="lx-tag lx-tag--ro">read-only</span>}
          </div>

          <div className="lx-chip lx-chip--static">
            <span className="lx-chip__k">Quality Control Run:</span>
            <span className="lx-chip__v" style={{ color: 'var(--warning)' }}>
              {displayedRunBaseline}
            </span>
          </div>

          <div className="lx-chip lx-chip--static">
            <span className="lx-chip__k">Snapshot:</span>
            <span className="lx-chip__v">{displayedSnapshotBaseline}</span>
          </div>

          <div className="lx-chip lx-chip--static">
            <span className="lx-chip__k">Guideline:</span>
            <span className="lx-chip__v">{guidelineVersion}</span>
          </div>

          <div className="lx-chip lx-chip--static">
            <span className="lx-chip__k">Taxonomy:</span>
            <span className="lx-chip__v">{taxonomyVersion}</span>
          </div>

          <div className="lx-chip lx-chip--static" style={{ marginLeft: 'auto' }}>
            <span className="lx-chip__k">Vai trò:</span>
            <span className="lx-chip__v" style={{ color: 'var(--primary)' }}>
              {roleLabel}
            </span>
          </div>
        </div>
      </div>
    );
  }

  // Synchronously filter visible items and errors by active owner keys
  const visibleDatasetList =
    currentUserId !== null && datasetsLoadedUser === currentUserId
      ? datasetList
      : [];
  const visibleDatasetsError =
    currentUserId !== null && datasetsLoadedUser === currentUserId
      ? datasetsError
      : null;

  const visibleRunList =
    runKey !== null && runsLoadedKey === runKey
      ? runList
      : [];
  const visibleRunsError =
    runKey !== null && runsLoadedKey === runKey
      ? runsError
      : null;

  const visibleTaskList =
    taskKey !== null && tasksLoadedKey === taskKey
      ? taskList
      : [];
  const visibleTasksError =
    taskKey !== null && tasksLoadedKey === taskKey
      ? tasksError
      : null;

  const currentSnapshotRecord =
    snapshotRecordState.key === snapshotOwnerKey &&
    snapshotRecordState.snapshot?.id === currentSnapshotId
      ? snapshotRecordState.snapshot
      : null;

  // Overview ContextBar (exact canonical TopBar.dc.html order, no colons, real data or “—”)
  const displayedDataset = effectiveDatasetName ?? '—';
  const displayedRun = effectiveRun
    ? `#${effectiveRun.id} · ${effectiveRun.status ? effectiveRun.status.toUpperCase() : '—'}`
    : activeRun === 'Chưa chọn' || !activeRun
    ? '—'
    : activeRun;
  const displayedSnapshot = effectiveRun?.snapshot_id
    ? `#${effectiveRun.snapshot_id}`
    : effectiveSnapshot === 'Chưa chọn' || !effectiveSnapshot
    ? '—'
    : effectiveSnapshot;
  const isSnapshotSelected = displayedSnapshot !== '—';
  const isLocked = isSnapshotSelected && currentSnapshotRecord?.status === 'locked';

  return (
    <>
      <div className="lx-ctxbar" aria-label="Ngữ cảnh làm việc" ref={containerRef}>
        {/* 1. Dataset */}
        <div className="lx-ctx">
          <button
            type="button"
            className="lx-chip"
            aria-haspopup="menu"
            aria-expanded={currentOpenMenu === 'ctx:ds'}
            ref={(el) => {
              triggerRefs.current['ds'] = el;
            }}
            onClick={() => toggleMenu('ds')}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                setMenu('ctx:ds');
              } else if (e.key === 'Escape' && currentOpenMenu === 'ctx:ds') {
                e.preventDefault();
                setMenu(null);
              }
            }}
          >
            <span className="lx-chip__k">Dataset</span>{' '}
            <span className="lx-chip__v">{displayedDataset}</span>
            {isReadOnly && <span className="lx-tag lx-tag--ro">read-only</span>}
            <svg
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
              style={{ width: 10, height: 10, marginLeft: 4 }}
            >
              <path d="M3 4.5 6 7.5 9 4.5" />
            </svg>
          </button>
          {currentOpenMenu === 'ctx:ds' && (
            <div className="lx-menu" role="menu" ref={menuRef} onKeyDown={handleMenuKeyDown}>
              <div className="lx-menu__head">Dataset và Version</div>
              {isDatasetsLoading && visibleDatasetList.length === 0 ? (
                <div className="lx-menu__item" style={{ color: 'var(--ink-muted)' }}>
                  Đang tải danh sách Dataset…
                </div>
              ) : visibleDatasetsError && visibleDatasetList.length === 0 ? (
                <div
                  className="lx-menu__item"
                  style={{
                    color: 'var(--danger)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    alignItems: 'flex-start',
                  }}
                >
                  <span>{visibleDatasetsError}</span>
                  <button
                    type="button"
                    className="lx-btn lx-btn--sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDatasetsLoadedUser(null);
                      setDatasetsRetryNonce((n) => n + 1);
                    }}
                  >
                    Thử lại
                  </button>
                </div>
              ) : visibleDatasetList.length === 0 ? (
                <div className="lx-menu__item" style={{ color: 'var(--ink-muted)' }}>
                  Chưa có Dataset nào
                </div>
              ) : (
                <>
                  {visibleDatasetList.map((d) => {
                    const isSelected = d.id === effectiveDatasetId;
                    return (
                      <button
                        key={d.id}
                        type="button"
                        className={`lx-menu__item${isSelected ? ' is-active' : ''}`}
                        role="menuitem"
                        onClick={() => {
                          setDatasetId(d.id);
                          if (!isRunControlled) setInternalSelectedRun({ ownerKey: null, run: null });
                          onDatasetSelect?.(d);
                          onRunSelect?.(null);
                          onScopeChange?.('Toàn dataset');
                          setMenu(null);
                        }}
                      >
                        <span className="lx-menu__t">{d.name}</span>
                        {isSelected && (
                          <svg
                            className="lx-menu__check"
                            viewBox="0 0 16 16"
                            role="img"
                            aria-label="Đang chọn"
                            style={{
                              width: 14,
                              height: 14,
                              stroke: 'currentColor',
                              fill: 'none',
                              strokeWidth: 2,
                            }}
                          >
                            <path
                              d="M3 8.5 6.5 12 13 4.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        )}
                      </button>
                    );
                  })}
                  {datasetsNextCursor && (
                    <button
                      type="button"
                      className="lx-menu__item"
                      style={{ justifyContent: 'center', color: 'var(--primary)' }}
                      role="menuitem"
                      disabled={isLoadingMoreDatasets}
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleLoadMoreDatasets();
                      }}
                    >
                      {isLoadingMoreDatasets ? 'Đang tải thêm…' : 'Tải thêm Dataset…'}
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* 2. Quality Control Run */}
        <div className="lx-ctx">
          <button
            type="button"
            className="lx-chip"
            aria-haspopup="menu"
            aria-expanded={currentOpenMenu === 'ctx:run'}
            ref={(el) => {
              triggerRefs.current['run'] = el;
            }}
            onClick={() => toggleMenu('run')}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                setMenu('ctx:run');
              } else if (e.key === 'Escape' && currentOpenMenu === 'ctx:run') {
                e.preventDefault();
                setMenu(null);
              }
            }}
          >
            <span className="lx-chip__k">Quality Control Run</span>{' '}
            <span
              className="lx-chip__v"
              style={displayedRun === '—' ? { color: 'var(--ink-muted)' } : undefined}
            >
              {displayedRun}
            </span>
            <svg
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
              style={{ width: 10, height: 10, marginLeft: 4 }}
            >
              <path d="M3 4.5 6 7.5 9 4.5" />
            </svg>
          </button>
          {currentOpenMenu === 'ctx:run' && (
            <div className="lx-menu" role="menu" ref={menuRef} onKeyDown={handleMenuKeyDown}>
              <div className="lx-menu__head">Quality Control Run</div>
              {!effectiveDatasetId ? (
                <div
                  className="lx-menu__item"
                  style={{ color: 'var(--ink-muted)', cursor: 'default' }}
                >
                  Chưa chọn Dataset
                </div>
              ) : !canAccessRuns ? (
                <div
                  className="lx-menu__item"
                  style={{ color: 'var(--ink-muted)', cursor: 'default' }}
                >
                  Tài khoản của bạn không có quyền xem QC Run
                </div>
              ) : isRunsLoading && visibleRunList.length === 0 ? (
                <div className="lx-menu__item" style={{ color: 'var(--ink-muted)' }}>
                  Đang tải danh sách QC Run…
                </div>
              ) : visibleRunsError && visibleRunList.length === 0 ? (
                <div
                  className="lx-menu__item"
                  style={{
                    color: 'var(--danger)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    alignItems: 'flex-start',
                  }}
                >
                  <span>{visibleRunsError}</span>
                  <button
                    type="button"
                    className="lx-btn lx-btn--sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setRunsLoadedKey(null);
                      setRunsRetryNonce((n) => n + 1);
                    }}
                  >
                    Thử lại
                  </button>
                </div>
              ) : visibleRunList.length === 0 ? (
                <div
                  className="lx-menu__item"
                  style={{ color: 'var(--ink-muted)', cursor: 'default' }}
                >
                  Chưa có phiên chạy QC Run
                </div>
              ) : (
                <>
                  {visibleRunList.map((r) => {
                    const isSelected = effectiveRun?.id === r.id;
                    const statusUpper = r.status ? r.status.toUpperCase() : '—';
                    return (
                      <button
                        key={r.id}
                        type="button"
                        className={`lx-menu__item${isSelected ? ' is-active' : ''}`}
                        role="menuitem"
                        aria-label={`#${r.id} ${statusUpper}`}
                        onClick={() => {
                          if (!isRunControlled) setInternalSelectedRun({ ownerKey: runKey, run: r });
                          onRunSelect?.(r);
                          setMenu(null);
                        }}
                      >
                        <span className="lx-menu__t lx-mono">{`#${r.id}`}</span>
                        <span className="lx-menu__meta">{statusUpper}</span>
                        {isSelected && (
                          <svg
                            className="lx-menu__check"
                            viewBox="0 0 16 16"
                            role="img"
                            aria-label="Đang chọn"
                            style={{
                              width: 14,
                              height: 14,
                              stroke: 'currentColor',
                              fill: 'none',
                              strokeWidth: 2,
                              marginLeft: 6,
                            }}
                          >
                            <path
                              d="M3 8.5 6.5 12 13 4.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            />
                          </svg>
                        )}
                      </button>
                    );
                  })}
                  {runsNextCursor && (
                    <button
                      type="button"
                      className="lx-menu__item"
                      style={{ justifyContent: 'center', color: 'var(--primary)' }}
                      role="menuitem"
                      disabled={isLoadingMoreRuns}
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleLoadMoreRuns();
                      }}
                    >
                      {isLoadingMoreRuns ? 'Đang tải thêm…' : 'Tải thêm QC Run…'}
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* 3. Snapshot (Static pill, click provides read-only factual info) */}
        <button
          type="button"
          className="lx-chip lx-chip--static"
          title={isLocked ? 'Snapshot bất biến' : 'Snapshot'}
          ref={(el) => {
            triggerRefs.current['snap'] = el;
          }}
          onClick={() => {
            if (isSnapshotSelected) {
              setNotice({
                ownerKey: noticeOwnerKey,
                type: 'info',
                message: `Snapshot ${displayedSnapshot}${
                  isLocked
                    ? ' (bất biến, đã khoá)'
                    : currentSnapshotRecord?.status
                    ? ` (trạng thái: ${currentSnapshotRecord.status})`
                    : ''
                } · gắn theo Quality Control Run`,
              });
            } else {
              setNotice({
                ownerKey: noticeOwnerKey,
                type: 'info',
                message: 'Chưa chọn Snapshot cho phiên làm việc hiện tại',
              });
            }
          }}
        >
          <span className="lx-chip__k">Snapshot</span>{' '}
          <span className="lx-chip__v lx-mono">{displayedSnapshot}</span>
          {isLocked && (
            <svg
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              role="img"
              aria-label="Đã khoá"
              style={{ width: 12, height: 12, marginLeft: 4 }}
            >
              <rect x="3.5" y="7" width="9" height="6.5" rx="1.5" />
              <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
            </svg>
          )}
        </button>

        {/* 4. Phạm vi */}
        <div className="lx-ctx">
          <button
            type="button"
            className="lx-chip"
            aria-haspopup="menu"
            aria-expanded={currentOpenMenu === 'ctx:scope'}
            ref={(el) => {
              triggerRefs.current['scope'] = el;
            }}
            onClick={() => toggleMenu('scope')}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                setMenu('ctx:scope');
              } else if (e.key === 'Escape' && currentOpenMenu === 'ctx:scope') {
                e.preventDefault();
                setMenu(null);
              }
            }}
          >
            <span className="lx-chip__k">Phạm vi</span>{' '}
            <span className="lx-chip__v">{scopeName}</span>
            <svg
              viewBox="0 0 12 12"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              aria-hidden="true"
              style={{ width: 10, height: 10, marginLeft: 4 }}
            >
              <path d="M3 4.5 6 7.5 9 4.5" />
            </svg>
          </button>
          {currentOpenMenu === 'ctx:scope' && (
            <div className="lx-menu" role="menu" ref={menuRef} onKeyDown={handleMenuKeyDown}>
              <div className="lx-menu__head">Phạm vi</div>
              <button
                type="button"
                className={`lx-menu__item${scopeName === 'Toàn dataset' ? ' is-active' : ''}`}
                role="menuitem"
                onClick={() => {
                  onScopeChange?.('Toàn dataset');
                  setMenu(null);
                }}
              >
                <span className="lx-menu__t">Toàn dataset</span>
                {scopeName === 'Toàn dataset' && (
                  <svg
                    className="lx-menu__check"
                    viewBox="0 0 16 16"
                    role="img"
                    aria-label="Đang chọn"
                    style={{
                      width: 14,
                      height: 14,
                      stroke: 'currentColor',
                      fill: 'none',
                      strokeWidth: 2,
                    }}
                  >
                    <path
                      d="M3 8.5 6.5 12 13 4.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </button>
              {isTasksLoading && visibleTaskList.length === 0 ? (
                <div className="lx-menu__item" style={{ color: 'var(--ink-muted)' }}>
                  Đang tải danh sách Task…
                </div>
              ) : visibleTasksError && visibleTaskList.length === 0 ? (
                <div
                  className="lx-menu__item"
                  style={{
                    color: 'var(--danger)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    alignItems: 'flex-start',
                  }}
                >
                  <span>{visibleTasksError}</span>
                  <button
                    type="button"
                    className="lx-btn lx-btn--sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setTasksLoadedKey(null);
                      setTasksRetryNonce((n) => n + 1);
                    }}
                  >
                    Thử lại
                  </button>
                </div>
              ) : visibleTaskList.length === 0 ? (
                <div
                  className="lx-menu__item"
                  style={{ color: 'var(--ink-muted)', cursor: 'default' }}
                >
                  Chưa có Task trong Dataset này
                </div>
              ) : (
                visibleTaskList.map((task) => {
                  const taskLabel = `Task #${task.cvat_task_id}${task.name ? ` · ${task.name}` : ''}`;
                  const isTaskSelected =
                    scopeName === taskLabel || scopeName === `Task #${task.cvat_task_id}`;
                  return (
                    <button
                      key={task.cvat_task_id}
                      type="button"
                      className={`lx-menu__item${isTaskSelected ? ' is-active' : ''}`}
                      role="menuitem"
                      onClick={() => {
                        onScopeChange?.(taskLabel);
                        setMenu(null);
                      }}
                    >
                      <span className="lx-menu__t">{taskLabel}</span>
                      {isTaskSelected && (
                        <svg
                          className="lx-menu__check"
                          viewBox="0 0 16 16"
                          role="img"
                          aria-label="Đang chọn"
                          style={{
                            width: 14,
                            height: 14,
                            stroke: 'currentColor',
                            fill: 'none',
                            strokeWidth: 2,
                          }}
                        >
                          <path
                            d="M3 8.5 6.5 12 13 4.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </button>
                  );
                })
              )}
            </div>
          )}
        </div>

        {/* 5. Guideline (Static chip, read-only factual info) */}
        <button
          type="button"
          className="lx-chip lx-chip--static"
          ref={(el) => {
            triggerRefs.current['gl'] = el;
          }}
          onClick={() => {
            if (guidelineVersion !== '—') {
              setNotice({
                ownerKey: noticeOwnerKey,
                type: 'info',
                message: `Phiên bản Guideline: ${guidelineVersion} (chỉ đọc, cấu hình tại Models & Guidelines)`,
              });
            } else {
              setNotice({
                ownerKey: noticeOwnerKey,
                type: 'info',
                message: 'Dataset hiện tại chưa có thông tin Guideline',
              });
            }
          }}
        >
          <span className="lx-chip__k">Guideline</span>{' '}
          <span className="lx-chip__v">{guidelineVersion}</span>
        </button>

        {/* 6. Taxonomy (Static chip, read-only factual info) */}
        <button
          type="button"
          className="lx-chip lx-chip--static"
          ref={(el) => {
            triggerRefs.current['tx'] = el;
          }}
          onClick={() => {
            if (taxonomyVersion !== '—') {
              setNotice({
                ownerKey: noticeOwnerKey,
                type: 'info',
                message: `Phiên bản Taxonomy: ${taxonomyVersion} (chỉ đọc, cấu hình tại Models & Guidelines)`,
              });
            } else {
              setNotice({
                ownerKey: noticeOwnerKey,
                type: 'info',
                message: 'Dataset hiện tại chưa có thông tin Taxonomy',
              });
            }
          }}
        >
          <span className="lx-chip__k">Taxonomy</span>{' '}
          <span className="lx-chip__v">{taxonomyVersion}</span>
        </button>
      </div>

      {effectiveNotice && (
        <div
          style={{ padding: 'var(--space-2) var(--space-6)', background: 'var(--surface-sunken)' }}
          role="status"
        >
          {effectiveNotice.type === 'not-connected' ? (
            <NotConnectedNotice detail={effectiveNotice.message} />
          ) : (
            <div
              className="lx-callout"
              style={{
                margin: 0,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                <span className="lx-badge">Chỉ đọc</span>
                <span className="lx-callout__text">{effectiveNotice.message}</span>
              </div>
              <button
                type="button"
                className="lx-btn lx-btn--sm"
                onClick={() => setNotice(null)}
              >
                Đóng
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
