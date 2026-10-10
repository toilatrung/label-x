import React from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ReviewPage from '@/app/review/page';
import { AuthProvider } from '@/lib/auth/auth-context';
import { installMockAuthApi } from './helpers/mock-api';
import frameFixture from '@/lib/demo/frames.fixture.json';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/review',
  useSearchParams: () => new URLSearchParams('run=1'),
}));

async function setup() {
  const api = installMockAuthApi();
  await api.signIn('reviewer');
  const passthrough = api.fetchSpy.getMockImplementation()!;
  api.fetchSpy.mockImplementation(async (request: Request) => {
    const url = new URL(request.url);
    if (url.pathname === '/api/runs/1/frames/') {
      return new Response(JSON.stringify(frameFixture), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return passthrough(request);
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuthProvider><ReviewPage /></AuthProvider>
    </QueryClientProvider>,
  );
  return api;
}

describe('ReviewWorkspace (M-DEMO01 D-04)', () => {
  it('loads ranked frames and switches the canvas, candidate details and CVAT link together', async () => {
    const api = await setup();

    expect(await screen.findByRole('img', { name: /Ảnh 0001.jpg/ })).toBeDefined();
    expect(screen.getByText('IoU 0.93 giữa hai box cùng lớp')).toBeDefined();
    expect(screen.getByRole('link', { name: 'Mở trong CVAT' }).getAttribute('href'))
      .toBe('http://localhost:8080/tasks/23/jobs/20?frame=0');

    const canvas = screen.getByRole('img', { name: /Ảnh 0001.jpg/ });
    const candidate = within(canvas).getByRole('group', { name: 'Candidate car s1' });
    const box = candidate.querySelector('rect');
    expect(box?.getAttribute('x')).toBe('100');
    expect(box?.getAttribute('y')).toBe('200');
    expect(box?.getAttribute('width')).toBe('300');
    expect(box?.getAttribute('height')).toBe('220');

    fireEvent.click(screen.getByRole('button', { name: 'Xem frame 0002.jpg' }));
    expect(screen.getByRole('img', { name: /Ảnh 0002.jpg/ })).toBeDefined();
    expect(screen.getByText('Box vượt ngoài ảnh')).toBeDefined();
    expect(screen.getByRole('link', { name: 'Mở trong CVAT' }).getAttribute('href'))
      .toBe('http://localhost:8080/tasks/23/jobs/20?frame=1');
    expect(api.fetchSpy.mock.calls.some(([request]) => {
      const url = new URL(request.url);
      return url.pathname === '/api/runs/1/frames/' && url.searchParams.get('page_size') === '100';
    })).toBe(true);
  });
});
