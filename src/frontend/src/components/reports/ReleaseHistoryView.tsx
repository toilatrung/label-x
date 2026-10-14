'use client';

import React, { useState } from 'react';
import { errorMessage } from '@/lib/api/errors';
import { useReleaseManifest, useReleases } from '@/lib/reports/queries';
import { formatDate, formatDateTime, type Release, type ReleaseManifest } from '@/lib/reports/api';

const DASH = <span className="lx-subtle">—</span>;

function releaseStatus(r: Release): { tone: string; label: string } {
  if (r.status === 'approved') return { tone: 'success', label: 'Released' };
  if (r.gate_status === 'failed') return { tone: 'danger', label: 'Blocked' };
  return { tone: 'warning', label: 'Chờ duyệt' };
}

function RetryRow({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="lx-card__body lx-row" role="alert">
      <span>{message}</span>
      <button type="button" className="lx-btn lx-btn--sm" onClick={onRetry}>Thử lại</button>
    </div>
  );
}

function downloadManifest(manifest: ReleaseManifest) {
  const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `release-${manifest.release_id}-manifest.json`;
  link.click();
  URL.revokeObjectURL(url);
}

function ManifestPanel({ release }: { release: Release | null }) {
  const manifest = useReleaseManifest(release?.id ?? null);
  const data = manifest.data;
  return (
    <section className="lx-card lx-side lx-side--wide" aria-label="Manifest">
      <div className="lx-card__head">
        <h2 className="lx-h2">{release ? `Manifest · ${release.version_tag}` : 'Manifest'}</h2>
        <button type="button" className="lx-iconbtn" disabled={!data} onClick={() => data && downloadManifest(data)}
          data-tip="Tải manifest (JSON)" aria-label="Tải manifest (JSON)">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v7M5 7l3 3 3-3M3 13h10" /></svg>
        </button>
      </div>
      {!release && <div className="lx-card__body lx-muted">Chưa có release để xem manifest.</div>}
      {manifest.isLoading && <div className="lx-card__body">Đang tải manifest…</div>}
      {manifest.isError && <RetryRow message={errorMessage(manifest.error)} onRetry={() => void manifest.refetch()} />}
      {data && (
        <div className="lx-card__body lx-stack">
          <dl className="lx-kv">
            <dt>Snapshot</dt><dd className="lx-mono">#{data.snapshot_id}</dd>
            <dt>Quality Control Run</dt><dd className="lx-mono">#QC-{data.run_id}</dd>
            <dt>Cấu hình kiểm tra</dt><dd className="lx-mono">#{data.config_version_id}</dd>
            <dt>Guideline</dt><dd>{data.guideline_version ?? DASH}</dd>
            <dt>Score version</dt><dd>{data.score_version ?? DASH}</dd>
            <dt>Quality Gate</dt><dd>{data.gate ? data.gate.status : DASH}</dd>
            <dt>Tạo lúc</dt><dd>{formatDateTime(data.generated_at) ?? DASH}</dd>
            <dt>Phê duyệt</dt><dd>{release?.approved_by ? `Người dùng #${release.approved_by} · ${formatDateTime(release.approved_at) ?? ''}` : DASH}</dd>
            <dt>Checksum</dt><dd className="lx-mono">{data.checksum}</dd>
            {data.artifacts.map((a) => (
              <React.Fragment key={a.name}><dt>{a.name}</dt><dd className="lx-mono">{a.sha256.slice(0, 12)}</dd></React.Fragment>
            ))}
          </dl>
        </div>
      )}
    </section>
  );
}

export function ReleaseHistoryBody() {
  const releases = useReleases();
  const rows = releases.data?.results ?? [];
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = rows.find((r) => r.id === selectedId) ?? rows[0] ?? null;
  return (
    <div className="lx-cols">
      <section className="lx-card lx-main" aria-label="Các lần phát hành">
        <div className="lx-card__head"><h2 className="lx-h2">Các lần phát hành</h2></div>
        {releases.isLoading && <div className="lx-card__body">Đang tải danh sách release…</div>}
        {releases.isError && <RetryRow message={errorMessage(releases.error)} onRetry={() => void releases.refetch()} />}
        {releases.data && (
          <div className="lx-scroll">
            <table className="lx-table lx-table--min-640">
              <thead><tr><th>Phiên bản</th><th>Quality Control Run</th><th className="r">Frame</th><th>Phê duyệt bởi</th><th>Ngày</th><th>Trạng thái</th></tr></thead>
              <tbody>
                {rows.map((r) => {
                  const s = releaseStatus(r);
                  return (
                    <tr key={r.id} aria-selected={selected?.id === r.id || undefined} tabIndex={0} onClick={() => setSelectedId(r.id)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedId(r.id); } }}>
                      <td className="lx-cell__main">{r.version_tag}</td>
                      <td className="lx-mono">#QC-{r.run_id}</td>
                      {/* Release (contract) không có số frame; xem ở Quality Report của run. */}
                      <td className="r">{DASH}</td>
                      <td className="lx-muted">{r.approved_by ? `Người dùng #${r.approved_by}` : DASH}</td>
                      <td className="lx-muted">{formatDate(r.approved_at ?? r.created_at) ?? DASH}</td>
                      <td><span className={`lx-badge lx-badge--${s.tone}`}>{s.label}</span></td>
                    </tr>
                  );
                })}
                {rows.length === 0 && <tr><td colSpan={6} className="lx-muted">Chưa có release nào trên server.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {releases.data?.next && <div className="lx-card__foot"><span>Đang hiện 50 release mới nhất.</span></div>}
      </section>

      <ManifestPanel release={selected} />
    </div>
  );
}
