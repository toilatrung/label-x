import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ApiExplorer } from '@/app/swagger/ApiExplorer';
import { API_ENDPOINTS } from '@/lib/api-explorer/catalog';

describe('API Explorer', () => {
  it('shows contract operations with backend and mock states', () => {
    render(<ApiExplorer />);
    expect(screen.getByRole('heading', { name: 'API Explorer' })).toBeInTheDocument();
    expect(screen.getAllByText('Đã kết nối BE').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mockup · Chưa nối BE').length).toBeGreaterThan(0);
    expect(screen.getByText('/api/auth/session/')).toBeInTheDocument();
    expect(screen.getByText('/api/evaluations/{id}/')).toBeInTheDocument();
  });

  it('filters operations by connection status and search text', () => {
    render(<ApiExplorer />);
    fireEvent.click(screen.getByRole('button', { name: /Chưa nối BE/ }));
    expect(screen.queryByText('/api/auth/session/')).not.toBeInTheDocument();
    expect(screen.getByText('/api/evaluations/{id}/')).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText('Tìm theo path, operation hoặc nhóm...'), { target: { value: 'reports' } });
    expect(screen.getByText('/api/reports/{id}/')).toBeInTheDocument();
    expect(screen.queryByText('/api/evaluations/{id}/')).not.toBeInTheDocument();
  });

  it('keeps exactly one sample response for every operation', () => {
    const ids = new Set(API_ENDPOINTS.map(endpoint => endpoint.id));
    expect(ids.size).toBe(API_ENDPOINTS.length);
    expect(API_ENDPOINTS.every(endpoint => Object.hasOwn(endpoint, 'response'))).toBe(true);
  });

  it('includes backend-only and design-driven operations outside the OpenAPI baseline', () => {
    render(<ApiExplorer />);
    expect(screen.getByText('/api/decision-cases/')).toBeInTheDocument();
    expect(screen.getByText('/api/calibration/assignments/')).toBeInTheDocument();
    expect(screen.getByText('/api/releases/{id}/manifest/')).toBeInTheDocument();
    expect(screen.getAllByText('Design').length).toBeGreaterThan(0);
  });
});
