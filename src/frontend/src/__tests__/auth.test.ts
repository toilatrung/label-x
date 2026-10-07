import { describe, it, expect } from 'vitest';
import {
  canAccessAnalysis,
  canAccessReview,
  canAccessEscalations,
  canAccessConfiguration,
  ROLE_LABELS,
  ROLE_CODES,
} from '@/lib/auth/roles';
import { findMockUser } from '@/lib/auth/mock-users';

describe('Auth & Roles Domain Logic', () => {
  it('defines labels and codes for all 5 roles', () => {
    expect(ROLE_LABELS.super_admin).toBe('Super Admin');
    expect(ROLE_LABELS.annotator).toBe('Annotator');
    expect(ROLE_CODES.super_admin).toBe('SA');
    expect(ROLE_CODES.annotator).toBe('AN');
  });

  it('restricts Quality Analysis strictly to QA Lead, QC Admin, Super Admin', () => {
    expect(canAccessAnalysis('super_admin')).toBe(true);
    expect(canAccessAnalysis('qa_lead')).toBe(true);
    expect(canAccessAnalysis('qc_admin')).toBe(true);
    expect(canAccessAnalysis('reviewer')).toBe(false);
    expect(canAccessAnalysis('annotator')).toBe(false);
  });

  it('restricts Review Center from Annotators', () => {
    expect(canAccessReview('super_admin')).toBe(true);
    expect(canAccessReview('reviewer')).toBe(true);
    expect(canAccessReview('qa_lead')).toBe(true);
    expect(canAccessReview('annotator')).toBe(false);
  });

  it('restricts Escalations to QA Lead and Super Admin', () => {
    expect(canAccessEscalations('super_admin')).toBe(true);
    expect(canAccessEscalations('qa_lead')).toBe(true);
    expect(canAccessEscalations('qc_admin')).toBe(false);
    expect(canAccessEscalations('reviewer')).toBe(false);
    expect(canAccessEscalations('annotator')).toBe(false);
  });

  it('restricts Configuration access correctly', () => {
    expect(canAccessConfiguration('super_admin')).toBe(true);
    expect(canAccessConfiguration('qc_admin')).toBe(true);
    expect(canAccessConfiguration('qa_lead')).toBe(true);
    expect(canAccessConfiguration('reviewer')).toBe(false);
    expect(canAccessConfiguration('annotator')).toBe(false);
  });

  it('finds mock users with valid credentials and rejects invalid passwords', () => {
    const valid = findMockUser('admin', 'password123');
    expect(valid).toBeDefined();
    expect(valid?.role).toBe('super_admin');

    const invalid = findMockUser('admin', 'wrong_pass');
    expect(invalid).toBeUndefined();

    const notFound = findMockUser('unknown_user');
    expect(notFound).toBeUndefined();
  });
});
