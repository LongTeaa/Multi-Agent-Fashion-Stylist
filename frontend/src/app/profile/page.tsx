import React from 'react';
import { AppHeader } from '@/components/navigation/AppHeader';
import { ProfilePreferencesForm } from '@/components/profile/ProfilePreferencesForm';

export const metadata = {
  title: 'Gu Thời Trang & Sở Thích - Multi-Agent Fashion Stylist',
  description: 'Chọn phong cách, bảng màu và ưu tiên phối đồ của bạn.',
};

export default function ProfilePage() {
  return (
    <div className="min-h-screen bg-[#FBFBF9] text-[#1A1918]">
      <AppHeader />

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

