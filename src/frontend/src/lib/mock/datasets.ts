import type { Dataset } from '@/lib/snapshots/api';

/**
 * Mock datasets matching design screens and API Explorer catalog (M-01/M-02).
 * Used when running Next.js without a live Django backend service.
 */
export const MOCK_DATASETS: Dataset[] = [
  {
    id: 14,
    name: 'Road Vision Urban',
    cvat_project_id: 31,
    guideline_version: 'v1.2',
    taxonomy_version: 'v3',
  },
  {
    id: 13,
    name: 'Road Vision Urban',
    cvat_project_id: 31,
    guideline_version: 'v1.2',
    taxonomy_version: 'v3',
  },
  {
    id: 9,
    name: 'Road Vision Highway',
    cvat_project_id: 34,
    guideline_version: 'v1.2',
    taxonomy_version: 'v3',
  },
  {
    id: 3,
    name: 'Parking Lot',
    cvat_project_id: 37,
    guideline_version: 'v1.1',
    taxonomy_version: 'v2',
  },
  {
    id: 1,
    name: 'Road Vision Urban',
    cvat_project_id: 31,
    guideline_version: 'v1.2',
    taxonomy_version: 'v3',
  },
  {
    id: 42,
    name: 'Urban',
    cvat_project_id: 31,
    guideline_version: 'v1.2',
    taxonomy_version: 'v3',
  },
];
