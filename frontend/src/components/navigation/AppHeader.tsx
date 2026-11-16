'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BookmarkIcon, HangerIcon, LooksIcon, ProfileIcon } from '@/components/ui/icons';

export interface NavItem {
  href: string;
  label: string;
  icon: (props: { size?: number }) => React.ReactElement;
}

/** Primary destinations, ordered by how often people use them. */
export const NAV_ITEMS: NavItem[] = [
  { href: '/chat', label: 'Phối đồ', icon: LooksIcon },
  { href: '/wardrobe', label: 'Tủ đồ', icon: HangerIcon },
  { href: '/saved', label: 'Đã lưu', icon: (p) => <BookmarkIcon {...p} /> },
  { href: '/profile', label: 'Gu của tôi', icon: ProfileIcon },
];

export function BrandMark({ className = '' }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`group inline-flex items-center gap-2 rounded-md text-ink ${className}`}
      aria-label="Fashion Stylist — Trang chủ"
    >
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-ink text-paper transition-colors group-hover:bg-accent">
        <HangerIcon size={17} />
      </span>
      <span className="display text-[1.2rem] leading-none">
        Fashion <em className="not-italic text-accent">Stylist</em>
      </span>
    </Link>
  );
}

export function AppHeader() {
  const pathname = usePathname() || '';

  return (
    // No backdrop-filter here: it would turn the header into the containing block
    // for the fixed mobile tab bar below and pin it to the top of the page.
    <header className="sticky top-0 z-40 border-b border-line bg-paper">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <BrandMark />

        {/*
          One navigation landmark: inline in the header on desktop,
          docked as a tab bar at the bottom of the screen on mobile.
        */}
        <nav
          aria-label="Điều hướng chính"
          className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-paper/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:static md:border-0 md:bg-transparent md:pb-0 md:backdrop-blur-none"
        >
          <ul className="mx-auto grid max-w-md grid-cols-4 md:flex md:max-w-none md:items-center md:gap-1">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? 'page' : undefined}
                    className={`flex flex-col items-center gap-1 px-2 py-2.5 text-[0.6875rem] font-semibold transition-colors md:flex-row md:gap-2 md:rounded-full md:px-3.5 md:py-2 md:text-sm ${
                      isActive
                        ? 'text-accent md:bg-ink md:text-paper'
                        : 'text-muted hover:text-ink md:hover:bg-sunken'
                    }`}
                  >
                    <span className="md:hidden">
                      <Icon size={22} />
                    </span>
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </header>
  );
}
