import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

export const MOCK_CONFIG_VERSIONS = [
  {
    id: 7,
    name: 'Road Vision Urban v7',
    status: 'published',
    engines: {
      schema: {
        enabled: true,
        version: '1.2.0',
        params: {
          taxonomy_version: 'Taxonomy v3',
          required_attributes: 'Thuộc tính bắt buộc theo từng lớp',
        },
      },
      geometry: {
        enabled: true,
        version: '1.0.0',
        params: {
          tolerance_px: 2,
          min_area_px: 24,
        },
      },
      duplicate: {
        enabled: true,
        version: '1.0.0',
        params: {
          iou_threshold: 0.85,
          same_class: true,
        },
      },
      detector: {
        enabled: true,
        version: '2.3.0',
        params: {
          model_version: 'Detector v2.3',
          confidence_threshold: 0.6,
        },
      },
      vlm: {
        enabled: true,
        version: '1.0.0',
        params: {
          model_version: 'VLM v1.0',
          max_candidates: 400,
        },
      },
      metric: {
        enabled: false,
        version: '1.0.0',
        params: {},
      },
    },
    thresholds: {
      iou: 0.85,
      coverage: 0.95,
      open_critical_issues: 0,
      residual_error_rate: 0.05,
      reviewer_agreement: 0.9,
      verified_rework: 1,
    },
    models: {
      detector: 'Detector v2.3',
      classifier: 'Classifier v1.8',
    },
    created_by: 1,
    created_at: '2026-10-04T06:45:00Z',
    published_at: '2026-10-04T06:47:00Z',
  },
];

export async function GET(request: Request) {
  if (!isMockAuth && process.env.NODE_ENV === 'production') {
    return NextResponse.json(
      { code: 'NOT_FOUND', message: 'API mẫu chưa được bật.' },
      { status: 404 }
    );
  }

  void request;
  return NextResponse.json(
    {
      next: null,
      previous: null,
      results: MOCK_CONFIG_VERSIONS,
    },
    {
      headers: { 'Cache-Control': 'no-store' },
    }
  );
}
