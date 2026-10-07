import { NextResponse } from 'next/server';
import { MOCK_USERS } from '@/lib/auth/mock-users';
import { AuthUser } from '@/types/auth';

export async function GET(req: Request) {
  const cookieHeader = req.headers.get('cookie') || '';
  const match = cookieHeader.match(/lx_session=([^;]+)/);
  const userId = match ? match[1] : null;

  if (!userId) {
    return NextResponse.json(
      {
        code: 'UNAUTHORIZED',
        message: 'Chưa đăng nhập',
        request_id: 'req-' + Date.now(),
      },
      { status: 401 }
    );
  }

  const user = MOCK_USERS.find((u) => u.id === userId);
  if (!user) {
    return NextResponse.json(
      {
        code: 'UNAUTHORIZED',
        message: 'Phiên làm việc không tồn tại hoặc đã hết hạn',
        request_id: 'req-' + Date.now(),
      },
      { status: 401 }
    );
  }

  const safeUser: AuthUser = {
    id: user.id,
    username: user.username,
    fullName: user.fullName,
    role: user.role,
    email: user.email,
    datasetScope: user.datasetScope,
  };

  return NextResponse.json({ user: safeUser }, { status: 200 });
}
