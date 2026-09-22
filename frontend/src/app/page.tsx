'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';

interface GarmentHotspot {
  id: string;
  name: string;
  shortLabel: string;
  category: string;
  material: string;
  style: string;
  palette: string;
  areaStyle: { top: string; left: string; width: string; height: string };
  description: string;
}

const HERO_HOTSPOTS: GarmentHotspot[] = [
  {
    id: 'top-linen',
    name: 'Áo Sơ Mi Linen Trắng Kem',
    shortLabel: 'Sơ Mi Linen',
    category: 'Tops · Phom Relaxed',
    material: '100% Linen dệt thoáng khí tự nhiên',
    style: 'Tối giản / Resort Casual',
    palette: 'Chalk White · #F7F5F0',
    areaStyle: { top: '8%', left: '16%', width: '34%', height: '82%' },
    description: 'Cắt may relaxed với độ rủ tự nhiên, tạo cảm giác thoáng mát và thanh lịch cho ngày nắng ấm.',
  },
  {
    id: 'bottom-trousers',
    name: 'Quần Âu Xếp Ly Than Chì',
    shortLabel: 'Quần Âu Xếp Ly',
    category: 'Bottoms · Regular Straight',
    material: 'Len pha Wool-blend cao cấp',
    style: 'Sartorial / Smart Casual',
    palette: 'Charcoal Grey · #3D4043',
    areaStyle: { top: '8%', left: '50%', width: '24%', height: '46%' },
    description: 'Chi tiết xếp ly đôi phong cách cổ điển, ống đứng vừa vặn che khuyết điểm và tôn dáng.',
  },
  {
    id: 'shoes-loafers',
    name: 'Penny Loafers Da Bóng Espresso',
    shortLabel: 'Loafers Da Bóng',
    category: 'Footwear · Da bóng khâu tay',
    material: 'Full-grain Calfskin leather',
    style: 'Heritage / Timeless Classic',
    palette: 'Espresso Brown · #2D1E18',
    areaStyle: { top: '55%', left: '50%', width: '35%', height: '40%' },
    description: 'Đế da khâu Goodyear bền bỉ, sắc nâu cà phê đậm đà kết nối hoàn hảo giữa áo sáng và quần trầm.',
  },
  {
    id: 'acc-watch-glasses',
    name: 'Phụ Kiện Kính & Đồng Hồ Cổ Điển',
    shortLabel: 'Kính & Đồng Hồ',
    category: 'Accessories · Điểm nhấn hoàn thiện',
    material: 'Tortoise Acetate & Vỏ đồng chải xước',
    style: 'Vintage Intellectual',
    palette: 'Warm Tortoise · Amber Gold',
    areaStyle: { top: '14%', left: '72%', width: '16%', height: '42%' },
    description: 'Chi tiết tinh tế giúp nâng tầm tổng thể trang phục mà không gây cảm giác phô trương.',
  },
];

interface CuratedLook {
  id: string;
  title: string;
  persona: string;
  context: string;
  weather: string;
  colorSwatches: string[];
  top: string;
  bottom: string;
  footwear: string;
  stylistNote: string;
}

const CURATED_LOOKS: CuratedLook[] = [
  {
    id: 'look-1',
    title: 'Cafe Cuối Tuần Tối Giản',
    persona: 'Minimalist Leisure',
    context: 'Gặp gỡ bạn bè, dạo phố buổi sáng',
    weather: '24°C · Nắng dịu nhẹ',
    colorSwatches: ['#F7F5F0', '#3D4043', '#2D1E18'],
    top: 'Áo sơ mi linen cổ bẻ thư thái',
    bottom: 'Quần âu xếp ly than chì phom đứng',
    footwear: 'Penny Loafers da mộc nâu sẫm',
    stylistNote: 'Sự tương phản nhẹ giữa chất liệu linen thô mộc và da bóng tạo chiều sâu thị giác tự nhiên mà không cần phụ kiện cầu kỳ.',
  },
  {
    id: 'look-2',
    title: 'Họp Văn Phòng & Sự Kiện Thu',
    persona: 'Contemporary Sartorial',
    context: 'Thuyết trình dự án, gặp gỡ đối tác',
    weather: '21°C · Se lạnh thoáng đãng',
    colorSwatches: ['#E8E0D5', '#242526', '#8A5836'],
    top: 'Blazer dệt kim len mỏng màu be cát',
    bottom: 'Quần tây lụa pha len đen mờ',
    footwear: 'Derby da mờ màu da bò sẫm',
    stylistNote: 'Tỷ lệ phom dáng cân đối giúp toát lên vẻ chỉn chu tuyệt đối nhưng vẫn đem lại sự dễ chịu suốt cả ngày dài làm việc.',
  },
  {
    id: 'look-3',
    title: 'Dạ Tiệc Tối Ấm Áp Lãng Mạn',
    persona: 'Nocturne Elegance',
    context: 'Bữa tối thân mật, không gian lounge ánh vàng',
    weather: '19°C · Gió lạnh về đêm',
    colorSwatches: ['#121110', '#9C5234', '#D4C9BC'],
    top: 'Áo măng-tô dạ dáng dài đen tuyền',
    bottom: 'Chân váy lụa satin rủ mềm / Quần âu slim',
    footwear: 'Chelsea boots da bóng mũi nhọn',
    stylistNote: 'Tông màu than chì phối cùng điểm nhấn Terracotta ánh ấm phản chiếu ánh đèn vàng, mang lại vẻ lôi cuốn đầy chất thơ.',
  },
];

export default function Home() {
  const [activeHotspot, setActiveHotspot] = useState<GarmentHotspot | null>(HERO_HOTSPOTS[0]);
  const [hoveredSpotId, setHoveredSpotId] = useState<string | null>(null);
  const [activeLookIndex, setActiveLookIndex] = useState<number>(0);

  const activeLook = CURATED_LOOKS[activeLookIndex];

  return (
    <div className="min-h-screen bg-[#FBFBF9] text-[#1A1918] selection:bg-[#E8DFD8] relative overflow-x-hidden">
      {/* Subtle Ambient Radial Glow */}
      <div
        className="pointer-events-none fixed inset-0 z-0 opacity-70"
        style={{
          background: 'radial-gradient(circle at 50% -5%, rgba(228, 218, 203, 0.45) 0%, rgba(251, 251, 249, 0) 65%)',
        }}
        aria-hidden="true"
      />

      {/* Floating Fluid Island Navigation (Soft-skill Section 5.A) */}
      <header className="fixed top-5 left-1/2 -translate-x-1/2 z-50 w-[94%] max-w-5xl rounded-full border border-[#1A1918]/[0.08] bg-[#FBFBF9]/80 backdrop-blur-xl shadow-lg shadow-black/[0.03] px-4 sm:px-6 py-2.5 flex items-center justify-between transition-all">
        <Link href="/" className="flex items-center gap-3 group">
          <span className="w-8 h-8 rounded-full bg-[#1A1918] text-[#FBFBF9] flex items-center justify-center font-serif text-xs tracking-wider group-hover:scale-105 group-hover:bg-[#9C5234] transition-all duration-300">
            FS
          </span>
          <div className="flex items-baseline gap-2">
            <span className="font-serif text-base tracking-tight font-medium text-[#1A1918]">
              Fashion Stylist
            </span>
            <span className="hidden sm:inline-block text-[9px] font-mono tracking-widest uppercase text-[#736E65]">
              AI Studio
            </span>
          </div>
        </Link>

        <nav aria-label="Điều hướng chính" className="flex items-center gap-1 sm:gap-4 md:gap-5">
          <Link
            href="/wardrobe"
            className="text-xs sm:text-sm font-medium text-[#5C564E] hover:text-[#1A1918] transition-colors px-2 py-1"
          >
            Tủ Đồ
          </Link>
          <Link
            href="/chat"
            className="text-xs sm:text-sm font-medium text-[#5C564E] hover:text-[#1A1918] transition-colors px-2 py-1"
          >
            Tư Vấn Phối Đồ
          </Link>
          <Link
            href="/saved"
            className="text-xs sm:text-sm font-medium text-[#5C564E] hover:text-[#1A1918] transition-colors px-2 py-1"
          >
            Bộ Đồ Đã Lưu
          </Link>
          <Link
            href="/profile"
            className="hidden md:inline-block text-xs sm:text-sm font-medium text-[#5C564E] hover:text-[#1A1918] transition-colors px-2 py-1"
          >
            Gu Thời Trang
          </Link>

          {/* Button-in-Button Primary CTA */}
          <Link
            href="/chat"
            className="tactile-btn group inline-flex items-center gap-2.5 pl-4 pr-1.5 py-1.5 rounded-full bg-[#1A1918] text-[#FBFBF9] hover:bg-[#2D2420] text-xs font-mono uppercase tracking-wider shadow-xs"
          >
            <span>Khám Phá</span>
            <span className="w-6 h-6 rounded-full bg-white/15 flex items-center justify-center group-hover:translate-x-0.5 group-hover:bg-white/25 transition-all">
              →
            </span>
          </Link>
        </nav>
      </header>

      {/* Main Container */}
      <main className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pt-28 sm:pt-36 pb-28">
        {/* Hero Section */}
        <section className="text-center max-w-4xl mx-auto">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-[#D5D1C7] bg-white/60 backdrop-blur-xs text-[#736E65] text-[10px] font-mono tracking-[0.2em] uppercase mb-8 shadow-2xs">
            <span className="w-1.5 h-1.5 rounded-full bg-[#9C5234] animate-pulse"></span>
            <span>Multi-Agent Wardrobe Intelligence</span>
          </div>

          <h1 className="font-serif text-4xl sm:text-6xl lg:text-7xl font-normal tracking-tight text-[#1A1918] leading-[1.08]">
            Nghệ thuật phối đồ từ chính tủ quần áo của bạn
          </h1>

          <p className="mt-6 text-base sm:text-lg text-[#5C564E] leading-relaxed max-w-2xl mx-auto">
            Số hóa trang phục từ ảnh chụp thực tế. Hệ thống đa tác nhân giải bài toán phong cách mỗi ngày theo quy luật thẩm mỹ, chất liệu vải và hoàn cảnh thời tiết.
          </p>

          {/* Action CTAs with Button-in-Button Architecture (Soft-skill Section 4.B) */}
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/chat"
              className="tactile-btn group inline-flex items-center gap-4 pl-7 pr-2.5 py-2.5 rounded-full bg-[#1A1918] text-[#FBFBF9] hover:bg-[#2D2420] font-medium text-sm shadow-sm"
            >
              <span>Bắt Đầu Tư Vấn Phối Đồ</span>
              <span className="w-8 h-8 rounded-full bg-white/15 flex items-center justify-center group-hover:translate-x-1 group-hover:-translate-y-0.5 group-hover:bg-white/25 transition-all">
                ↗
              </span>
            </Link>

            <Link
              href="/wardrobe"
              className="tactile-btn inline-flex items-center gap-2 px-6 py-3.5 rounded-full bg-white border border-[#D5D1C7] text-[#1A1918] hover:bg-[#F5F4F0] font-medium text-sm transition-colors shadow-2xs"
            >
              <span>Số Hóa Tủ Đồ Số</span>
            </Link>
          </div>
        </section>

        {/* Double-Bezel Interactive Lookbook Stage (Soft-skill Section 4.A + Taste-skill 4.8) */}
        <section className="mt-14 sm:mt-20">
          <div className="double-bezel-shell">
            <div className="double-bezel-core overflow-hidden relative border border-[#E8E5DE]">
              {/* Header Bar of Stage */}
              <div className="px-6 py-4 border-b border-[#E8E5DE] bg-[#FBFBF9]/90 backdrop-blur-md flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono text-[#736E65]">
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#9C5234]"></span>
                  <span className="uppercase tracking-widest text-[#1A1918] font-semibold">
                    Studio Lookbook
                  </span>
                  <span className="hidden sm:inline text-[#D5D1C7]">/</span>
                  <span className="hidden sm:inline text-[#736E65]">Rê chuột lên trang phục hoặc chọn danh mục bên dưới</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-white border border-[#E8E5DE] text-[#736E65]">
                    AI Vision Grounded
                  </span>
                </div>
              </div>

              {/* Stage Image with Invisible Hover Zones (No Ugly Dots) */}
              <div className="relative aspect-16/9 sm:aspect-16/9 w-full bg-[#EAE8E1]/30 overflow-hidden select-none">
                <Image
                  src="/images/hero-flatlay.jpg"
                  alt="High-end editorial fashion flat-lay with linen shirt, tailored pleated trousers, and loafers"
                  fill
                  className="object-cover object-center transform transition-transform duration-700 ease-out"
                  priority
                />

                {/* Invisible Hover Zones covering each garment area */}
                {HERO_HOTSPOTS.map((spot) => {
                  const isHovered = hoveredSpotId === spot.id;

                  return (
                    <div
                      key={spot.id}
                      style={spot.areaStyle}
                      onMouseEnter={() => {
                        setHoveredSpotId(spot.id);
                        setActiveHotspot(spot);
                      }}
                      onMouseLeave={() => {
                        setHoveredSpotId(null);
                      }}
                      onClick={() => setActiveHotspot(spot)}
                      className="absolute cursor-pointer z-20 group/garment"
                      aria-label={`Chi tiết ${spot.name}`}
                    >
                      {/* Subtle elegant glass highlight on hover only */}
                      <div
                        className={`absolute inset-0 rounded-3xl transition-all duration-300 pointer-events-none ${
                          isHovered
                            ? 'bg-white/10 ring-1 ring-white/60 backdrop-blur-[1px] shadow-sm'
                            : 'bg-transparent ring-0'
                        }`}
                      />

                      {/* Micro hover pill label that appears smoothly only when hovering */}
                      <div
                        className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 transition-all duration-300 pointer-events-none z-30 ${
                          isHovered ? 'opacity-100 scale-100' : 'opacity-0 scale-90'
                        }`}
                      >
                        <div className="px-3.5 py-1.5 rounded-full bg-[#1A1918]/85 text-[#FBFBF9] backdrop-blur-md text-[11px] font-mono tracking-wider shadow-xl flex items-center gap-2 whitespace-nowrap">
                          <span className="w-1.5 h-1.5 rounded-full bg-[#9C5234]"></span>
                          <span>{spot.name}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Floating Garment Inspector Badge Overlay */}
                {activeHotspot && (
                  <div className="absolute bottom-4 left-4 sm:bottom-6 sm:left-6 z-30 max-w-sm w-[calc(100%-2rem)] sm:w-auto bg-[#FBFBF9]/95 backdrop-blur-md rounded-2xl p-4 sm:p-5 border border-[#E8E5DE] shadow-xl animate-fadeIn">
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="text-[10px] font-mono uppercase tracking-widest text-[#9C5234] font-semibold">
                        {activeHotspot.category}
                      </span>
                      <span className="text-[10px] font-mono text-[#736E65] px-2 py-0.5 rounded bg-[#F5F4F0]">
                        {activeHotspot.palette}
                      </span>
                    </div>
                    <h2 className="font-serif text-base sm:text-lg font-medium text-[#1A1918] leading-tight">
                      {activeHotspot.name}
                    </h2>
                    <p className="mt-1 text-xs text-[#5C564E] leading-relaxed">
                      {activeHotspot.description}
                    </p>
                    <div className="mt-2.5 pt-2 border-t border-[#E8E5DE] flex items-center justify-between text-[11px] font-mono text-[#736E65]">
                      <span>{activeHotspot.material}</span>
                      <span className="text-[#9C5234] font-medium">{activeHotspot.style}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Elegant Garment Selector Bar below the image */}
              <div className="px-6 py-3.5 bg-[#FBFBF9] border-t border-[#E8E5DE] flex flex-wrap items-center justify-between gap-3 text-xs">
                <div className="flex items-center gap-2 font-mono text-[11px] text-[#736E65]">
                  <span>Chi tiết danh mục:</span>
                </div>
                <div className="flex flex-wrap gap-2">
                  {HERO_HOTSPOTS.map((spot, idx) => {
                    const isCurrent = activeHotspot?.id === spot.id;
                    return (
                      <button
                        key={spot.id}
                        type="button"
                        onMouseEnter={() => {
                          setHoveredSpotId(spot.id);
                          setActiveHotspot(spot);
                        }}
                        onMouseLeave={() => setHoveredSpotId(null)}
                        onClick={() => setActiveHotspot(spot)}
                        className={`tactile-btn px-3.5 py-1.5 rounded-full text-xs font-mono transition-all ${
                          isCurrent
                            ? 'bg-[#1A1918] text-[#FBFBF9] shadow-xs'
                            : 'bg-white text-[#5C564E] border border-[#E8E5DE] hover:border-[#D5D1C7] hover:text-[#1A1918]'
                        }`}
                      >
                        0{idx + 1}. {spot.shortLabel}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Asymmetrical Architectural Bento Grid (Soft-skill Section 3.B.1) */}
        <section className="mt-24 sm:mt-32">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Tile 1 (Large 7 Columns) */}
            <div className="lg:col-span-7 double-bezel-shell">
              <div className="double-bezel-core p-8 sm:p-10 h-full flex flex-col justify-between border border-[#E8E5DE]">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#9C5234] font-semibold">
                      01 / Vision Segmentation
                    </span>
                    <span className="text-xs font-mono px-3 py-1 rounded-full bg-[#F5F4F0] text-[#736E65] border border-[#E8E5DE]">
                      Tách Nền Tự Động
                    </span>
                  </div>

                  <h2 className="font-serif text-2xl sm:text-3xl font-normal text-[#1A1918] tracking-tight">
                    Số Hóa Tủ Đồ Không Cần Studio Chuyên Nghiệp
                  </h2>

                  <p className="mt-3 text-sm sm:text-base text-[#5C564E] leading-relaxed">
                    Bạn chỉ cần chụp phẳng trên sàn hoặc chụp trang phục thường ngày. Tác nhân thị giác máy tính sẽ tự động cô lập từng chiếc áo, quần, váy và bóc tách cấu trúc vải để lập chỉ mục tủ đồ cá nhân.
                  </p>
                </div>

                {/* Micro Visual Showcase */}
                <div className="mt-8 pt-6 border-t border-[#F5F4F0] grid grid-cols-3 gap-3">
                  <div className="p-3 rounded-2xl bg-[#FBFBF9] border border-[#E8E5DE] text-center">
                    <span className="text-[10px] font-mono uppercase text-[#736E65] block mb-1">Detect</span>
                    <span className="text-xs font-medium text-[#1A1918] block">Phân Vùng Đồ</span>
                    <span className="text-[10px] font-mono text-[#9C5234]">Tops / Bottoms</span>
                  </div>
                  <div className="p-3 rounded-2xl bg-[#FBFBF9] border border-[#E8E5DE] text-center">
                    <span className="text-[10px] font-mono uppercase text-[#736E65] block mb-1">Extract</span>
                    <span className="text-xs font-medium text-[#1A1918] block">Trích Xuất Vải</span>
                    <span className="text-[10px] font-mono text-[#9C5234]">Linen, Wool, Denim</span>
                  </div>
                  <div className="p-3 rounded-2xl bg-[#FBFBF9] border border-[#E8E5DE] text-center">
                    <span className="text-[10px] font-mono uppercase text-[#736E65] block mb-1">Verify</span>
                    <span className="text-xs font-medium text-[#1A1918] block">Kiểm Duyệt</span>
                    <span className="text-[10px] font-mono text-[#9C5234]">Chính xác 100%</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Tile 2 (5 Columns) */}
            <div className="lg:col-span-5 double-bezel-shell">
              <div className="double-bezel-core p-8 sm:p-10 h-full flex flex-col justify-between border border-[#E8E5DE] bg-gradient-to-br from-white via-white to-[#F5F4F0]">
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#9C5234] font-semibold">
                      02 / Context Reasoning
                    </span>
                    <span className="w-2 h-2 rounded-full bg-[#9C5234]"></span>
                  </div>

                  <h2 className="font-serif text-2xl sm:text-3xl font-normal text-[#1A1918] tracking-tight">
                    Tư Vấn Đúng Bối Cảnh & Nhiệt Độ
                  </h2>

                  <p className="mt-3 text-sm text-[#5C564E] leading-relaxed">
                    Hệ thống phối hợp tác nhân thời tiết và tác nhân phong cách. Nếu trời Đà Lạt 18°C, hệ thống ưu tiên len hoặc dạ ấm; nếu trời Sài Gòn 33°C, ưu tiên vải đũi, cotton thoáng khí.
                  </p>
                </div>

                <div className="mt-6 flex flex-wrap gap-2 pt-4 border-t border-[#E8E5DE]">
                  <span className="px-3 py-1 rounded-full bg-white border border-[#E8E5DE] text-[#1A1918] text-xs font-mono">
                    Hà Nội · 22°C
                  </span>
                  <span className="px-3 py-1 rounded-full bg-white border border-[#E8E5DE] text-[#1A1918] text-xs font-mono">
                    Smart Casual
                  </span>
                  <span className="px-3 py-1 rounded-full bg-white border border-[#E8E5DE] text-[#1A1918] text-xs font-mono">
                    Monochrome
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Interactive Curated Lookbook Studio (Taste-skill Section 12) */}
        <section className="mt-28 sm:mt-36">
          <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-[#9C5234] font-semibold block mb-2">
                Lookbook Atelier
              </span>
              <h2 className="font-serif text-3xl sm:text-4xl font-normal text-[#1A1918] tracking-tight">
                Không Gian Trải Nghiệm Phối Đồ Trực Quan
              </h2>
            </div>

            {/* Persona Switcher Tabs */}
            <div className="flex items-center gap-1.5 p-1 rounded-full bg-[#F5F4F0] border border-[#E8E5DE]">
              {CURATED_LOOKS.map((look, idx) => {
                const isActive = activeLookIndex === idx;
                return (
                  <button
                    key={look.id}
                    type="button"
                    onClick={() => setActiveLookIndex(idx)}
                    className={`tactile-btn px-4 py-2 rounded-full text-xs font-mono uppercase tracking-wider transition ${
                      isActive
                        ? 'bg-[#1A1918] text-[#FBFBF9] shadow-xs'
                        : 'text-[#5C564E] hover:text-[#1A1918]'
                    }`}
                  >
                    #{idx + 1}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Look Interactive Card */}
          <div className="double-bezel-shell">
            <div className="double-bezel-core p-6 sm:p-10 border border-[#E8E5DE]">
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
                {/* Information Column */}
                <div className="lg:col-span-7 space-y-5">
                  <div className="flex items-center gap-3">
                    <span className="px-3 py-1 rounded-full text-[10px] font-mono uppercase tracking-wider bg-[#F5F4F0] text-[#736E65] border border-[#E8E5DE]">
                      {activeLook.persona}
                    </span>
                    <span className="text-xs font-mono text-[#9C5234]">{activeLook.weather}</span>
                  </div>

                  <h3 className="font-serif text-2xl sm:text-3xl font-normal text-[#1A1918]">
                    {activeLook.title}
                  </h3>

                  <p className="text-sm text-[#5C564E] leading-relaxed">
                    {activeLook.stylistNote}
                  </p>

                  {/* Garment Breakdown */}
                  <div className="space-y-2.5 pt-2">
                    <div className="flex items-center justify-between text-xs py-2 border-b border-[#F5F4F0]">
                      <span className="font-mono text-[#736E65] uppercase">Áo (Top):</span>
                      <span className="font-medium text-[#1A1918]">{activeLook.top}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs py-2 border-b border-[#F5F4F0]">
                      <span className="font-mono text-[#736E65] uppercase">Quần (Bottom):</span>
                      <span className="font-medium text-[#1A1918]">{activeLook.bottom}</span>
                    </div>
                    <div className="flex items-center justify-between text-xs py-2 border-b border-[#F5F4F0]">
                      <span className="font-mono text-[#736E65] uppercase">Giày (Footwear):</span>
                      <span className="font-medium text-[#1A1918]">{activeLook.footwear}</span>
                    </div>
                  </div>

                  {/* Color Harmony Palette */}
                  <div className="pt-2 flex items-center gap-3">
                    <span className="text-[11px] font-mono text-[#736E65] uppercase tracking-wider">
                      Bảng Màu Hài Hòa:
                    </span>
                    <div className="flex gap-2">
                      {activeLook.colorSwatches.map((color, cIdx) => (
                        <span
                          key={cIdx}
                          style={{ backgroundColor: color }}
                          className="w-5 h-5 rounded-full border border-black/10 shadow-2xs block"
                          title={color}
                        />
                      ))}
                    </div>
                  </div>
                </div>

                {/* Visual Editorial Model Showcase Column */}
                <div className="lg:col-span-5 relative rounded-2xl overflow-hidden border border-[#E8E5DE] shadow-md group">
                  <div className="relative aspect-3/4 w-full bg-[#EAE8E1]">
                    <Image
                      src="/images/model-lookbook.jpg"
                      alt="Editorial model wearing styled trench coat and pleated trousers in Paris"
                      fill
                      className="object-cover object-center group-hover:scale-103 transition-transform duration-700 ease-out"
                    />

                    {/* Gradient Scrim for readable overlay */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent"></div>

                    {/* Overlay Content */}
                    <div className="absolute bottom-0 inset-x-0 p-6 text-white space-y-3">
                      <div className="flex items-center justify-between text-[10px] font-mono uppercase tracking-widest text-[#E8DFD8]">
                        <span>On-Model Styling Preview</span>
                        <span className="px-2 py-0.5 rounded-full bg-white/20 backdrop-blur-xs">Vogue Edition</span>
                      </div>

                      <p className="font-serif text-lg text-white leading-snug">
                        &ldquo;{activeLook.context}&rdquo;
                      </p>

                      <Link
                        href="/chat"
                        className="tactile-btn group/btn flex items-center justify-between w-full px-5 py-3 rounded-full bg-white/95 text-[#1A1918] hover:bg-white text-xs font-mono uppercase tracking-wider backdrop-blur-md shadow-lg"
                      >
                        <span>Nhờ Stylist Phối Lên Dáng</span>
                        <span className="w-6 h-6 rounded-full bg-black/10 flex items-center justify-center group-hover/btn:translate-x-1 transition-transform">
                          →
                        </span>
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-[#E8E5DE] bg-white py-14 relative z-10">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-6 text-xs font-mono text-[#736E65]">
          <div className="flex items-center gap-3">
            <span className="w-6 h-6 rounded-full bg-[#1A1918] text-[#FBFBF9] flex items-center justify-center text-[10px] font-serif">
              FS
            </span>
            <span>© 2026 Multi-Agent Fashion Stylist. High-Fashion Editorial Experience.</span>
          </div>

          <div className="flex items-center gap-6">
            <Link href="/wardrobe" className="hover:text-[#1A1918] transition-colors">Số Hóa Tủ Đồ</Link>
            <Link href="/chat" className="hover:text-[#1A1918] transition-colors">Tư Vấn Stylist</Link>
            <Link href="/saved" className="hover:text-[#1A1918] transition-colors">Bộ Đồ Đã Lưu</Link>
            <Link href="/profile" className="hover:text-[#1A1918] transition-colors">Sở Thích</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
