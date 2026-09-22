import React from 'react';
import { AppHeader } from '@/components/navigation/AppHeader';
import { WardrobeView } from '@/components/wardrobe/WardrobeView';

export const metadata = {
  title: 'Tủ Đồ & Số Hóa - Multi-Agent Fashion Stylist',
  description: 'Quản lý tủ đồ cá nhân và số hóa trang phục của bạn với sự hỗ trợ của AI.',
};

export default function WardrobePage() {
  return (
    <div className="min-h-screen bg-[#FBFBF9] text-[#1A1918]">
      <AppHeader />

      {/* Main Workflow View */}
      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <WardrobeView />
      </main>
    </div>
  );
}
