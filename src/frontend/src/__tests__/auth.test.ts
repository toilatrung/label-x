import { describe, it, expect } from 'vitest';
import { canAccessAnalysis, canAccessReview, canAccessEscalations, canAccessConfiguration,
  ROLE_LABELS, ROLE_CODES, rolesForDataset, hasDatasetPermission } from '@/lib/auth/roles';
import { findMockUser, MOCK_USERS, toMockSession } from '@/lib/auth/mock-users';
import type { AuthSession } from '@/types/auth';

describe('Contract roles and dataset grants', () => {
  it('covers all seven T-001 roles', () => {
    expect(Object.keys(ROLE_LABELS)).toHaveLength(7);
    expect(Object.keys(ROLE_CODES)).toHaveLength(7);
    expect(MOCK_USERS.map((user) => user.role).sort()).toEqual(Object.keys(ROLE_LABELS).sort());
  });

  it('does not treat read-only QC Admin as a reviewer', () => {
    expect(canAccessReview('qc_admin')).toBe(false);
    expect(canAccessReview('reviewer')).toBe(true);
    expect(canAccessAnalysis('qc_admin')).toBe(true);
    expect(canAccessConfiguration('annotator')).toBe(false);
    expect(canAccessEscalations('qa_lead')).toBe(true);
    expect(canAccessReview('product_owner')).toBe(false);
    expect(canAccessReview('data_model_owner')).toBe(false);
  });

  it('rejects invalid credentials', () => {
    expect(findMockUser('admin', 'password123')).toBeDefined();
    expect(findMockUser('admin', 'wrong')).toBeUndefined();
    expect(findMockUser('unknown')).toBeUndefined();
  });

  it('combines grants only inside the selected dataset', () => {
    const session: AuthSession = { ...toMockSession(MOCK_USERS[3]), roles: [
      { role: 'reviewer', dataset_id: 1 }, { role: 'qa_lead', dataset_id: 2 },
    ] };
    expect(rolesForDataset(session, 1)).toEqual(['reviewer']);
    expect(hasDatasetPermission(session, 1, canAccessAnalysis)).toBe(false);
    expect(hasDatasetPermission(session, 2, canAccessAnalysis)).toBe(true);
    expect(hasDatasetPermission(session, 3, canAccessReview)).toBe(false);
  });

  it('combines multiple roles in one dataset without trusting the display role', () => {
    const session: AuthSession = { ...toMockSession(MOCK_USERS[4]), roles: [
      { role: 'annotator', dataset_id: 1 }, { role: 'reviewer', dataset_id: 1 },
    ] };
    expect(hasDatasetPermission(session, 1, canAccessReview, true)).toBe(true);
  });

  it('accepts global grants only for Super Admin and QC Admin', () => {
    expect(hasDatasetPermission(toMockSession(MOCK_USERS[0]), 42, canAccessReview)).toBe(true);
    const invalid: AuthSession = { ...toMockSession(MOCK_USERS[3]), roles: [{ role: 'reviewer', dataset_id: null }] };
    expect(hasDatasetPermission(invalid, 1, canAccessReview)).toBe(false);
  });

  it('fails closed for missing CVAT identity, including Super Admin', () => {
    const unmapped: AuthSession = { ...toMockSession(MOCK_USERS[0]), identity_mapping: { status: 'missing' } };
    expect(hasDatasetPermission(unmapped, 1, canAccessReview, true)).toBe(false);
    expect(hasDatasetPermission(unmapped, 1, canAccessConfiguration)).toBe(true);
  });
});
