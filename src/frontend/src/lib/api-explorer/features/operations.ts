import type { ApiEndpoint } from '../types';

export const OPERATIONS_ENDPOINTS = [
  { id: 'internal_metrics', method: 'GET', path: '/internal/metrics/', group: 'Operations', summary: 'Metrics vận hành dạng Prometheus', connection: 'backend', responseStatus: 200, response: 'labelx_run_shards_total{status="succeeded"} 240' },
] satisfies ApiEndpoint[];
