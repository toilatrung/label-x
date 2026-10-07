import { NextResponse } from 'next/server';
import { findMockUser } from '@/lib/auth/mock-users';
import { AuthUser } from '@/types/auth';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { username, password } = body;

    if (!username || !password) {
      return NextResponse.json(
        {
          code: 'VALIDATION_ERROR',
          message: 'Tên đăng nhập và mật khẩu không được để trống',
          request_id: 'req-' + Date.now(),
        },
        { status: 400 }
      );
    }

    const matched = findMockUser(username, password);
    if (!matched) {
      return NextResponse.json(
        {
          code: 'UNAUTHORIZED',
          message: 'Tên đăng nhập hoặc mật khẩu không chính xác',
          request_id: 'req-' + Date.now(),
        },
        { status: 401 }
      );
    }

    const safeUser: AuthUser = {
      id: matched.id,
      username: matched.username,
      fullName: matched.fullName,
      role: matched.role,
      email: matched.email,
      datasetScope: matched.datasetScope,
    };

    const response = NextResponse.json(
      {
        user: safeUser,
        token: 'mock-session-token-' + safeUser.id,
      },
      { status: 200 }
    );

    response.cookies.set('lx_session', safeUser.id, {
      httpOnly: true,
      path: '/',
      sameSite: 'lax',
      maxAge: 86400,
    });

    return response;
  } catch {
    return NextResponse.json(
      {
        code: 'INTERNAL_ERROR',
        message: 'Lỗi xử lý yêu cầu xác thực',
        request_id: 'req-' + Date.now(),
      },
      { status: 500 }
    );
  }
}
