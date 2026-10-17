'use client';

export function ProgressBar({ label, value, active = false, paused = false, warning = false }: {
  label: string; value?: number; active?: boolean; paused?: boolean; warning?: boolean;
}) {
  const percent = value === undefined ? undefined : Math.max(0, Math.min(100, value));
  const classes = ['lx-progress', warning && 'lx-progress--warn',
    active && !paused && 'lx-progress--active', percent === undefined && 'lx-progress--indeterminate',
    paused && 'lx-progress--paused'].filter(Boolean).join(' ');
  return <div className={classes} role="progressbar" aria-label={label}
    aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}
    aria-valuetext={paused ? 'Chưa cập nhật được tiến độ' : percent === undefined ? 'Đang chờ xác định tiến độ' : `${percent}%`}>
    <i style={{ width: percent === undefined ? '35%' : `${percent}%` }} />
  </div>;
}
