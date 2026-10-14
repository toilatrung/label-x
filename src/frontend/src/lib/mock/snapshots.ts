/**
 * Dữ liệu minh họa cho Snapshot, lấy từ docs/design/screens/Snapshot.dc.html.
 * Chỉ dùng cho các trường thiết kế chưa có API (revision và seed khi tạo Snapshot).
 * TODO(backend): GET /api/datasets/{id}/revisions/ (danh sách annotation revision), seed lấy mẫu và cấu hình kiểm tra gắn với Snapshot
 *   (trường seed, config_version_id, models trên Snapshot), GET /api/snapshots/{id}/runs/ (Quality Control Run đã chạy trên Snapshot).
 * Dữ liệu thật từ endpoint đã tồn tại luôn được ưu tiên; lỗi endpoint thật không bị che bằng fixture.
 */
export const SAMPLE_SNAPSHOT_FORM = {
  revisions: ['a91f3c · mới nhất (2026-10-04 06:41)', '7be204 · 2026-10-02 17:10'],
  seed: '20261004',
} as const;
