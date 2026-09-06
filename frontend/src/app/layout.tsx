import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Multi-Agent Fashion Stylist",
  description: "Wardrobe-grounded outfit recommendations",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="vi">
      <body>{children}</body>
    </html>
  );
}
