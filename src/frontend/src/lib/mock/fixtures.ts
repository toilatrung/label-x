/**
 * Số liệu minh họa dùng chung cho các màn dựng theo thiết kế khi chưa có API (M-FE01).
 * Giữ nhất quán giữa mọi màn hình (bộ chuẩn trong skill labelx-design). Luôn hiển thị kèm SampleDataBadge.
 */
export const SAMPLE = {
  frames: 12500,
  coverage: { value: 92.4, threshold: 95 },
  candidates: 384,
  confirmedErrors: 126,
  rework: { total: 86, closed: 74, open: 12, closedRate: 86.0 },
  randomAudit: { sampled: 4, of: 100, rate: 4.0 },
  reviewerAgreement: 94.1,
} as const;

/** Định dạng số có dấu phân cách hàng nghìn; giá trị rỗng là dấu gạch dài. */
export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toLocaleString('en-US');
}

export function formatPercent(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${value.toFixed(1)}%`;
}
