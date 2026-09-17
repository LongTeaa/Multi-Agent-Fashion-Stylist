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
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 h-18 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
            <Link
              href="/"
              className="flex items-center gap-2 font-serif text-lg tracking-tight font-medium text-[#1A1918] hover:text-[#9C5234] transition-colors"
            >
              <span className="w-8 h-8 rounded-full bg-[#1A1918] text-[#FBFBF9] flex items-center justify-center text-xs font-serif shadow-xs">
                FS
              </span>
              <span className="hidden sm:inline">Fashion Stylist</span>
            </Link>
            <span className="hidden text-[#D5D1C7] sm:inline">/</span>
            <span className="hidden text-xs font-mono tracking-wider uppercase text-[#736E65] md:inline">Tủ Đồ Cá Nhân</span>
          </div>

          <nav aria-label="Điều hướng tủ đồ" className="flex min-w-0 items-center gap-1 sm:gap-4">
            <Link
              href="/wardrobe"
              className="px-2.5 sm:px-3.5 py-1.5 rounded-full text-[10px] sm:text-xs font-mono uppercase tracking-wider text-[#9C5234] font-semibold bg-[#9C5234]/10 border border-[#9C5234]/20 whitespace-nowrap"
            >
              <span className="sm:hidden">Số hóa</span>
              <span className="hidden sm:inline">Số Hóa Trang Phục</span>
            </Link>
            <Link
              href="/saved"
              className="hidden sm:inline-flex px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition-colors"
            >
              Đã Lưu
            </Link>
            <Link
              href="/chat"
              className="tactile-btn group inline-flex items-center gap-1.5 pl-3 sm:pl-4 pr-1.5 py-1.5 rounded-full bg-[#1A1918] text-[#FBFBF9] hover:bg-[#2D2420] text-[10px] sm:text-xs font-mono uppercase tracking-wider shadow-xs whitespace-nowrap"
            >
              <span className="sm:hidden">Tư vấn</span>
              <span className="hidden sm:inline">Tư Vấn Stylist</span>
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
