'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getDatasets, cursorFrom, type Dataset } from '@/lib/snapshots/api';
import { useAuth } from '@/lib/auth/auth-context';
import { errorMessage } from '@/lib/api/errors';
import { HOME_DATASETS, type HomeDatasetRow } from '@/lib/overview/home-data';

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
  const [paginationError, setPaginationError] = useState<string | null>(null);
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
      .catch(() => {
        if (inFlightCursorRef.current === 'page1') {
          inFlightCursorRef.current = null;
        }
        if (!isMountedRef.current || gen !== currentGen.current) return;
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

  const filteredProductDatasets = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return HOME_DATASETS;
    return HOME_DATASETS.filter((d) => {
      const matchName = d.name.toLowerCase().includes(q);
      const matchVersion = d.version ? d.version.toLowerCase().includes(q) : false;
      const matchProject = d.cvatProjectId ? `cvat project #${d.cvatProjectId}`.toLowerCase().includes(q) : false;
      return matchName || matchVersion || matchProject;
    });
  }, [searchQuery]);

  const handleSelectDataset = (ds: Dataset) => {
    setDatasetId(ds.id);
    onDatasetSelect?.(ds);
  };

  const handleSelectAndOpenSummary = (ds: Dataset) => {
    setDatasetId(ds.id);
    onDatasetSelect?.(ds);
    router.push('/?view=summary');
  };

  const selectProductDataset = (row: HomeDatasetRow) => {
    const dataset: Dataset = {
      id: row.id,
      name: row.name,
      cvat_project_id: row.cvatProjectId ?? 0,
    };
    setDatasetId(dataset.id);
    onDatasetSelect?.(dataset);
    router.push(row.actionHref);
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

  const handleSync = handleRetryInitial;

  // F-5: Helper to render non-empty version tag, never rendering an empty "—" chip
  const renderVersionTag = (version?: string | null) => {
    if (!version || version.trim() === '' || version.trim() === '—') return null;
    return <span className="lx-tag">{version}</span>;
  };

  const isRealDataActive = datasets.length > 0;

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
            {isRealDataActive ? 'Đồng bộ CVAT —' : 'Đồng bộ CVAT 2 phút trước'}
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
            {isRealDataActive ? (
              isScanningSearch
                ? `Đang tìm kiếm… (${filteredDatasets.length} / ${datasets.length} dataset)`
                : `${filteredDatasets.length} / ${datasets.length} dataset`
            ) : (
              `${filteredProductDatasets.length} / ${HOME_DATASETS.length} dataset`
            )}
          </span>
        </div>

        {/* Keep the initial API refresh localized; canonical product data remains available afterwards. */}
        {isLoading ? (
          <div className="lx-state--card-muted">
            Đang tải danh sách Dataset...
          </div>
        ) : null}

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
                  {filteredDatasets.map((ds, idx) => {
                    const isSelected = ds.id === datasetId;
                    const product = HOME_DATASETS.find(row => row.id === ds.id)
                      ?? HOME_DATASETS[idx % HOME_DATASETS.length];
                    return (
                      <tr
                        key={ds.id}
                        aria-selected={isSelected ? 'true' : undefined}
                        onClick={() => handleSelectDataset(ds)}
                        className="lx-tr--clickable"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                            e.preventDefault();
                            handleSelectDataset(ds);
                          }
                        }}
                      >
                        <td>
                          <div className="lx-cell__main">
                            {ds.name}
                            {isSelected && <span className="lx-hint"> · Đang chọn</span>}
                          </div>
                          <div className="lx-cell__sub">CVAT project #{ds.cvat_project_id}</div>
                        </td>
                        <td className="r">{product.tasksJobs}</td>
                        <td className="r">{product.frames}</td>
                        <td>
                          {product.qcRunStatus ? (
                            <>
                              <span className="lx-mono">{product.qcRun}</span>{' '}
                              <span className={`lx-badge${product.qcRunTone ? ` lx-badge--${product.qcRunTone}` : ''}`}>
                                {product.qcRunStatus}
                              </span>
                              {product.qcRunTime && <div className="lx-cell__sub">{product.qcRunTime}</div>}
                            </>
                          ) : (
                            <span className="lx-subtle">{product.qcRun}</span>
                          )}
                        </td>
                        <td className="r">{product.coverage}</td>
                        <td className="r">{product.openIssues}</td>
                        <td>
                          <span className={`lx-badge${product.gateTone ? ` lx-badge--${product.gateTone}` : ''}`}>
                            {product.gate}
                          </span>
                        </td>
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
                            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="lx-ico-16">
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
          )
        )}

        {/* Canonical product data remains available when the live API has no rows. */}
        {!isRealDataActive && !isLoading && (
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
                {filteredProductDatasets.map((ds) => {
                  const isSelected = ds.id === datasetId;
                  return (
                    <tr
                      key={ds.id}
                      aria-selected={isSelected ? 'true' : undefined}
                      className="lx-tr--clickable"
                      tabIndex={0}
                      onClick={() => selectProductDataset(ds)}
                      onKeyDown={(e) => {
                        if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) {
                          e.preventDefault();
                          selectProductDataset(ds);
                        }
                      }}
                    >
                      <td>
                        <div className="lx-cell__main">
                          {ds.name} {renderVersionTag(ds.version)}
                          {isSelected && <span className="lx-hint"> · Đang chọn</span>}
                        </div>
                        <div className="lx-cell__sub">
                          {ds.subLabel || (ds.cvatProjectId ? `CVAT project #${ds.cvatProjectId}` : '')}
                        </div>
                      </td>
                      <td className="r">{ds.tasksJobs}</td>
                      <td className="r">{ds.frames}</td>
                      <td>
                        {ds.qcRunStatus ? (
                          <>
                            <span className="lx-mono">{ds.qcRun}</span>{' '}
                            <span className={`lx-badge${ds.qcRunTone ? ` lx-badge--${ds.qcRunTone}` : ''}`}>
                              {ds.qcRunStatus}
                            </span>
                            {ds.qcRunTime && <div className="lx-cell__sub">{ds.qcRunTime}</div>}
                          </>
                        ) : (
                          <span className="lx-subtle">{ds.qcRun}</span>
                        )}
                      </td>
                      <td className="r">{ds.coverage}</td>
                      <td className="r">{ds.openIssues}</td>
                      <td>
                        <span className={`lx-badge${ds.gateTone ? ` lx-badge--${ds.gateTone}` : ''}`}>
                          {ds.gate}
                        </span>
                      </td>
                      <td className="r">
                        <button
                          type="button"
                          className="lx-iconbtn"
                          data-tip={ds.actionTip}
                          aria-label={ds.actionTip}
                          onClick={(e) => {
                            e.stopPropagation();
                            selectProductDataset(ds);
                          }}
                        >
                          {ds.actionHref.includes('releases') ? (
                            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="lx-ico-16">
                              <circle cx="8" cy="8" r="5.5" />
                              <path d="M8 5v3.5l2 1.5" />
                            </svg>
                          ) : ds.actionHref === '/analysis' ? (
                            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="lx-ico-16">
                              <path d="M8 3v10M3 8h10" />
                            </svg>
                          ) : (
                            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true" className="lx-ico-16">
                              <path d="M3 8h10M9 4l4 4-4 4" />
                            </svg>
                          )}
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
