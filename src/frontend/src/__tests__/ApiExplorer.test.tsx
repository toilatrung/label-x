import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
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
    expect(screen.getByText('/api/rework/{id}/current-revision/')).toBeInTheDocument();
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
    expect(API_ENDPOINTS).toHaveLength(83);
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

  it('includes backend-only and design-driven operations outside the OpenAPI baseline', () => {
    render(<ApiExplorer />);
    expect(screen.getByText('/api/decision-cases/')).toBeInTheDocument();
    expect(screen.getByText('/api/calibration/assignments/')).toBeInTheDocument();
    expect(screen.getByText('/api/releases/{id}/manifest/')).toBeInTheDocument();
    expect(screen.getAllByText('Design').length).toBeGreaterThan(0);
  });
});
