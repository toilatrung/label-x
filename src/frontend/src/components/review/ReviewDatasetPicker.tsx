'use client';

import React from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessReview } from '@/lib/auth/roles';

export function ReviewDatasetPicker({ onChange }: { onChange?: () => void }) {
  const { session, datasetId, setDatasetId } = useAuth();

  const scoped = [
    ...new Set(
      session?.roles
        .filter((r) => r.dataset_id !== null && canAccessReview(r.role))
        .map((r) => r.dataset_id as number) ?? []
    ),
  ];

  const global =
    session?.roles.some(
      (r) => r.dataset_id === null && (r.role === 'super_admin' || r.role === 'qc_admin')
    ) ?? false;

  return (
    <div className="lx-field">
      <label htmlFor="review-dataset" className="lx-label">
        Bộ dữ liệu (Dataset)
      </label>
      {global ? (
        <input
          id="review-dataset"
          className="lx-input"
          type="number"
          min={1}
          value={datasetId ?? ''}
          onChange={(e) => {
            const val = e.target.value ? Number(e.target.value) : null;
            setDatasetId(val);
            onChange?.();
          }}
          placeholder="Nhập ID dataset"
        />
      ) : (
        <select
          id="review-dataset"
          className="lx-select"
          value={datasetId ?? ''}
          onChange={(e) => {
            const val = e.target.value ? Number(e.target.value) : null;
            setDatasetId(val);
            onChange?.();
          }}
        >
          <option value="">-- Chọn dataset --</option>
          {scoped.map((id) => (
            <option key={id} value={id}>
              Dataset #{id}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
