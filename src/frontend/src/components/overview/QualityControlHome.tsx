'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getDatasets, cursorFrom, type Dataset } from '@/lib/snapshots/api';
import { useAuth } from '@/lib/auth/auth-context';
import { errorMessage } from '@/lib/api/errors';
import { useQueryClient } from '@tanstack/react-query';
import { DatasetHomeRow } from './DatasetHomeRow';

interface QualityControlHomeProps {
  onDatasetSelect?: (dataset: Dataset) => void;
}

export function QualityControlHome({ onDatasetSelect }: QualityControlHomeProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { user, datasetId, setDatasetId, isLoading: isAuthLoading } = useAuth();
  const currentUserId = user?.id ?? null;

  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [nextCursor, setNextCursor] = useState<string | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanningSearch, setIsScanningSearch] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [paginationError, setPaginationError] = useState<string | null>(null);
  const [initialError, setInitialError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const [searchQuery, setSearchQuery] = useState('');

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
      setPaginationError(null);
      setInitialError(null);
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
        setDatasets([]);
        setNextCursor(undefined);
        setInitialError(errorMessage(err));
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

  const loadMore = useCallback(async (overrideCursor?: string) => {
    const targetCursor = overrideCursor || nextCursor;
    if (!targetCursor || isLoadingMore || isLoading || isScanningSearch || inFlightCursorRef.current) return;
    const gen = currentGen.current;

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
    const retryCursor = nextCursor || lastAttemptedCursorRef.current;
    if (retryCursor) {
      seenCursorsRef.current.delete(retryCursor);
      void loadMore(retryCursor);
    }
  }, [nextCursor, loadMore]);

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

  /** Nút hành động cuối dòng: chưa có run → tạo snapshot đầu tiên; có run → Quality Summary. */
  const handleOpenDataset = (ds: Dataset, href: string) => {
    setDatasetId(ds.id);
    onDatasetSelect?.(ds);
    router.push(href);
  };

  const handleRetryInitial = () => {
    currentGen.current++;
    inFlightCursorRef.current = null;
    seenCursorsRef.current = new Set();
    setIsLoading(true);
    setPaginationError(null);
    setDatasets([]);
    setNextCursor(undefined);
    setIsScanningSearch(false);
    setIsLoadingMore(false);
    setRefreshTrigger((prev) => prev + 1);
  };

  const handleSync = () => {
    // Làm mới cả danh sách lẫn số liệu từng dòng (task, run, gate).
    void queryClient.invalidateQueries({ queryKey: ['overview'] });
    handleRetryInitial();
  };

  const isRealDataActive = datasets.length > 0;
  const isEmpty = !isLoading && !initialError && datasets.length === 0;

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
          <span className="lx-hint">
            {/* TODO(backend): thời điểm đồng bộ CVAT gần nhất chưa có trong API. */}
            Đồng bộ CVAT —
          </span>
          <button type="button" className="lx-btn" onClick={handleSync}>
            Đồng bộ lại
          </button>
        </div>
      </div>

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

        {isLoading ? (
          <div className="lx-state--card-muted">
            Đang tải danh sách Dataset...
          </div>
        ) : null}

        {initialError && !isLoading && (
          <div className="lx-state--card" role="alert">
            <div className="lx-text-danger lx-mb-3">Không thể tải danh sách Dataset: {initialError}</div>
            <button type="button" className="lx-btn lx-btn--sm" onClick={handleRetryInitial}>Thử lại</button>
          </div>
        )}

        {/* Real datasets table when connected */}
        {isRealDataActive && !isLoading && (
          filteredDatasets.length === 0 ? (
            paginationError ? (
              <div className="lx-state--card">
                <div className="lx-text-danger lx-mb-3">{paginationError}</div>
                <button
                  type="button"
                  className="lx-btn lx-btn--sm"
                  onClick={handleRetryPagination}
                >
                  Thử lại tải trang
                </button>
              </div>
            ) : isScanningSearch ? (
              <div className="lx-state--card-muted">
                Đang tìm kiếm thêm trên các trang tiếp theo…
              </div>
            ) : (
              <div className="lx-state--card-muted">
                <div>Không tìm thấy Dataset phù hợp với từ khóa &ldquo;{searchQuery}&rdquo;.</div>
                <button
                  type="button"
                  className="lx-btn lx-btn--sm lx-mt-3"
                  onClick={() => setSearchQuery('')}
                >
                  Xóa bộ lọc tìm kiếm
                </button>
              </div>
            )
          ) : (
            <div className="lx-scroll">
              <table className="lx-table lx-table--min-1040">
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
                  {filteredDatasets.map((ds) => (
                    <DatasetHomeRow
                      key={ds.id}
                      dataset={ds}
                      isSelected={ds.id === datasetId}
                      onSelect={handleSelectDataset}
                      onOpen={handleOpenDataset}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}

        {isEmpty && (
          <div className="lx-state--card-muted">
            Chưa có Dataset nào trong phạm vi quyền của bạn. Dataset xuất hiện ở đây sau khi CVAT Project được đồng bộ.
          </div>
        )}

        {/* Pagination error and working retry */}
        {paginationError && filteredDatasets.length > 0 && (
          <div className="lx-pagination-retry">
            <span className="lx-text-danger lx-mr-3">{paginationError}</span>
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
          <div className="lx-pagination-more">
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
