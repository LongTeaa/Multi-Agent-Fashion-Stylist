'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export interface NavItem {
  href: string;
  label: string;
  mobileLabel: string;
}

export const NAV_ITEMS: NavItem[] = [
  { href: '/wardrobe', label: 'Tủ Đồ', mobileLabel: 'Tủ đồ' },
  { href: '/chat', label: 'Tư Vấn Phối Đồ', mobileLabel: 'Tư vấn' },
  { href: '/saved', label: 'Bộ Đồ Đã Lưu', mobileLabel: 'Đã lưu' },
  { href: '/profile', label: 'Gu Thời Trang', mobileLabel: 'Gu đồ' },
];

export function AppHeader() {
  const pathname = usePathname();
  const currentPath = pathname || '';

  const activeItem = NAV_ITEMS.find(
    (item) => currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href))
  );

  return (
    <header className="sticky top-0 z-40 w-full bg-[#FBFBF9]/90 backdrop-blur-md border-b border-[#E8E5DE]">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 h-18 flex items-center justify-between gap-2">
        {/* Brand / Logo */}
        <div className="flex min-w-0 items-center gap-2 sm:gap-3">
          <Link
            href="/"
            className="group flex items-center gap-2 font-serif text-lg tracking-tight font-medium text-[#1A1918] hover:text-[#9C5234] transition-colors"
          >
            <span className="w-8 h-8 rounded-full bg-[#1A1918] text-[#FBFBF9] flex items-center justify-center text-xs font-serif shadow-xs group-hover:bg-[#9C5234] transition-colors">
              FS
            </span>
            <span className="hidden sm:inline">Fashion Stylist</span>
          </Link>
          {activeItem && (
            <>
              <span className="hidden text-[#D5D1C7] sm:inline" aria-hidden="true">
                /
              </span>
              <span className="hidden text-xs font-mono tracking-wider uppercase text-[#736E65] md:inline">
                {activeItem.label}
              </span>
            </>
          )}
        </div>

        {/* Unified Primary Navigation */}
        <nav aria-label="Điều hướng chính" className="flex min-w-0 items-center gap-1 sm:gap-2 md:gap-3">
          {NAV_ITEMS.map((item) => {
            const isActive =
              currentPath === item.href || (item.href !== '/' && currentPath.startsWith(item.href));

            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? 'page' : undefined}
                className={`inline-flex items-center gap-1.5 px-2.5 sm:px-3.5 py-1.5 rounded-full text-[11px] sm:text-xs font-mono uppercase tracking-wider transition-all whitespace-nowrap ${
                  isActive
                    ? 'bg-[#9C5234]/10 text-[#9C5234] font-semibold border border-[#9C5234]/25 shadow-2xs'
                    : 'text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] border border-transparent'
                }`}
              >
                {isActive && (
                  <>
                    <span className="w-1.5 h-1.5 rounded-full bg-[#9C5234]" aria-hidden="true" />
                    <span className="sr-only">(đang xem)</span>
                  </>
                )}
                <span className="sm:hidden">{item.mobileLabel}</span>
                <span className="hidden sm:inline">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
