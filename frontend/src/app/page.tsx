import React from 'react';
import Link from 'next/link';

export const metadata = {
  title: 'Multi-Agent Fashion Stylist - Nền Tảng Phối Đồ Cá Nhân Hóa',
  description: 'Trợ lý thời trang đa tác nhân thông minh với khả năng số hóa tủ đồ từ ảnh chụp thực tế.',
};

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-indigo-950 text-white">
      {/* Header */}
      <header className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/30">
            FS
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight">Fashion Stylist AI</h1>
            <p className="text-[11px] text-slate-400">Multi-Agent Wardrobe Intelligence</p>
          </div>
        </div>

        <nav className="flex items-center gap-3 sm:gap-4">
          <Link
            href="/profile"
            className="px-3 py-2 text-sm font-semibold text-slate-300 hover:text-white transition"
          >
            Sở thích
          </Link>
          <Link
            href="/wardrobe"
            className="px-4 py-2 rounded-xl text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 transition shadow-lg shadow-indigo-600/30"
          >
            Số Hóa Tủ Đồ →
          </Link>
        </nav>
      </header>

      {/* Hero Section */}
      <main className="max-w-5xl mx-auto px-4 pt-16 pb-24 text-center">
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs font-medium mb-6">
          <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse"></span>
          <span>Hệ Thống Phối Đồ Đa Tác Nhân Thông Minh</span>
        </div>

        <h2 className="text-4xl sm:text-6xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white via-indigo-100 to-indigo-400 max-w-3xl mx-auto leading-tight">
          Biến Mọi Món Đồ Trong Tủ Của Bạn Thành Trang Phục Hoàn Hảo
        </h2>

        <p className="mt-6 text-base sm:text-lg text-slate-300 max-w-2xl mx-auto leading-relaxed">
          Tải ảnh quần áo bạn sở hữu lên hệ thống. AI sẽ tự động tách từng món, trích xuất chất liệu, phom dáng, phong cách và phối đồ phù hợp với từng bối cảnh thực tế.
        </p>

        {/* Feature Cards Grid */}
        <div className="mt-14 grid grid-cols-1 md:grid-cols-3 gap-6 text-left">
          {/* Card 1 */}
          <Link
            href="/wardrobe"
            className="group p-6 rounded-2xl bg-white/5 border border-white/10 hover:border-indigo-500/50 hover:bg-white/[0.08] transition duration-200 block shadow-xl"
          >
            <div className="w-12 h-12 rounded-xl bg-indigo-600/20 text-indigo-400 flex items-center justify-center mb-4 group-hover:scale-110 transition-transform">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-white group-hover:text-indigo-300 transition">
              1. Số Hóa Tủ Đồ (Ingestion)
            </h3>
            <p className="mt-2 text-sm text-slate-400">
              Kéo thả ảnh chụp phẳng hoặc ảnh OOTD. AI tự động phát hiện từng món đồ, cắt khung và cho phép bạn kiểm duyệt trước khi lưu.
            </p>
            <div className="mt-4 text-xs font-semibold text-indigo-400 flex items-center gap-1 group-hover:translate-x-1 transition-transform">
              <span>Bắt đầu số hóa</span>
              <span>→</span>
            </div>
          </Link>

          {/* Card 2 */}
          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 opacity-80 block shadow-xl">
            <div className="w-12 h-12 rounded-xl bg-purple-600/20 text-purple-400 flex items-center justify-center mb-4">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-white">2. Phối Đồ Cá Nhân Hóa</h3>
            <p className="mt-2 text-sm text-slate-400">
              Tác nhân điều phối kết hợp quy luật thẩm mỹ, thời tiết và hoàn cảnh để tạo ra các set đồ độc bản từ chính quần áo bạn có.
            </p>
          </div>

          {/* Card 3 */}
          <div className="p-6 rounded-2xl bg-white/5 border border-white/10 opacity-80 block shadow-xl">
            <div className="w-12 h-12 rounded-xl bg-emerald-600/20 text-emerald-400 flex items-center justify-center mb-4">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <h3 className="text-lg font-bold text-white">3. Bảo Mật & Riêng Tư</h3>
            <p className="mt-2 text-sm text-slate-400">
              Mọi hình ảnh được lưu trữ trong Object Storage riêng biệt và chỉ có bạn mới có quyền truy cập thông qua Signed URL bảo mật.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
