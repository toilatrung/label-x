import { describe, it, expect } from 'vitest';
import { SAMPLE, formatCount, formatPercent } from '@/lib/mock/fixtures';

describe('mock fixtures', () => {
  it('keeps the canonical dataset consistent', () => {
    expect(SAMPLE.rework.closed + SAMPLE.rework.open).toBe(SAMPLE.rework.total);
    expect(((SAMPLE.rework.closed / SAMPLE.rework.total) * 100).toFixed(1)).toBe('86.0');
    expect(SAMPLE.coverage.value).toBeLessThan(SAMPLE.coverage.threshold);
  });
  it('formats counts and percents, em dash when empty', () => {
    expect(formatCount(12500)).toBe('12,500');
    expect(formatCount(null)).toBe('—');
    expect(formatPercent(92.4)).toBe('92.4%');
    expect(formatPercent(undefined)).toBe('—');
  });
});
