import type { Run } from '@/lib/execution/api';

/** Quality Control Run mới nhất (id lớn nhất) của từng Snapshot; Snapshot chưa có run không có trong Map. */
export function latestRunBySnapshot(runs: Run[]): Map<number, Run> {
  const latest = new Map<number, Run>();
  for (const run of runs) {
    const current = latest.get(run.snapshot_id);
    if (!current || run.id > current.id) latest.set(run.snapshot_id, run);
  }
  return latest;
}
