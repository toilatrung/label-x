import type { Metadata } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import '@/styles/tokens.css';
import '@/styles/labelx.css';
import './globals.css';
import { AuthProvider } from '@/lib/auth/auth-context';

const inter = Inter({ variable: '--font-inter', subsets: ['latin', 'vietnamese'] });
const jetbrainsMono = JetBrains_Mono({ variable: '--font-jetbrains-mono', subsets: ['latin'], weight: '500' });

export const metadata: Metadata = {
  title: 'LabelX - Quality Control cho Annotation CVAT',
  description: 'Hệ thống kiểm soát chất lượng dữ liệu gán nhãn cho CVAT',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="lx">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
