import { UserRole } from '@/types/auth';

export const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: 'Super Admin',
  qc_admin: 'Quality Control Admin',
  qa_lead: 'Quality Assurance Lead',
  reviewer: 'Reviewer',
  annotator: 'Annotator',
};

export const ROLE_CODES: Record<UserRole, string> = {
  super_admin: 'SA',
  qc_admin: 'AD',
  qa_lead: 'QA',
  reviewer: 'RV',
  annotator: 'AN',
};

export function canAccessSummary(_role: UserRole): boolean {
  return Boolean(_role); // Mọi vai trò hợp lệ đều có thể xem Summary
}

export function canAccessAnalysis(role: UserRole): boolean {
  return ['qa_lead', 'qc_admin', 'super_admin'].includes(role);
}

export function canAccessReview(role: UserRole): boolean {
  return ['reviewer', 'qa_lead', 'qc_admin', 'super_admin'].includes(role);
}

export function canAccessEscalations(role: UserRole): boolean {
  return ['qa_lead', 'super_admin'].includes(role);
}

export function canAccessCalibration(_role: UserRole): boolean {
  return Boolean(_role); // Mọi vai trò hợp lệ đều tham gia
}

export function canAccessReports(role: UserRole): boolean {
  return ['qa_lead', 'super_admin'].includes(role);
}

export function canAccessConfiguration(role: UserRole): boolean {
  return ['qc_admin', 'super_admin', 'qa_lead'].includes(role);
}
