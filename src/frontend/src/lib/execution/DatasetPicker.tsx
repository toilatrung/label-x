'use client';

import React from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis } from '@/lib/auth/roles';
import { useDatasets } from '@/lib/snapshots/queries';

/** Chọn Dataset: người dùng theo Dataset thấy các Dataset được cấp; Super Admin và Quality Control Admin thấy mọi Dataset từ server. */
export function DatasetPicker({ onChange }: { onChange?: (datasetId: number | null) => void }) {
  const { session, datasetId, setDatasetId } = useAuth();
  const datasets = useDatasets(session?.user.id);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = datasets;
  React.useEffect(() => { if (hasNextPage && !isFetchingNextPage) void fetchNextPage(); }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  const known = datasets.data?.pages.flatMap((page) => page.results ?? []) ?? [];
  const scoped = [...new Set(session?.roles.filter((r) => r.dataset_id !== null && canAccessAnalysis(r.role)).map((r) => r.dataset_id as number) ?? [])];
  const global = session?.roles.some((r) => r.dataset_id === null && (r.role === 'super_admin' || r.role === 'qc_admin')) ?? false;
  const ids = global ? known.map((item) => item.id) : scoped;
  const options = datasetId !== null && !ids.includes(datasetId) ? [...ids, datasetId] : ids;
  const label = (id: number) => {
    const item = known.find((entry) => entry.id === id);
    return item ? `${item.name} · project #${item.cvat_project_id}` : `Dataset #${id}`;
  };
  return <div className="lx-field">
    <label className="lx-label" htmlFor="analysis-dataset">Dataset</label>
    <select className="lx-select" id="analysis-dataset" value={datasetId ?? ''} onChange={(e) => { const nextId = e.target.value ? Number(e.target.value) : null; setDatasetId(nextId); onChange?.(nextId); }}>
      <option value="">Chọn Dataset</option>
      {options.map((id) => <option key={id} value={id}>{label(id)}</option>)}
    </select>
    {global && datasets.isError && <span className="lx-hint" role="status">Không tải được danh sách Dataset từ server.</span>}
  </div>;
}
