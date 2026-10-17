import React from 'react';

const DASH = <span className="lx-subtle">—</span>;

/**
 * Khung chi tiết phân xử theo Escalations.dc.html khi chưa chọn issue. Không có dữ liệu giả: mọi giá trị là "—",
 * điều khiển bị khoá; tab Adjudication dùng dữ liệu thật (API T-038/T-039) nên chỉ hiện nội dung thật sau khi chọn issue.
 */
export function AdjudicationEmptyDetail() {
  return (
    <section className="lx-card" aria-label="Chi tiết phân xử">
      <div className="lx-card__head"><h2 className="lx-h2">Chi tiết phân xử</h2></div>
      <div className="lx-card__body lx-stack">
        <p className="lx-muted lx-m-0">Chọn một issue ở danh sách bên trái để xem bằng chứng và phân xử.</p>
        <div className="lx-grid lx-grid--3">
          <div className="lx-stack lx-stack--tight"><span className="lx-label">Quyết định của reviewer</span>{DASH}</div>
          <div className="lx-stack lx-stack--tight"><span className="lx-label">Bằng chứng</span>{DASH}</div>
          <div className="lx-stack lx-stack--tight"><span className="lx-label">Hướng dẫn liên quan</span>{DASH}</div>
        </div>
        <div className="lx-field"><span className="lx-label">Kết luận phân xử</span>
          <div className="lx-choices">
            {['Xác nhận lỗi', 'Bác bỏ', 'Guideline còn thiếu'].map((label) => (
              <label key={label} className="lx-choice"><input type="radio" name="empty-adjudication" disabled /><span>{label}</span></label>
            ))}
          </div>
        </div>
        <div className="lx-grid lx-grid--3">
          <div className="lx-field"><label className="lx-label" htmlFor="empty-rule">Quy tắc áp dụng</label><select id="empty-rule" className="lx-select" disabled><option>—</option></select></div>
          <div className="lx-field"><label className="lx-label" htmlFor="empty-label">Nhãn đúng</label><select id="empty-label" className="lx-select" disabled><option>—</option></select></div>
          <div className="lx-field"><label className="lx-label" htmlFor="empty-after">Sau khi phân xử</label><select id="empty-after" className="lx-select" disabled><option>—</option></select></div>
        </div>
        <div className="lx-field"><label className="lx-label" htmlFor="empty-reason">Lý do phân xử</label><textarea id="empty-reason" className="lx-textarea" disabled placeholder="Nêu căn cứ để các case tương tự có thể tham chiếu." /></div>
        <div className="lx-actions lx-actions--end">
          <button type="button" className="lx-btn" disabled>Tạo Guideline Gap</button>
          <button type="button" className="lx-btn lx-btn--primary" disabled>Lưu phân xử</button>
        </div>
      </div>
    </section>
  );
}
