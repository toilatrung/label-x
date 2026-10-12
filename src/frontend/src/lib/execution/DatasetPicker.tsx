'use client';

import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis } from '@/lib/auth/roles';

export function DatasetPicker({ onChange }: { onChange?: (datasetId: number | null) => void }) {
  const { session, datasetId, setDatasetId } = useAuth();
  const scoped = [...new Set(session?.roles.filter((r) => r.dataset_id !== null && canAccessAnalysis(r.role)).map((r) => r.dataset_id as number) ?? [])];
  const global = session?.roles.some((r) => r.dataset_id === null && (r.role === 'super_admin' || r.role === 'qc_admin')) ?? false;
  return <div className="lx-field">
    <label className="lx-label" htmlFor="analysis-dataset">Dataset</label>
    {global ? <input className="lx-input" id="analysis-dataset" type="number" min={1} value={datasetId ?? ''} onChange={(e) => { const nextId = e.target.value ? Number(e.target.value) : null; setDatasetId(nextId); onChange?.(nextId); }} placeholder="ID dataset" /> :
      <select className="lx-select" id="analysis-dataset" value={datasetId ?? ''} onChange={(e) => { const nextId = e.target.value ? Number(e.target.value) : null; setDatasetId(nextId); onChange?.(nextId); }}>
        <option value="">Chọn dataset</option>
        {scoped.map((id) => <option key={id} value={id}>Dataset #{id}</option>)}
      </select>}
  </div>;
}
