import React from 'react';
import Link from 'next/link';

import { ProfilePreferencesForm } from '@/components/profile/ProfilePreferencesForm';

export const metadata = {
  title: 'Gu Thời Trang & Sở Thích - Multi-Agent Fashion Stylist',
  description: 'Chọn phong cách, bảng màu và ưu tiên phối đồ của bạn.',
};

export default function ProfilePage() {
  return (
    <div className="min-h-screen bg-[#FBFBF9] text-[#1A1918]">
      {/* Sticky Navigation Header */}
      <header className="sticky top-0 z-40 w-full bg-[#FBFBF9]/90 backdrop-blur-md border-b border-[#E8E5DE]">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-18 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-2 font-serif text-lg tracking-tight font-medium text-[#1A1918] hover:text-[#9C5234] transition-colors"
            >
              <span className="w-8 h-8 rounded-full bg-[#1A1918] text-[#FBFBF9] flex items-center justify-center text-xs font-serif shadow-xs">
                FS
              </span>
              <span>Fashion Stylist</span>
            </Link>
            <span className="text-[#D5D1C7]">/</span>
            <span className="text-xs font-mono tracking-wider uppercase text-[#736E65]">
              Gu Thời Trang
            </span>
          </div>

          <nav className="flex items-center gap-2 sm:gap-3">
            <Link
              href="/chat"
              className="px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition-colors"
            >
              Tư Vấn Stylist
            </Link>
            <Link
              href="/saved"
              className="px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition-colors"
            >
              Đã Lưu
            </Link>
            <Link
              href="/wardrobe"
              className="px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition-colors"
            >
              Tủ Đồ
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-4 py-8 sm:py-10 space-y-8">
        <header className="space-y-2">
          <span className="text-xs font-mono uppercase tracking-widest text-[#9C5234] block">
            Aesthetic Preferences
          </span>
          <h1 className="font-serif text-3xl sm:text-4xl font-normal tracking-tight text-[#1A1918]">
            Sở thích phong cách
          </h1>
          <p className="text-sm text-[#5C564E] leading-relaxed max-w-xl">
            Chọn các lựa chọn phù hợp để hệ thống ưu tiên trang phục trong tủ đồ của bạn. Bạn có thể bỏ qua hoặc chỉnh sửa bất cứ lúc nào.
          </p>
        </header>

        <ProfilePreferencesForm />
      </main>
    </div>
  );
}

