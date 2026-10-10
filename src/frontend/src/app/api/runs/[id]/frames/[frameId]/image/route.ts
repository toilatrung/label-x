import { NextResponse } from 'next/server';
import { isMockAuth } from '@/lib/auth/config';

const fixtureImages: Record<string, string> = {
  '101': '/demo/frame-001.png',
  '102': '/demo/frame-002.png',
  '103': '/demo/frame-003.png',
};

// DEMO-ONLY: fixture media proxy used only while NEXT_PUBLIC_AUTH_MODE=mock.
export async function GET(request: Request, context: { params: Promise<{ id: string; frameId: string }> }) {
  const { id, frameId } = await context.params;
  const imagePath = fixtureImages[frameId];
  if (!isMockAuth || id !== '1' || !imagePath) {
    return NextResponse.json({ code: 'NOT_FOUND', message: 'Ảnh frame không tồn tại.' }, { status: 404 });
  }
  return NextResponse.redirect(new URL(imagePath, request.url));
}
