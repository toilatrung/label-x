import type { AuthSession, UserRole } from '@/types/auth';

export const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: 'Super Admin',
  qc_admin: 'Quality Control Admin',
  qa_lead: 'Quality Assurance Lead',
  reviewer: 'Reviewer',
  annotator: 'Annotator',
  product_owner: 'Product Owner',
  data_model_owner: 'Data/Model Owner',
};

export const ROLE_CODES: Record<UserRole, string> = {
  super_admin: 'SA',
  qc_admin: 'AD',
  qa_lead: 'QA',
  reviewer: 'RV',
  annotator: 'AN',
  product_owner: 'PO',
  data_model_owner: 'DMO',
};

export function rolesForDataset(session: AuthSession | null, datasetId: number | null): UserRole[] {
  return session?.roles.filter(({ role, dataset_id }) => (datasetId !== null && dataset_id === datasetId) ||
    (dataset_id === null && (role === 'super_admin' || role === 'qc_admin'))).map(({ role }) => role) ?? [];
}

export function hasDatasetPermission(session: AuthSession | null, datasetId: number | null,
  check: (role: UserRole) => boolean, requiresIdentity = false): boolean {
  if (requiresIdentity && session?.identity_mapping.status !== 'mapped') return false;
  return rolesForDataset(session, datasetId).some(check);
}

export function canAccessAnalysis(role: UserRole): boolean {
  return ['qa_lead', 'qc_admin', 'super_admin'].includes(role);
}

export function canAccessReview(role: UserRole): boolean {
  return ['reviewer', 'qa_lead', 'super_admin'].includes(role);
}

export function canAccessEscalations(role: UserRole): boolean {
  return ['qa_lead', 'super_admin'].includes(role);
}

export function canAccessReports(role: UserRole): boolean {
  return ['annotator', 'reviewer', 'qa_lead', 'qc_admin', 'super_admin', 'product_owner', 'data_model_owner'].includes(role);
}

export function canAccessConfiguration(role: UserRole): boolean {
  return ['qc_admin', 'super_admin', 'qa_lead'].includes(role);
}
