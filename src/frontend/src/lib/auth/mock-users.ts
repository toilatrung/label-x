import type { AuthSession, UserRole } from '@/types/auth';

export interface MockUserRecord {
  id: number; username: string; password: string; fullName: string; role: UserRole;
}

// Fictional demo accounts; never used to recover from backend/network failures.
export const MOCK_USERS: MockUserRecord[] = [
  { id: 1, username: 'admin', password: 'password123', fullName: 'Quản trị hệ thống mẫu', role: 'super_admin' },
  { id: 2, username: 'qalead', password: 'password123', fullName: 'Trưởng kiểm tra mẫu', role: 'qa_lead' },
  { id: 3, username: 'qcadmin', password: 'password123', fullName: 'Quản trị chất lượng mẫu', role: 'qc_admin' },
  { id: 4, username: 'reviewer', password: 'password123', fullName: 'Người kiểm tra mẫu', role: 'reviewer' },
  { id: 5, username: 'annotator', password: 'password123', fullName: 'Người gán nhãn mẫu', role: 'annotator' },
  { id: 6, username: 'productowner', password: 'password123', fullName: 'Chủ sản phẩm mẫu', role: 'product_owner' },
  { id: 7, username: 'modelowner', password: 'password123', fullName: 'Chủ dữ liệu và mô hình mẫu', role: 'data_model_owner' },
];

export function findMockUser(username: string, password?: string): MockUserRecord | undefined {
  return MOCK_USERS.find((item) => item.username === username.trim() &&
    (password === undefined || item.password === password));
}

export function toMockSession(user: MockUserRecord): AuthSession {
  return {
    user: { id: user.id, username: user.username, display_name: user.fullName },
    roles: [{ role: user.role, dataset_id: ['super_admin', 'qc_admin'].includes(user.role) ? null : 1 }],
    identity_mapping: { status: 'mapped', cvat_user_id: 100 + user.id },
  };
}
