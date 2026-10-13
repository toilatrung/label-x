import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { REQUEST_BODIES } from '@/lib/api-explorer/requests';
import { ApiExplorer } from '@/app/swagger/ApiExplorer';
import { API_ENDPOINTS, API_NAVIGATION } from '@/lib/api-explorer/catalog';
import { STATUS_RESPONSE_EXAMPLES } from '@/lib/api-explorer/status-examples';

describe('API Explorer', () => {
  it('shows backend and product API operations as available data sources', () => {
    render(<ApiExplorer />);
    expect(screen.getByRole('heading', { name: 'API Explorer' })).toBeInTheDocument();
    expect(screen.getAllByText('Backend API').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Product API').length).toBeGreaterThan(0);
    expect(screen.getByText('/api/auth/session/')).toBeInTheDocument();
    expect(screen.getByText('/api/evaluations/{id}/')).toBeInTheDocument();
  });

  it('filters operations by connection status and search text', () => {
    render(<ApiExplorer />);
    fireEvent.click(screen.getByRole('button', { name: /Product API/ }));
    expect(screen.queryByText('/api/auth/session/')).not.toBeInTheDocument();
    expect(screen.getByText('/api/evaluations/{id}/')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Tìm theo path, operation hoặc nhóm...'), { target: { value: 'reports' } });
    expect(screen.getByText('/api/reports/{id}/')).toBeInTheDocument();
    expect(screen.queryByText('/api/evaluations/{id}/')).not.toBeInTheDocument();
  });

  it('keeps a default response and adds state variants where the contract has a state machine', () => {
    const ids = new Set(API_ENDPOINTS.map(endpoint => endpoint.id));
    expect(API_ENDPOINTS).toHaveLength(78);
    expect(ids.size).toBe(API_ENDPOINTS.length);
    expect(API_ENDPOINTS.every(endpoint => Object.hasOwn(endpoint, 'response'))).toBe(true);
    expect(API_ENDPOINTS.find(endpoint => endpoint.id === 'runs_list')?.responseExamples?.map(example => example.label))
      .toEqual(['design', 'queued', 'running', 'completed', 'partial', 'failed', 'cancelled']);
    expect(API_ENDPOINTS.find(endpoint => endpoint.id === 'snapshots_list')?.responseExamples?.map(example => example.label))
      .toEqual(['design', 'pending', 'exporting', 'locked', 'failed']);
    expect(API_ENDPOINTS.find(endpoint => endpoint.id === 'rework_list')?.responseExamples?.map(example => example.label))
      .toEqual(['fix_pending', 'recheck_pending', 'resolved', 'reopened']);
    expect(API_ENDPOINTS.find(endpoint => endpoint.id === 'queues_list')?.responseExamples?.map(example => example.label))
      .toEqual(['unreviewed', 'in_review', 'incomplete', 'reviewed', 'awaiting_followup', 'completed']);
    expect(API_ENDPOINTS.find(endpoint => endpoint.id === 'evaluations_retrieve')?.responseExamples?.map(example => example.label))
      .toEqual(['queued', 'running', 'completed', 'failed', 'insufficient_sample']);
    expect(API_ENDPOINTS.find(endpoint => endpoint.id === 'waivers_approve')?.responseExamples?.map(example => example.label))
      .toEqual(['pending', 'approved', 'rejected', 'expired']);
    expect(Object.keys(STATUS_RESPONSE_EXAMPLES).length).toBeGreaterThanOrEqual(25);
    expect(Object.values(STATUS_RESPONSE_EXAMPLES).every(examples => examples && examples.length > 0)).toBe(true);
  });

  it('switches the displayed and copied payload between response states', () => {
    render(<ApiExplorer />);
    const selector = screen.getByRole('combobox', { name: 'Chọn response runs_list' });
    fireEvent.change(selector, { target: { value: '5' } });
    expect((selector as HTMLSelectElement).value).toBe('5');
    expect(selector.querySelector('option:checked')?.textContent).toBe('failed');
  });

  it('groups APIs by the product navigation shown in the design', () => {
    expect(API_NAVIGATION.map(group => group.label)).toEqual([
      'Overview',
      'Quality Analysis',
      'Review Center',
      'Escalations',
      'Calibration & Audit',
      'Reports & Releases',
      'Configuration',
    ]);
    expect(API_NAVIGATION.find(group => group.label === 'Overview')?.sections.map(item => item.label))
      .toEqual(['Quality Control Home', 'Quality Summary']);
    expect(API_NAVIGATION.find(group => group.label === 'Calibration & Audit')?.sections.map(item => item.label))
      .toEqual(['Performance Evaluation', 'Ground Truth Benchmark', 'Audit Sampling', 'Calibration']);
    expect(API_NAVIGATION.find(group => group.label === 'Configuration')?.sections.map(item => item.label))
      .toEqual(['Rules & Thresholds', 'Models & Guidelines', 'Workflow & Permissions']);
    expect(API_ENDPOINTS.every(endpoint => endpoint.section)).toBe(true);
  });

  it('uses the OpenAPI operation ID for Decision Case detail in Escalations', () => {
    const openapi = readFileSync('../../docs/04-api/openapi.yaml', 'utf8');
    const operationId = openapi.match(/\/api\/decision-cases\/\{id\}\/:\s*get:\s*operationId:\s*(\S+)/)?.[1];
    expect(operationId).toBeDefined();
    const detail = API_ENDPOINTS.find(endpoint => endpoint.path === '/api/decision-cases/{id}/');
    expect(detail?.id).toBe(operationId);
    expect(detail?.group).toBe('Escalations');
    expect(API_ENDPOINTS.some(endpoint => endpoint.id === 'decision_cases_retrieve')).toBe(false);
    render(<ApiExplorer />);
    fireEvent.change(screen.getByPlaceholderText('Tìm theo path, operation hoặc nhóm...'), { target: { value: operationId } });
    expect(screen.getByText('/api/decision-cases/{id}/')).toBeInTheDocument();
    expect(screen.getByLabelText(`Response ${operationId}`)).toBeDefined();
    expect(screen.getByRole('button', { name: `Sao chép request ${operationId}` })).toBeDefined();
    expect(screen.getByRole('button', { name: `Sao chép payload ${operationId}` })).toBeDefined();
  });

  it('includes backend-only and design-driven operations outside the OpenAPI baseline', () => {
    render(<ApiExplorer />);
    expect(screen.getByText('/api/decision-cases/')).toBeInTheDocument();
    expect(screen.getByText('/api/calibration/assignments/')).toBeInTheDocument();
    expect(screen.getByText('/api/releases/{id}/manifest/')).toBeInTheDocument();
    expect(screen.getAllByText('Design').length).toBeGreaterThan(0);
  });

  it('shows the sketch payload before state variants can replace its rows and metrics', () => {
    render(<ApiExplorer />);
    const sketch = readFileSync('../../docs/design/screens/Escalations.dc.html', 'utf8');
    const gaps = JSON.parse(screen.getByLabelText('Response guideline_gaps_list').textContent!);
    expect(gaps.count).toBe(6);
    for (const gap of gaps.results) {
      expect(sketch).toContain(gap.code);
      expect(sketch).toContain(gap.title);
      expect(sketch).toContain(gap.proposed_rule);
      expect(sketch).toContain(gap.status_label);
    }
    const rework = JSON.parse(screen.getByLabelText('Response rework_list').textContent!);
    expect(rework.counts).toMatchObject({ fix_pending: 5, recheck_pending: 7, resolved: 74 });
    const models = JSON.parse(screen.getByLabelText('Response models_list').textContent!).results;
    expect(models).toHaveLength(3);
    expect(models[1].confidence_threshold).toBe(0.7);
    expect(models[2].confidence_threshold).toBeNull();
    const rules = JSON.parse(screen.getByLabelText('Response config_version_rules').textContent!);
    const ruleSketch = readFileSync('../../docs/design/screens/RulesThresholds.dc.html', 'utf8');
    expect(rules.rules).toHaveLength(5);
    for (const rule of rules.rules) {
      expect(ruleSketch).toContain(rule.id);
      expect(ruleSketch).toContain(rule.name);
      expect(ruleSketch).toContain(rule.threshold_label);
    }
    expect(rules.sampling.random_rate).toBe(0.008);
    expect(rules.sampling.risk_rate).toBe(0.008);
    expect(rules.rules.find((rule: {id: string}) => rule.id === 'A-003').enabled).toBe(false);
  });

  it('includes all documented JSON bodies and leaves bodyless operations empty', () => {
    render(<ApiExplorer />);
    expect(screen.getByLabelText('Request guideline_gaps_create').textContent).toContain('VEH-03');
    expect(screen.getByLabelText('Request guideline_gaps_create').textContent).toContain('reason');
    expect(screen.getByLabelText('Request rework_list').textContent).toBe('GET /api/rework/?dataset_id=14');
    expect(screen.getByLabelText('Request auth_session').textContent).toBe('GET /api/auth/session/');
    for (const id of Object.keys(REQUEST_BODIES)) expect(API_ENDPOINTS.some(endpoint => endpoint.id === id)).toBe(true);
    expect(screen.getByLabelText('Response rework_current_revision').textContent).toContain('revision_sha256');
    const cases = JSON.parse(screen.getByLabelText('Response decision_cases_list').textContent!);
    expect(cases.results[0]).toMatchObject({ outcome: 'confirm', rule_id: 'VEH-03', correct_label: 'truck' });
    fireEvent.change(screen.getByRole('combobox', { name: 'Chọn response issues_adjudicate' }), { target: { value: '1' } });
    expect(screen.getByLabelText('Request issues_adjudicate').textContent).toContain('"correct_label": "truck"');
  });

  it('copies the selected response and the matching request independently', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    try {
      render(<ApiExplorer />);
      const selector = screen.getByRole('combobox', { name: 'Chọn response issues_decide' });
      fireEvent.change(selector, { target: { value: '2' } });
      expect(screen.getByLabelText('Request issues_decide').textContent).toContain('"action": "reject"');
      fireEvent.click(screen.getByRole('button', { name: 'Sao chép request issues_decide' }));
      expect(writeText).toHaveBeenLastCalledWith(screen.getByLabelText('Request issues_decide').textContent);
      fireEvent.click(screen.getByRole('button', { name: 'Sao chép payload issues_decide' }));
      expect(writeText).toHaveBeenLastCalledWith(screen.getByLabelText('Response issues_decide').textContent);
      await waitFor(() => expect(screen.getByRole('button', { name: 'Sao chép payload issues_decide' }).textContent).toBe('Đã sao chép'));
    } finally { vi.unstubAllGlobals(); }
  });
});
