import React from 'react';
import Link from 'next/link';
import { IngestionWorkflow } from '@/components/ingestion/IngestionWorkflow';

export const metadata = {
  title: 'Số Hóa Tủ Đồ - Multi-Agent Fashion Stylist',
  description: 'Tải lên và số hóa trang phục của bạn với sự hỗ trợ của thị giác máy tính AI.',
};

export default function WardrobePage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/30 to-slate-100 text-slate-800">
      {/* Navigation Header */}
      <header className="sticky top-0 z-40 w-full bg-white/80 backdrop-blur-md border-b border-slate-200/80 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-2 font-black text-lg tracking-tight text-indigo-600 hover:text-indigo-700 transition"
            >
              <span className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm font-bold shadow-md shadow-indigo-200">
                FS
              </span>
              <span>Fashion Stylist</span>
            </Link>
            <span className="text-slate-300">/</span>
            <span className="text-sm font-semibold text-slate-700">Tủ Đồ Cá Nhân</span>
          </div>

          <nav className="flex items-center gap-2 sm:gap-4">
            <Link
              href="/wardrobe"
              className="px-3.5 py-1.5 rounded-lg text-sm font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200/60"
            >
              Số Hóa Trang Phục
            </Link>
            <Link
              href="/chat"
              className="px-3.5 py-1.5 rounded-lg text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition"
            >
              Tư Vấn Stylist AI
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Workflow View */}
      <main className="max-w-7xl mx-auto py-6">
        <IngestionWorkflow />
      </main>
    </div>
  );
}
