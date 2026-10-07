import { AuthUser } from '@/types/auth';

export interface MockUserRecord extends AuthUser {
  password: string;
}

export const MOCK_USERS: MockUserRecord[] = [
  {
    id: 'usr-sa-01',
    username: 'admin',
    password: 'password123',
    fullName: 'Trần Đức Thọ',
    role: 'super_admin',
    email: 'admin@labelx.internal',
    datasetScope: null,
  },
  {
    id: 'usr-qa-02',
    username: 'qalead',
    password: 'password123',
    fullName: 'Phạm QA Lead',
    role: 'qa_lead',
    email: 'qalead@labelx.internal',
    datasetScope: 'Road Vision Urban',
  },
  {
    id: 'usr-qc-03',
    username: 'qcadmin',
    password: 'password123',
    fullName: 'Hoàng QC Admin',
    role: 'qc_admin',
    email: 'qcadmin@labelx.internal',
    datasetScope: 'Road Vision Urban',
  },
  {
    id: 'usr-rv-04',
    username: 'reviewer',
    password: 'password123',
    fullName: 'Nguyễn Văn Review',
    role: 'reviewer',
    email: 'reviewer@labelx.internal',
    datasetScope: 'Road Vision Urban',
  },
  {
    id: 'usr-an-05',
    username: 'annotator',
    password: 'password123',
    fullName: 'Lê Thị Ghi Nhãn',
    role: 'annotator',
    email: 'annotator@labelx.internal',
    datasetScope: 'Road Vision Urban',
  },
];

export function findMockUser(username: string, password?: string): MockUserRecord | undefined {
  const u = MOCK_USERS.find(
    (item) => item.username.toLowerCase() === username.trim().toLowerCase()
  );
  if (!u) return undefined;
  if (password !== undefined && u.password !== password) {
    return undefined;
  }
  return u;
}
