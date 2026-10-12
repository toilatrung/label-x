'use client';

import React, { useEffect, useRef, useState } from 'react';

interface Props {
  onClose: () => void;
  issueId?: number;
  initialRule?: string;
}

export function GuidelineGapModal({ onClose, issueId, initialRule = '' }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const ruleField = useRef<HTMLSelectElement>(null);
  const contentField = useRef<HTMLTextAreaElement>(null);
  const reasonField = useRef<HTMLTextAreaElement>(null);
  const [rule, setRule] = useState(initialRule);
  const [content, setContent] = useState('');
  const [reason, setReason] = useState('');
  const [tried, setTried] = useState(false);
  const [notice, setNotice] = useState(false);

  useEffect(() => {
    if (!opener.current && document.activeElement instanceof HTMLElement) opener.current = document.activeElement;
    dialog.current?.showModal();
    ruleField.current?.focus();
  }, []);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setTried(true);
    setNotice(false);
    if (!rule) return ruleField.current?.focus();
    if (!content.trim()) return contentField.current?.focus();
    if (!reason.trim()) return reasonField.current?.focus();
    setNotice(true);
  };

  return (
    <dialog ref={dialog} className="lx-gap-dialog" aria-labelledby="guideline-gap-title"
      aria-describedby="guideline-gap-description" onClose={() => { onClose(); requestAnimationFrame(() => opener.current?.focus()); }}
      onClick={(event) => { if (event.target === dialog.current) dialog.current?.close(); }}>
      <div className="lx-gap">
        <header className="lx-gap__head">
          <div>
            <h2 id="guideline-gap-title">Tạo Guideline Gap</h2>
            <p id="guideline-gap-description">Ghi nhận phần hướng dẫn còn thiếu để nhóm phụ trách xem xét. Đây là bản thiết kế minh họa.</p>
          </div>
          <button type="button" className="lx-gap__close" aria-label="Đóng hộp thoại" onClick={() => dialog.current?.close()}>×</button>
        </header>
        <form className="lx-gap__body" noValidate onSubmit={submit}>
          <div className="lx-gap__context"><strong>Ngữ cảnh:</strong> Dataset Road Vision Urban · Guideline v1.2<br />
            {issueId && <><strong>Issue liên quan:</strong> QC-{String(issueId).padStart(5, '0')} · Quy tắc {initialRule || '—'}<br /></>}
            <span className="lx-muted">Dữ liệu minh họa</span>
          </div>
          <div className="lx-gap__fields">
            <div className="lx-field">
              <label className="lx-label" htmlFor="gap-rule">Quy tắc liên quan *</label>
              <select ref={ruleField} id="gap-rule" className="lx-select" value={rule} onChange={(event) => setRule(event.target.value)} aria-invalid={tried && !rule} aria-describedby={tried && !rule ? 'gap-rule-error' : undefined}>
                <option value="">Chọn quy tắc</option>
                {initialRule && !['VEH-03', 'G-014', 'A-003'].includes(initialRule) && <option value={initialRule}>{initialRule}</option>}
                <option value="VEH-03">VEH-03 · Phân loại phương tiện</option>
                <option value="G-014">G-014 · Vật bị che</option>
                <option value="A-003">A-003 · Thuộc tính occluded</option>
              </select>
              {tried && !rule && <span id="gap-rule-error" className="lx-gap__error">Chọn quy tắc liên quan.</span>}
            </div>
            <div className="lx-field">
              <label className="lx-label" htmlFor="gap-content">Nội dung hướng dẫn còn thiếu *</label>
              <textarea ref={contentField} id="gap-content" className="lx-textarea" value={content} onChange={(event) => setContent(event.target.value)} aria-invalid={tried && !content.trim()} aria-describedby={tried && !content.trim() ? 'gap-content-error' : undefined} placeholder="Ví dụ: Chưa rõ xe buýt mini chở hàng thuộc nhãn nào." />
              {tried && !content.trim() && <span id="gap-content-error" className="lx-gap__error">Mô tả nội dung còn thiếu.</span>}
            </div>
            <div className="lx-field">
              <label className="lx-label" htmlFor="gap-reason">Lý do / bằng chứng *</label>
              <textarea ref={reasonField} id="gap-reason" className="lx-textarea" value={reason} onChange={(event) => setReason(event.target.value)} aria-invalid={tried && !reason.trim()} aria-describedby={tried && !reason.trim() ? 'gap-reason-error' : undefined} placeholder="Nêu tình huống, quyết định còn mâu thuẫn hoặc Case liên quan." />
              {tried && !reason.trim() && <span id="gap-reason-error" className="lx-gap__error">Nhập lý do hoặc bằng chứng.</span>}
            </div>
          </div>
          {notice && <div className="lx-gap__notice" role="status">Chức năng vẫn chưa được kết nối với server. Nội dung chưa được lưu.</div>}
          <div className="lx-gap__actions">
            <button type="button" className="lx-btn" onClick={() => dialog.current?.close()}>Hủy</button>
            <button type="submit" className="lx-btn lx-btn--primary">Tạo Guideline Gap</button>
          </div>
        </form>
      </div>
    </dialog>
  );
}
