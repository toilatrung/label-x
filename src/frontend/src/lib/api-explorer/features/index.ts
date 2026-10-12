import { AUTH_ENDPOINTS } from './auth';
import { DATASETS_ENDPOINTS } from './datasets';
import { SNAPSHOTS_ENDPOINTS } from './snapshots';
import { CONFIGURATION_ENDPOINTS } from './configuration';
import { RUNS_ENDPOINTS } from './runs';
import { OPERATIONS_ENDPOINTS } from './operations';
import { GUIDELINES_ENDPOINTS } from './guidelines';
import { REVIEW_ENDPOINTS } from './review';
import { REWORK_ENDPOINTS } from './rework';
import { EVALUATION_ENDPOINTS } from './evaluation';
import { GATE_ENDPOINTS } from './gate';
import { REPORTS_ENDPOINTS } from './reports';
import { ESCALATIONS_ENDPOINTS } from './escalations';
import { BENCHMARK_ENDPOINTS } from './benchmark';
import { AUDIT_ENDPOINTS } from './audit';
import { CALIBRATION_ENDPOINTS } from './calibration';
import { RELEASES_ENDPOINTS } from './releases';

import type { ApiEndpoint, ApiNavigationGroup, ApiSection } from '../types';

const pick = (endpoints: readonly ApiEndpoint[], ids: readonly string[]) => {
  const selected = new Set(ids);
  return endpoints.filter(endpoint => selected.has(endpoint.id));
};

const omit = (endpoints: readonly ApiEndpoint[], ids: readonly string[]) => {
  const excluded = new Set(ids);
  return endpoints.filter(endpoint => !excluded.has(endpoint.id));
};

const section = (key: string, label: string, ...sources: readonly ApiEndpoint[][]): ApiSection => ({
  key,
  label,
  endpoints: sources.flat(),
});

const WORKFLOW_AUTH_IDS = ['auth_workflow_permissions'] as const;
const WORKFLOW_CONFIG_IDS = ['workflow_rule_update'] as const;
const MODEL_CONFIG_IDS = ['models_list', 'models_update'] as const;
const ESCALATION_REVIEW_IDS = [
  'escalations_list',
  'issues_adjudicate',
  'decision_cases_list',
  'decision_cases_retrieve',
  'issues_similar_cases',
] as const;

/** Product navigation taxonomy mirrored from the approved TopBar design. */
export const API_NAVIGATION: readonly ApiNavigationGroup[] = [
  {
    key: 'overview',
    label: 'Overview',
    sections: [
      section('quality-control-home', 'Quality Control Home', omit(AUTH_ENDPOINTS, WORKFLOW_AUTH_IDS), DATASETS_ENDPOINTS),
      section('quality-summary', 'Quality Summary', OPERATIONS_ENDPOINTS),
    ],
  },
  {
    key: 'quality-analysis',
    label: 'Quality Analysis',
    sections: [section('quality-analysis', 'Quality Analysis', SNAPSHOTS_ENDPOINTS, RUNS_ENDPOINTS)],
  },
  {
    key: 'review-center',
    label: 'Review Center',
    sections: [section('review-center', 'Review Center', omit(REVIEW_ENDPOINTS, ESCALATION_REVIEW_IDS), REWORK_ENDPOINTS)],
  },
  {
    key: 'escalations',
    label: 'Escalations',
    sections: [section('escalations', 'Escalations', pick(REVIEW_ENDPOINTS, ESCALATION_REVIEW_IDS), ESCALATIONS_ENDPOINTS)],
  },
  {
    key: 'calibration-audit',
    label: 'Calibration & Audit',
    sections: [
      section('performance-evaluation', 'Performance Evaluation', EVALUATION_ENDPOINTS),
      section('ground-truth-benchmark', 'Ground Truth Benchmark', BENCHMARK_ENDPOINTS),
      section('audit-sampling', 'Audit Sampling', AUDIT_ENDPOINTS),
      section('calibration', 'Calibration', CALIBRATION_ENDPOINTS),
    ],
  },
  {
    key: 'reports-releases',
    label: 'Reports & Releases',
    sections: [
      section('quality-gate', 'Quality Gate', GATE_ENDPOINTS),
      section('reports', 'Reports', REPORTS_ENDPOINTS),
      section('releases', 'Releases', RELEASES_ENDPOINTS),
    ],
  },
  {
    key: 'configuration',
    label: 'Configuration',
    sections: [
      section(
        'rules-thresholds',
        'Rules & Thresholds',
        omit(CONFIGURATION_ENDPOINTS, [...WORKFLOW_CONFIG_IDS, ...MODEL_CONFIG_IDS]),
      ),
      section('models-guidelines', 'Models & Guidelines', pick(CONFIGURATION_ENDPOINTS, MODEL_CONFIG_IDS), GUIDELINES_ENDPOINTS),
      section(
        'workflow-permissions',
        'Workflow & Permissions',
        pick(AUTH_ENDPOINTS, WORKFLOW_AUTH_IDS),
        pick(CONFIGURATION_ENDPOINTS, WORKFLOW_CONFIG_IDS),
      ),
    ],
  },
] as const;

/** Backwards-compatible name for consumers that imported the first split catalog. */
export const API_FEATURES = API_NAVIGATION;
