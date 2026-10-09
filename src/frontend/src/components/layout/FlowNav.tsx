'use client';

import React from 'react';
import { useAuth } from '@/lib/auth/auth-context';
import { canAccessAnalysis, canAccessReview, canAccessReports } from '@/lib/auth/roles';

export type FlowModule = 'analysis' | 'review' | 'reports';
const FLOWS = {
  analysis: { title: 'Phân tích chất lượng', steps: ['Snapshot', 'Cấu hình phân tích', 'Lịch sử thực thi'], descriptions: ['Chốt dữ liệu', 'Chọn engine và ngưỡng', 'Theo dõi kết quả'], permission: canAccessAnalysis },
  review: { title: 'Trung tâm kiểm tra', steps: ['Hàng đợi', 'Kiểm tra ảnh', 'Theo dõi sửa'], descriptions: ['Ảnh cần kiểm tra', 'Xem và đánh giá', 'Kiểm tra lại sau khi sửa'], permission: canAccessReview },
  reports: { title: 'Báo cáo và phát hành', steps: ['Báo cáo chất lượng', 'Cổng chất lượng', 'Lịch sử phát hành'], descriptions: ['Tổng hợp kết quả', 'Đối chiếu điều kiện', 'Theo dõi phát hành'], permission: canAccessReports },
};

export function FlowNav({ flow, currentStep = 1 }: { flow: FlowModule; currentStep?: number }) {
  const { hasPermission } = useAuth();
  const definition = FLOWS[flow];
  if (!hasPermission(definition.permission, flow === 'review')) return null;
  return <nav className="lx-flow" aria-label={definition.title}>
    <ol className="lx-flow__steps">
      {definition.steps.map((title, index) => <li key={title} className={`lx-flow__step${index + 1 === currentStep ? ' is-active' : ''}`}>
        <span className="lx-flow__label" aria-current={index + 1 === currentStep ? 'step' : undefined}>
          <span className="lx-flow__n">{index + 1}</span>
          <span>{title}<small className="lx-flow__description">{definition.descriptions[index]}</small></span>
        </span>
      </li>)}
    </ol>
  </nav>;
}
