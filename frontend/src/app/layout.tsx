import type { Metadata } from "next";
import { Be_Vietnam_Pro, Fraunces } from "next/font/google";

import "./globals.css";

const beVietnam = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-be-vietnam",
  display: "swap",
});

const fraunces = Fraunces({
  subsets: ["latin", "vietnamese"],
  axes: ["SOFT", "opsz"],
  variable: "--font-fraunces",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Fashion Stylist — Phối đồ từ tủ đồ của bạn",
    template: "%s · Fashion Stylist",
  },
  description:
    "Chụp ảnh quần áo bạn đang có, mô tả dịp và thời tiết, nhận bộ phối phù hợp từ chính tủ đồ của bạn.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi" className={`${beVietnam.variable} ${fraunces.variable}`}>
      <body className="min-h-screen bg-paper font-sans text-ink antialiased">{children}</body>
    </html>
  );
}
