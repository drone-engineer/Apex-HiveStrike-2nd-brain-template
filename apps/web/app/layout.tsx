import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Apex HiveStrike Dashboard",
  description: "드론 2nd-Brain 볼트와 ULog 진단 대시보드",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-hive-bg antialiased">{children}</body>
    </html>
  );
}
