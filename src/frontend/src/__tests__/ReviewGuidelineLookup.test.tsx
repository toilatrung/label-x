import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { ReviewGuidelineLookup } from '@/components/review/ReviewGuidelineLookup';
import { installMockAuthApi } from './helpers/mock-api';

describe('ReviewGuidelineLookup (T-037 Fail-Closed & Stale-Safe Guideline Lookup)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('fails closed when snapshot guideline_version is null or empty, sending no request', async () => {
    const api = installMockAuthApi();
    const calls: URL[] = [];
    api.fetchSpy.mockImplementation(async (request) => {
      calls.push(new URL(request.url));
      return Response.json({ code: 'NOT_FOUND' }, { status: 404 });
    });

    render(<ReviewGuidelineLookup ruleId="VEH-03" guidelineVersion={null} />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeDefined();
    });

    expect(screen.getByText(/Snapshot không có guideline_version cố định/)).toBeDefined();
    // Absolutely no unpinned network request sent to API!
    expect(calls.filter((u) => u.pathname.includes('/api/guidelines/'))).toHaveLength(0);
  });

  it('clears stale content on rule/version change, and leaves no stale rule visible on failure', async () => {
    const api = installMockAuthApi();
    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname.includes('VEH-03')) {
        return Response.json({
          rule_id: 'VEH-03',
          section: '3.2',
          content: 'Nội dung quy tắc xe tải VEH-03',
          guideline_version: 'v1.0',
        });
      }
      return Response.json({ code: 'NOT_FOUND' }, { status: 404 });
    });

    const { rerender } = render(
      <ReviewGuidelineLookup ruleId="VEH-03" guidelineVersion="v1.0" />
    );

    await screen.findByText('Nội dung quy tắc xe tải VEH-03');
    expect(screen.getByText(/Mục 3.2/)).toBeDefined();

    // Rerender with a non-existent rule: should immediately clear VEH-03, then show failure
    rerender(<ReviewGuidelineLookup ruleId="NON_EXISTENT" guidelineVersion="v1.0" />);

    // Old rule must NOT remain visible
    expect(screen.queryByText('Nội dung quy tắc xe tải VEH-03')).toBeNull();

    await waitFor(() => {
      expect(screen.getByText(/Không tìm thấy quy tắc NON_EXISTENT/)).toBeDefined();
    });
    // Still no stale rule visible
    expect(screen.queryByText('Nội dung quy tắc xe tải VEH-03')).toBeNull();
  });

  it('discards out-of-order stale responses when requests finish out of order', async () => {
    const api = installMockAuthApi();

    // Simulate VEH-01 taking 200ms, PED-02 taking 50ms
    api.fetchSpy.mockImplementation(async (request) => {
      const url = new URL(request.url);
      if (url.pathname.includes('SLOW-01')) {
        await new Promise((r) => setTimeout(r, 100));
        return Response.json({
          rule_id: 'SLOW-01',
          section: '1.0',
          content: 'Nội dung cũ của SLOW-01',
          guideline_version: 'v1.0',
        });
      }
      if (url.pathname.includes('FAST-02')) {
        return Response.json({
          rule_id: 'FAST-02',
          section: '2.0',
          content: 'Nội dung mới của FAST-02',
          guideline_version: 'v1.0',
        });
      }
      return Response.json({}, { status: 404 });
    });

    const { rerender } = render(
      <ReviewGuidelineLookup ruleId="SLOW-01" guidelineVersion="v1.0" />
    );

    // Rapidly switch to FAST-02 before SLOW-01 returns
    rerender(<ReviewGuidelineLookup ruleId="FAST-02" guidelineVersion="v1.0" />);

    await screen.findByText('Nội dung mới của FAST-02');

    // Wait past SLOW-01 resolution time
    await new Promise((r) => setTimeout(r, 150));

    // FAST-02 should still be displayed, SLOW-01 must NOT overwrite it
    expect(screen.getByText('Nội dung mới của FAST-02')).toBeDefined();
    expect(screen.queryByText('Nội dung cũ của SLOW-01')).toBeNull();
  });

  it('rejects response if returned guideline_version mismatches requested version', async () => {
    const api = installMockAuthApi();
    api.fetchSpy.mockImplementation(async () => {
      return Response.json({
        rule_id: 'VEH-03',
        section: '3.2',
        content: 'Quy tắc từ phiên bản sai',
        guideline_version: 'v2.0-latest', // Mismatched version
      });
    });

    render(<ReviewGuidelineLookup ruleId="VEH-03" guidelineVersion="v1.0-snapshot" />);

    await waitFor(() => {
      expect(screen.getByText(/không khớp với phiên bản snapshot yêu cầu/)).toBeDefined();
    });

    expect(screen.queryByText('Quy tắc từ phiên bản sai')).toBeNull();
  });

  it('displays Case lookup limitation note without fabricating fake cases', async () => {
    render(<ReviewGuidelineLookup ruleId="VEH-03" guidelineVersion="v1.0" />);
    expect(
      screen.getByText(/Chức năng tra cứu Case tương tự hiện chưa khả dụng/)
    ).toBeDefined();
  });
});
