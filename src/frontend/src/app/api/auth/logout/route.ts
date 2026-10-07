import { NextResponse } from 'next/server';

export async function POST() {
  const response = NextResponse.json({ message: 'Đã đăng xuất thành công' }, { status: 200 });
  response.cookies.delete('lx_session');
  return response;
}
