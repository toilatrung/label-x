import { describe, expect, it } from 'vitest';
import { formatCount, formatDateTime, shortRevision, snapshotCode } from '@/lib/format';

describe('shared display formats (design: 12,500 · 2026-10-04 06:50 · a91f3c · SNP-014)', () => {
  it('separates thousands and shows an empty value as a dash', () => {
    expect(formatCount(12500)).toBe('12,500');
    expect(formatCount(3000)).toBe('3,000');
    expect(formatCount(0)).toBe('0');
    expect(formatCount(null)).toBe('—');
    expect(formatCount(undefined)).toBe('—');
  });

  it('formats ISO time as YYYY-MM-DD HH:mm in local time and keeps unparsable text', () => {
    const local = new Date(2026, 9, 4, 6, 50);
    expect(formatDateTime(local.toISOString())).toBe('2026-10-04 06:50');
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime('chưa rõ')).toBe('chưa rõ');
  });

  it('shortens a revision to 6 characters without the algorithm prefix', () => {
    expect(shortRevision('sha256:a91f3c5d77e0')).toBe('a91f3c');
    expect(shortRevision('7be2049d')).toBe('7be204');
    expect(shortRevision('')).toBe('—');
    expect(shortRevision(null)).toBe('—');
  });

  it('pads snapshot codes to three digits', () => {
    expect(snapshotCode(14)).toBe('SNP-014');
    expect(snapshotCode(7)).toBe('SNP-007');
    expect(snapshotCode(2100)).toBe('SNP-2100');
  });
});
