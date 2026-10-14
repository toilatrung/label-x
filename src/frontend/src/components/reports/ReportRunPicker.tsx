'use client';

import React from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth/auth-context';
import { errorMessage } from '@/lib/api/errors';
import { DatasetPicker } from '@/lib/execution/DatasetPicker';
import { listRuns, runStatusLabel } from '@/lib/execution/api';

/** Run đang xem lấy từ `?run=` (cùng quy ước với Execution History). */
export function useSelectedRunId(): number | null {
  const params = useSearchParams();
  const value = Number(params.get('run'));
  return Number.isInteger(value) && value > 0 ? value : null;
}

/** Chọn Dataset rồi Quality Control Run; ghi lựa chọn vào `?run=` để header và body đọc chung. */
export function ReportRunPicker() {
  const router = useRouter();
  const pathname = usePathname();
  const { session, datasetId } = useAuth();
  const runId = useSelectedRunId();
  const runs = useQuery({
    queryKey: ['report-runs', session?.user.id, datasetId],
    queryFn: ({ signal }) => listRuns(datasetId!, null, signal),
    enabled: datasetId !== null,
    retry: false,
  });
  const select = (id: number | null) => router.replace(id ? `${pathname}?run=${id}` : pathname);
  const options = runs.data?.results ?? [];
  const known = runId === null || options.some((r) => r.id === runId);
  return (
    <div className="lx-grid lx-grid--2">
      <DatasetPicker onChange={() => select(null)} />
      <div className="lx-field">
        <label className="lx-label" htmlFor="report-run">Quality Control Run</label>
        <select id="report-run" className="lx-select" value={runId ?? ''} disabled={datasetId === null && runId === null}
          onChange={(e) => select(e.target.value ? Number(e.target.value) : null)}>
          <option value="">Chọn Quality Control Run</option>
          {!known && runId !== null && <option value={runId}>#QC-{runId}</option>}
          {options.map((r) => <option key={r.id} value={r.id}>#QC-{r.id} · {runStatusLabel[r.status]}</option>)}
        </select>
        {runs.isLoading && <span className="lx-hint">Đang tải danh sách run…</span>}
        {runs.isError && (
          <span className="lx-hint" role="alert">
            {errorMessage(runs.error)} <button type="button" className="lx-btn lx-btn--sm" onClick={() => void runs.refetch()}>Thử lại</button>
          </span>
        )}
        {runs.data && options.length === 0 && <span className="lx-hint">Chưa có Quality Control Run trong Dataset này.</span>}
      </div>
    </div>
  );
}
