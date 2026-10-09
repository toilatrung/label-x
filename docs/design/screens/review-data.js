/* Shared sample data for the design canvas. No backend writes. */
window.LabelXReview = {
  frames: [
    { name: 'Ảnh 001', id: 'BDD100K-0001234', frame: '001234', alert: 'Thiếu nhãn', priority: 'Cao', scene: 'Đường phố', time: '10 thg 6, 2024 10:24', image: 'assets/frame-001.png' },
    { name: 'Ảnh 002', id: 'BDD100K-0005678', frame: '005678', alert: 'Hộp lệch', priority: 'Trung bình', scene: 'Người đi bộ', time: '10 thg 6, 2024 09:17', image: 'assets/frame-002.png' },
    { name: 'Ảnh 003', id: 'BDD100K-0009012', frame: '009012', alert: 'Nhãn trùng', priority: 'Trung bình', scene: 'Biển báo', time: '10 thg 6, 2024 08:03', image: 'assets/frame-003.png' }
  ],
  readFilters() {
    try { return JSON.parse(sessionStorage.getItem('labelx-design-filters')) || {}; }
    catch { return {}; }
  },
  saveFilters(filters) {
    try { sessionStorage.setItem('labelx-design-filters', JSON.stringify(filters)); }
    catch { /* The preview also works when storage is unavailable. */ }
  }
};
