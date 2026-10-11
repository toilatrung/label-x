'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getDatasets, cursorFrom, type Dataset } from '@/lib/snapshots/api';
import { useAuth } from '@/lib/auth/auth-context';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { ApiRequestError, errorMessage } from '@/lib/api/errors';

interface QualityControlHomeProps {
  onDatasetSelect?: (dataset: Dataset) => void;
}

export function QualityControlHome({ onDatasetSelect }: QualityControlHomeProps) {
  const router = useRouter();
  const { user, datasetId, setDatasetId, isLoading: isAuthLoading } = useAuth();
  const currentUserId = user?.id ?? null;

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [nextCursor, setNextCursor] = useState<string | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanningSearch, setIsScanningSearch] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<{ message: string; isForbidden: boolean } | null>(null);
  const [paginationError, setPaginationError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [searchQuery, setSearchQuery] = useState('');
  const [syncNotice, setSyncNotice] = useState<string | null>(null);

  const currentGen = useRef(0);
  const inFlightCursorRef = useRef<string | null>(null);
  const seenCursorsRef = useRef<Set<string>>(new Set());
  const lastAttemptedCursorRef = useRef<string | null>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // Initial load with generation guard and auth scope reset
  useEffect(() => {
    if (isAuthLoading) return;

    const gen = ++currentGen.current;
    inFlightCursorRef.current = 'page1';
    seenCursorsRef.current = new Set();

    Promise.resolve().then(() => {
      if (!isMountedRef.current || gen !== currentGen.current) return;
      setIsLoading(true);
      setError(null);
      setPaginationError(null);
      setDatasets([]);
      setNextCursor(undefined);
      setIsScanningSearch(false);
      setIsLoadingMore(false);
    });

    getDatasets()
      .then((page) => {
        if (inFlightCursorRef.current === 'page1') {
          inFlightCursorRef.current = null;
        }
        if (!isMountedRef.current || gen !== currentGen.current) return;
        setDatasets(page.results ?? []);
        setNextCursor(cursorFrom(page.next));
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (inFlightCursorRef.current === 'page1') {
          inFlightCursorRef.current = null;
        }
        if (!isMountedRef.current || gen !== currentGen.current) return;
        const isForbidden = err instanceof ApiRequestError && err.status === 403;
        setError({
          message: isForbidden
            ? 'Bạn không có quyền truy cập danh sách Dataset.'
            : errorMessage(err) || 'Không thể tải danh sách Dataset từ server.',
          isForbidden,
        });
        setDatasets([]);
        setNextCursor(undefined);
        setIsLoading(false);
      });
  }, [refreshTrigger, currentUserId, isAuthLoading]);

  // Drive search coverage from current query / current cursor / loading state with bounded single-flight requests
  useEffect(() => {
    const query = searchQuery.trim();
    if (!query) {
      Promise.resolve().then(() => {
        if (isMountedRef.current) {
          setIsScanningSearch((prev) => (prev ? false : prev));
        }
      });
      return;
    }

    if (isLoading || !nextCursor || inFlightCursorRef.current) {
      return;
    }

    const gen = currentGen.current;
    const targetCursor = nextCursor;

    if (seenCursorsRef.current.has(targetCursor)) {
      lastAttemptedCursorRef.current = targetCursor;
      setPaginationError('Phát hiện vòng lặp phân trang từ server khi tìm kiếm.');
      setIsScanningSearch(false);
      return;
    }

    inFlightCursorRef.current = targetCursor;
    setIsScanningSearch(true);
    setPaginationError(null);

    getDatasets(targetCursor)
      .then((page) => {
        if (inFlightCursorRef.current === targetCursor) {
          inFlightCursorRef.current = null;
        }
        if (!isMountedRef.current || gen !== currentGen.current) return;
        seenCursorsRef.current.add(targetCursor);
        const newResults = page.results ?? [];
        setDatasets((prev) => {
          const existingIds = new Set(prev.map((d) => d.id));
          const newItems = newResults.filter((d) => !existingIds.has(d.id));
          return [...prev, ...newItems];
        });
        const next = cursorFrom(page.next);
        if (next && (seenCursorsRef.current.has(next) || next === targetCursor)) {
          lastAttemptedCursorRef.current = next;
          setPaginationError('Phát hiện vòng lặp phân trang từ server khi tìm kiếm.');
          setNextCursor(undefined);
          setIsScanningSearch(false);
          return;
        }
        setNextCursor(next);
        setIsScanningSearch(false);
      })
      .catch((err: unknown) => {
        if (inFlightCursorRef.current === targetCursor) {
          inFlightCursorRef.current = null;
        }
        if (!isMountedRef.current || gen !== currentGen.current) return;
        lastAttemptedCursorRef.current = targetCursor;
        setPaginationError(`Lỗi khi quét các trang tiếp theo: ${errorMessage(err)}`);
        setIsScanningSearch(false);
      });
  }, [searchQuery, nextCursor, isLoading]);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
  };

  const loadMore = useCallback(async () => {
    if (!nextCursor || isLoadingMore || isLoading || isScanningSearch || inFlightCursorRef.current) return;
    const gen = currentGen.current;
    const targetCursor = nextCursor;

    if (seenCursorsRef.current.has(targetCursor)) {
      setPaginationError('Phát hiện vòng lặp phân trang từ server.');
      return;
    }

    inFlightCursorRef.current = targetCursor;
    setIsLoadingMore(true);
    setPaginationError(null);

    try {
      const page = await getDatasets(targetCursor);
      if (!isMountedRef.current || gen !== currentGen.current) return;

      seenCursorsRef.current.add(targetCursor);
      setDatasets((prev) => {
        const existingIds = new Set(prev.map((d) => d.id));
        const newItems = (page.results ?? []).filter((d) => !existingIds.has(d.id));
        return [...prev, ...newItems];
      });
      const next = cursorFrom(page.next);
      if (next && (seenCursorsRef.current.has(next) || next === targetCursor)) {
        lastAttemptedCursorRef.current = targetCursor;
        setPaginationError('Phát hiện vòng lặp phân trang từ server.');
        setNextCursor(undefined);
        return;
      }
      setNextCursor(next);
    } catch (err: unknown) {
      if (!isMountedRef.current || gen !== currentGen.current) return;
      lastAttemptedCursorRef.current = targetCursor;
      setPaginationError(`Không thể tải thêm trang: ${errorMessage(err)}`);
    } finally {
      if (gen === currentGen.current) {
        inFlightCursorRef.current = null;
        if (isMountedRef.current) {
          setIsLoadingMore(false);
        }
      }
    }
  }, [nextCursor, isLoadingMore, isLoading, isScanningSearch]);

  const handleRetryPagination = useCallback(() => {
    setPaginationError(null);
    seenCursorsRef.current = new Set();
    const retryCursor = nextCursor || lastAttemptedCursorRef.current;
    if (retryCursor) {
      setNextCursor(retryCursor);
    }
  }, [nextCursor]);

  const filteredDatasets = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return datasets;
    return datasets.filter((d) => {
      const matchName = d.name.toLowerCase().includes(q);
      const matchProject = `cvat project #${d.cvat_project_id}`.toLowerCase().includes(q) ||
        String(d.cvat_project_id).includes(q);
      const matchTaxonomy = d.taxonomy_version ? d.taxonomy_version.toLowerCase().includes(q) : false;
      const matchGuideline = d.guideline_version ? d.guideline_version.toLowerCase().includes(q) : false;
      return matchName || matchProject || matchTaxonomy || matchGuideline;
    });
  }, [datasets, searchQuery]);

  const handleSelectDataset = (ds: Dataset) => {
    setDatasetId(ds.id);
    onDatasetSelect?.(ds);
  };

  const handleSelectAndOpenSummary = (ds: Dataset) => {
    setDatasetId(ds.id);
    onDatasetSelect?.(ds);
    router.push('/?view=summary');
  };

  const handleSync = () => {
    setSyncNotice('Đồng bộ danh sách Dataset từ CVAT qua Webhook/Sync worker chưa được kích hoạt');
  };

  const handleRetryInitial = () => {
    currentGen.current++;
    inFlightCursorRef.current = null;
    seenCursorsRef.current = new Set();
    setIsLoading(true);
    setError(null);
    setPaginationError(null);
    setDatasets([]);
    setNextCursor(undefined);
    setIsScanningSearch(false);
    setIsLoadingMore(false);
    setRefreshTrigger((prev) => prev + 1);
  };

  return (
    <>
      {/* Header */}
      <div className="lx-head">
        <div className="lx-head__text">
          <h1 className="lx-h1">Quality Control Home</h1>
          <p className="lx-lead">
            Chọn một Dataset để đặt ngữ cảnh làm việc chung cho toàn bộ module. Mọi màn hình, Quality Control Run và nhật ký kiểm toán đều gắn với Dataset và phạm vi đã chọn.
          </p>
        </div>
        <div className="lx-actions">
          <span className="lx-hint">Đồng bộ CVAT —</span>
          <button type="button" className="lx-btn" onClick={handleSync}>
            Đồng bộ lại
          </button>
        </div>
      </div>

      {syncNotice && (
        <div style={{ marginBottom: 'var(--space-4)' }} role="status" aria-live="polite">
          <NotConnectedNotice detail={syncNotice} />
        </div>
      )}

      {/* Main card */}
      <section className="lx-card">
        {/* Toolbar */}
        <div className="lx-toolbar">
          <label className="lx-search">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <circle cx="7" cy="7" r="4.5" />
              <path d="m10.5 10.5 3 3" />
            </svg>
            <input
              type="search"
              aria-label="Tìm dataset"
              placeholder="Tìm dataset, version, CVAT project…"
              value={searchQuery}
              onChange={handleSearchChange}
            />
          </label>
          <span className="lx-hint">
            {isScanningSearch
              ? `Đang tìm kiếm… (${filteredDatasets.length} / ${datasets.length} dataset)`
              : `${filteredDatasets.length} / ${datasets.length} dataset`}
          </span>
        </div>

        {/* Region-level notice for unaggregated fields in table, preserving canonical table cell density */}
        <div style={{ padding: '0 var(--space-4) var(--space-2)' }}>
          <NotConnectedNotice detail="Các trường Task/Job, Frame, QC Run và Quality Gate chưa có API tổng hợp" />
        </div>

        {/* Table content / Loading / Error states */}
        {isLoading ? (
          <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--ink-muted)' }}>
            Đang tải danh sách Dataset từ server...
          </div>
        ) : error ? (
          <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--ink)' }}>
            <div style={{ color: 'var(--danger)', marginBottom: 'var(--space-3)' }}>{error.message}</div>
            {!error.isForbidden && (
              <button type="button" className="lx-btn lx-btn--sm" onClick={handleRetryInitial}>
                Thử lại
              </button>
            )}
          </div>
        ) : datasets.length === 0 ? (
          <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--ink-muted)' }}>
            Chưa có Dataset nào được phân quyền cho tài khoản này.
          </div>
        ) : filteredDatasets.length === 0 ? (
          paginationError ? (
            <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--ink)' }}>
              <div style={{ color: 'var(--danger)', marginBottom: 'var(--space-3)' }}>{paginationError}</div>
              <button
                type="button"
                className="lx-btn lx-btn--sm"
                onClick={handleRetryPagination}
              >
                Thử lại tải trang
              </button>
            </div>
          ) : isScanningSearch ? (
            <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--ink-muted)' }}>
              Đang tìm kiếm thêm trên các trang tiếp theo…
            </div>
          ) : (
            <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--ink-muted)' }}>
              <div>Không tìm thấy Dataset phù hợp với từ khóa &ldquo;{searchQuery}&rdquo;.</div>
              <button
                type="button"
                className="lx-btn lx-btn--sm"
                style={{ marginTop: 'var(--space-3)' }}
                onClick={() => setSearchQuery('')}
              >
                Xóa bộ lọc tìm kiếm
              </button>
            </div>
          )
        ) : (
          <div className="lx-scroll">
            <table className="lx-table" style={{ minWidth: '1040px' }}>
              <thead>
                <tr>
                  <th>Dataset</th>
                  <th className="r">Task / Job</th>
                  <th className="r">Frame</th>
                  <th>Quality Control Run gần nhất</th>
                  <th className="r">Coverage</th>
                  <th className="r">Issue đang mở</th>
                  <th>Gate</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filteredDatasets.map((ds) => {
                  const isSelected = ds.id === datasetId;
                  return (
                    <tr
                      key={ds.id}
                      aria-selected={isSelected ? 'true' : undefined}
                      onClick={() => handleSelectDataset(ds)}
                      style={{ cursor: 'pointer' }}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        // Separate row activation from child button click
                        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                          e.preventDefault();
                          handleSelectDataset(ds);
                        }
                      }}
                    >
                      <td>
                        <div className="lx-cell__main">
                          {ds.name} <span className="lx-tag" title="API chưa cung cấp trường dataset version">—</span>
                          {isSelected && <span className="lx-hint"> · Đang chọn</span>}
                        </div>
                        <div className="lx-cell__sub">CVAT project #{ds.cvat_project_id}</div>
                      </td>
                      <td className="r">—</td>
                      <td className="r">—</td>
                      <td>—</td>
                      <td className="r">—</td>
                      <td className="r">—</td>
                      <td>—</td>
                      <td className="r">
                        <button
                          type="button"
                          className="lx-iconbtn"
                          data-tip="Tiếp tục làm việc với Dataset này"
                          aria-label="Tiếp tục làm việc với Dataset này"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleSelectAndOpenSummary(ds);
                          }}
                        >
                          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" style={{ width: 16, height: 16 }}>
                            <path d="M3 8h10M9 4l4 4-4 4" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination error and working retry */}
        {paginationError && filteredDatasets.length > 0 && (
          <div style={{ padding: 'var(--space-3)', textAlign: 'center', background: 'var(--surface-sunken)', borderTop: '1px solid var(--border)' }}>
            <span style={{ color: 'var(--danger)', marginRight: 'var(--space-3)' }}>{paginationError}</span>
            <button
              type="button"
              className="lx-btn lx-btn--sm"
              onClick={handleRetryPagination}
              disabled={isLoadingMore}
            >
              Thử lại tải trang
            </button>
          </div>
        )}

        {/* Pagination if more available */}
        {nextCursor && !isLoading && !paginationError && (
          <div style={{ padding: 'var(--space-3)', textAlign: 'center', borderTop: '1px solid var(--border)' }}>
            <button
              type="button"
              className="lx-btn lx-btn--sm"
              onClick={() => void loadMore()}
              disabled={isLoadingMore || isScanningSearch}
            >
              {isLoadingMore || isScanningSearch ? 'Đang tải thêm…' : 'Tải thêm dataset'}
            </button>
          </div>
        )}

        {/* Table footer */}
        <div className="lx-table__foot">
          <b>Dataset = CVAT Project + Version.</b> Dataset được đồng bộ từ CVAT, gồm cấu trúc Project, Task, Job và Frame. Quality Control chỉ đọc cấu trúc này; mọi thao tác tạo, sửa hoặc xoá annotation đều thực hiện trực tiếp trên CVAT.
        </div>
      </section>
    </>
  );
}
