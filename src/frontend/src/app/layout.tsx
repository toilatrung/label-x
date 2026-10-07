import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "@/styles/tokens.css";
import "@/styles/labelx.css";
import "./globals.css";
import { AuthProvider } from "@/lib/auth/auth-context";

// Design System LabelX: Inter cho mọi chữ, JetBrains Mono chỉ cho ID.
const inter = Inter({ variable: "--font-inter", subsets: ["latin", "vietnamese"] });
const jetbrainsMono = JetBrains_Mono({ variable: "--font-jetbrains-mono", subsets: ["latin"], weight: "500" });

export const metadata: Metadata = {
  title: "LabelX",
  description: "Quality Control cho annotation CVAT",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="vi" className={`${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="lx">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
