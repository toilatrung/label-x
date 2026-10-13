/** Định dạng hiển thị dùng chung theo thiết kế (số có dấu phân cách hàng nghìn, thời gian, mã, revision). */

export function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : value.toLocaleString('en-US');
}

/** ISO 8601 → `YYYY-MM-DD HH:mm` theo giờ máy người xem; giá trị rỗng là `—`, không phải ngày thì giữ nguyên. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Revision hiển thị 6 ký tự đầu (bỏ tiền tố thuật toán như `sha256:`); bản đầy đủ đặt ở `title`. */
export function shortRevision(hash: string | null | undefined): string {
  if (!hash) return '—';
  return hash.replace(/^[a-z0-9-]+:/i, '').slice(0, 6);
}

/** Mã Snapshot đệm 3 chữ số: 14 → `SNP-014`. */
export function snapshotCode(id: number): string {
  return `SNP-${String(id).padStart(3, '0')}`;
}
