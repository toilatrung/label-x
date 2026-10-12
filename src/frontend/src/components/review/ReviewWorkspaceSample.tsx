'use client';

import React, { useState } from 'react';
import { NotConnectedNotice } from '@/components/ui/NotConnectedNotice';
import { SampleDataBadge } from '@/components/ui/SampleDataBadge';

type Mode = 'issue' | 'frame';

const DECISIONS = ['Xác nhận lỗi', 'Bác bỏ', 'Chưa chắc chắn', 'Yêu cầu sửa', 'Chuyển cấp trên'];

/**
 * Review Workspace theo đúng docs/design/screens/ReviewWorkspace.dc.html, dùng dữ liệu minh họa.
 * Hiện khi route mở không có frame_id (chưa nhận frame từ hàng đợi) hoặc chưa có API.
 * Mọi hành động ghi bị chặn: không gọi API, không báo thành công giả.
 */
export function ReviewWorkspaceSample() {
  const [mode, setMode] = useState<Mode>('issue');
  const [decision, setDecision] = useState(DECISIONS[0]);
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null);

  // TODO(backend): GET /api/frames/{id}/issues/ — nạp issue thật cho khung hình
  // TODO(backend): POST /api/issues/{id}/decisions/ — lưu quyết định
  // TODO(backend): GET /api/queues/{name}/next/ — chuyển frame qua hàng đợi
  const block = (message: string) => (event: React.FormEvent | React.MouseEvent) => {
    event.preventDefault();
    setBlockedMessage(message);
  };

  return (
    <div className="lx-stack" data-testid="review-workspace-sample">
      <div className="lx-row">
        <SampleDataBadge />
        <span className="lx-hint">Chưa có frame từ hàng đợi nên hiển thị dữ liệu minh họa theo thiết kế.</span>
      </div>

      <div className="lx-ws lx-ws--reference">
        <section className="lx-stage" aria-label="Khung hình annotation từ CVAT">
          <div className="lx-stage__bar">
            <div className="lx-segment" role="group" aria-label="Chế độ review">
              <button type="button" aria-pressed={mode === 'issue'} onClick={() => setMode('issue')}>
                Issue Review
              </button>
              <button type="button" aria-pressed={mode === 'frame'} onClick={() => setMode('frame')}>
                Frame Review
              </button>
            </div>
            <span>
              Frame <b className="lx-num">00428</b> / 00599
            </span>
            <span className="lx-grow" />
            <label className="lx-check">
              <input type="checkbox" defaultChecked />
              <span>Annotation hiện tại</span>
            </label>
            <label className="lx-check">
              <input type="checkbox" defaultChecked />
              <span>Đề xuất mô hình</span>
            </label>
            <button type="button" className="lx-ghostbtn" onClick={block('Chưa có liên kết CVAT thật, chưa mở được CVAT')}>
              Mở trong CVAT
            </button>
          </div>

          <div className="lx-stage__view">
            <svg viewBox="0 0 960 540" role="img" aria-label="Khung hình đường phố với annotation xe số 18 và đề xuất của mô hình">
              <rect width="960" height="540" fill="#2a2f37" />
              <polygon points="0,540 960,540 960,330 600,230 360,230 0,330" fill="#353b45" />
              <line x1="480" y1="540" x2="480" y2="236" stroke="#59616e" strokeWidth="3" strokeDasharray="26 22" />
              <rect x="0" y="0" width="960" height="228" fill="#252a31" />
              <g opacity={mode === 'frame' ? 1 : 0.3} fontFamily="Inter, sans-serif" fontSize="14">
                <rect x="96" y="318" width="150" height="104" fill="none" stroke="#c7ccd4" strokeWidth="2" />
                <text x="96" y="310" fill="#e8eaee">car #12</text>
                <rect x="740" y="268" width="38" height="92" fill="none" stroke="#c7ccd4" strokeWidth="2" />
                <text x="700" y="260" fill="#e8eaee">pedestrian #07</text>
                <rect x="560" y="286" width="84" height="58" fill="none" stroke="#c7ccd4" strokeWidth="2" />
                <text x="560" y="278" fill="#e8eaee">car #21</text>
              </g>
              <rect x="300" y="296" width="200" height="140" fill="none" stroke="#5fd0c7" strokeWidth="3" strokeDasharray="10 6" />
              <rect x="318" y="316" width="168" height="112" fill="none" stroke="#f2c14e" strokeWidth="3" />
              <g fontFamily="Inter, sans-serif" fontSize="14" fontWeight="600">
                <rect x="318" y="292" width="124" height="22" fill="#f2c14e" />
                <text x="326" y="308" fill="#1f2329">car #18 · hiện tại</text>
                <rect x="300" y="440" width="196" height="22" fill="#5fd0c7" />
                <text x="308" y="456" fill="#1f2329">mô hình: truck · 0.81</text>
              </g>
            </svg>
          </div>

          <div className="lx-stage__bar lx-stage__bar--foot">
            <button type="button" className="lx-ghostbtn" onClick={block('Chưa chuyển frame vì chưa có hàng đợi thật')}>‹ Frame trước</button>
            <button type="button" className="lx-ghostbtn" onClick={block('Chưa chuyển frame vì chưa có hàng đợi thật')}>Frame sau ›</button>
            <span className="lx-grow" />
            {mode === 'frame' ? (
              <span>Nhấn vào một object để tạo issue mới.</span>
            ) : (
              <span>Đường liền: annotation hiện tại · Đường đứt: đề xuất của mô hình</span>
            )}
          </div>
        </section>

        <aside className="lx-ws__panel" aria-label="Chi tiết issue và quyết định">
          <div className="lx-ws__sec">
            <div className="lx-row lx-row--between">
              <span>
                <b className="lx-mono">QC-00128</b> <span className="lx-hint">· Issue 3 / 124</span>
              </span>
              <span>
                <span className="lx-badge lx-badge--danger">Cao</span> <span className="lx-badge">Chờ review</span>
              </span>
            </div>
            <h2 className="lx-h2">Nghi sai nhãn: car hay truck</h2>
            <dl className="lx-kv">
              <dt>Frame · Object</dt>
              <dd>00428 · #18</dd>
              <dt>Annotation hiện tại</dt>
              <dd>car</dd>
              <dt>Nguồn</dt>
              <dd>
                Mô hình độc lập bất đồng · revision <span className="lx-mono">a91f3c</span>
              </dd>
            </dl>
          </div>

          <div className="lx-ws__sec">
            <h3 className="lx-h2 lx-h2--sm">Bằng chứng</h3>
            <table className="lx-table lx-table--sm">
              <tbody>
                <tr><td className="lx-muted">Annotation</td><td>car</td></tr>
                <tr><td className="lx-muted">Mô hình độc lập</td><td>truck · độ tin cậy 0.81</td></tr>
                <tr>
                  <td className="lx-muted">Mô hình thị giác – ngôn ngữ</td>
                  <td><span className="lx-badge lx-badge--danger">Failed</span> chưa có kết quả</td>
                </tr>
              </tbody>
            </table>
            <details>
              <summary className="lx-ws__summary">Hướng dẫn liên quan · Quy tắc VEH-03</summary>
              <p className="lx-muted lx-ws__note">
                Xe có thùng hàng rời phía sau cabin được gán nhãn <b>truck</b>. Xe chở người, mui kín liền khối gán nhãn <b>car</b>.{' '}
                <span className="lx-subtle">Guideline v1.2 · Phân loại phương tiện, mục 3.2</span>
              </p>
            </details>
            <details>
              <summary className="lx-ws__summary">Case tương tự đã phân xử (3)</summary>
              <p className="lx-muted lx-ws__note">
                CASE-021 · Xe bán tải thùng hở → <b>truck</b>. CASE-034 · Xe van → <b>car</b>. CASE-040 · Xe bán tải có nắp thùng → <b>truck</b>.
              </p>
            </details>
          </div>

          <form className="lx-ws__decide" onSubmit={block('Quyết định chưa được lưu và chưa gửi tới server')}>
            <NotConnectedNotice detail={blockedMessage ?? undefined} />
            <span className="lx-label" id="sample-decision-label">Quyết định</span>
            <div className="lx-choices" role="radiogroup" aria-labelledby="sample-decision-label">
              {DECISIONS.map((label) => (
                <label className="lx-choice" key={label}>
                  <input
                    type="radio"
                    name="sample-decision"
                    checked={decision === label}
                    onChange={() => setDecision(label)}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            <div className="lx-grid lx-grid--2">
              <div className="lx-field">
                <label className="lx-label" htmlFor="sample-dt">Loại lỗi đã xác nhận</label>
                <select id="sample-dt" className="lx-select">
                  <option>Sai nhãn</option>
                  <option>Hình học</option>
                  <option>Thiếu object</option>
                </select>
              </div>
              <div className="lx-field">
                <label className="lx-label" htmlFor="sample-sv">Mức độ</label>
                <select id="sample-sv" className="lx-select">
                  <option>Nghiêm trọng</option>
                  <option>Trung bình</option>
                  <option>Nhẹ</option>
                </select>
              </div>
            </div>
            <div className="lx-field">
              <label className="lx-label" htmlFor="sample-rs">Lý do</label>
              <textarea
                id="sample-rs"
                className="lx-textarea"
                placeholder="Ví dụ: Thùng hàng rời phía sau cabin, theo VEH-03 phải gán nhãn truck."
              />
            </div>
            <div className="lx-row lx-row--between">
              <button type="button" className="lx-btn lx-btn--ghost" onClick={block('Chưa chuyển issue vì chưa có danh sách issue thật')}>‹ Issue trước</button>
              <button type="submit" className="lx-btn lx-btn--primary">Lưu và chuyển issue tiếp ›</button>
            </div>
          </form>
        </aside>
      </div>
    </div>
  );
}
