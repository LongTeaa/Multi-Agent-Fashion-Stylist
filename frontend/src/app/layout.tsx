import type { Metadata } from "next";
import { Playfair_Display, Plus_Jakarta_Sans, Geist_Mono } from "next/font/google";

import "./globals.css";

const playfair = Playfair_Display({
  subsets: ["latin", "vietnamese"],
  variable: "--font-serif",
  display: "swap",
});

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin", "vietnamese"],
  variable: "--font-sans",
  display: "swap",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Multi-Agent Fashion Stylist | Trợ Lý Phối Đồ Cá Nhân Hóa",
  description: "Trợ lý thời trang đa tác nhân thông minh với khả năng số hóa tủ đồ từ ảnh chụp thực tế và gợi ý trang phục chuẩn quy luật thẩm mỹ.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="vi"
      className={`${playfair.variable} ${plusJakarta.variable} ${geistMono.variable}`}
    >
      <body className="min-h-screen bg-[#FBFBF9] text-[#1A1918] font-sans antialiased selection:bg-[#E8DFD8] selection:text-[#1A1918]">
        {children}
      </body>
    </html>
  );
}
