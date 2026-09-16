import React from 'react';
import Link from 'next/link';
import { IngestionWorkflow } from '@/components/ingestion/IngestionWorkflow';

export const metadata = {
  title: 'Số Hóa Tủ Đồ - Multi-Agent Fashion Stylist',
  description: 'Tải lên và số hóa trang phục của bạn với sự hỗ trợ của thị giác máy tính AI.',
};

export default function WardrobePage() {
  return (
    <div className="min-h-screen bg-[#FBFBF9] text-[#1A1918]">
      {/* Navigation Header */}
      <header className="sticky top-0 z-40 w-full bg-[#FBFBF9]/90 backdrop-blur-md border-b border-[#E8E5DE]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-18 flex items-center justify-between">
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
            <span className="text-xs font-mono tracking-wider uppercase text-[#736E65]">Tủ Đồ Cá Nhân</span>
          </div>

          <nav className="flex items-center gap-2 sm:gap-4">
            <Link
              href="/wardrobe"
              className="px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#9C5234] font-semibold bg-[#9C5234]/10 border border-[#9C5234]/20"
            >
              Số Hóa Trang Phục
            </Link>
            <Link
              href="/saved"
              className="px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition-colors"
            >
              Đã Lưu
            </Link>
            <Link
              href="/chat"
              className="tactile-btn group inline-flex items-center gap-2 pl-4 pr-1.5 py-1.5 rounded-full bg-[#1A1918] text-[#FBFBF9] hover:bg-[#2D2420] text-xs font-mono uppercase tracking-wider shadow-xs"
            >
              <span>Tư Vấn Stylist</span>
              <span className="w-5 h-5 rounded-full bg-white/15 flex items-center justify-center group-hover:translate-x-0.5 transition-all text-xs">
                →
              </span>
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Workflow View */}
      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <IngestionWorkflow />
      </main>
    </div>
  );
}
