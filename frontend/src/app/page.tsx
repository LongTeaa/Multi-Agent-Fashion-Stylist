'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { AppShell } from '@/components/layout/AppShell';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';
import { ArrowRightIcon, CameraIcon, LooksIcon, PlusIcon } from '@/components/ui/icons';
import { getSavedOutfits, getUserProfile, listWardrobeItems } from '@/lib/api';
import { OCCASION_SHORTCUTS, STYLIST_QUERY_PARAM } from '@/lib/occasions';
import { preferenceLabel } from '@/lib/preferenceLabels';
import type { WardrobeItem } from '@/types/wardrobe';

interface HomeSummary {
  /** False until every summary request has settled; avoids swapping the hero mid-typing. */
  loaded: boolean;
  wardrobeTotal: number | null;
  recentItems: WardrobeItem[];
  savedTotal: number | null;
  styleSummary: string[] | null;
}

const EMPTY_SUMMARY: HomeSummary = {
  loaded: false,
  wardrobeTotal: null,
  recentItems: [],
  savedTotal: null,
  styleSummary: null,
};

function stylistHref(prompt: string): string {
  return `/chat?${STYLIST_QUERY_PARAM}=${encodeURIComponent(prompt)}`;
}

export default function Home() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [summary, setSummary] = useState<HomeSummary>(EMPTY_SUMMARY);

  useEffect(() => {
    let ignore = false;
    // Each request is independent; a failing one simply leaves its tile without numbers.
    Promise.allSettled([
      listWardrobeItems({ page: 1, page_size: 6 }),
      getSavedOutfits({ page: 1, page_size: 1 }),
      getUserProfile(),
    ]).then(([wardrobe, saved, profile]) => {
      if (ignore) return;
      setSummary({
        loaded: true,
        wardrobeTotal: wardrobe.status === 'fulfilled' ? wardrobe.value.total : null,
        recentItems: wardrobe.status === 'fulfilled' ? wardrobe.value.items : [],
        savedTotal: saved.status === 'fulfilled' ? saved.value.total : null,
        styleSummary:
          profile.status === 'fulfilled'
            ? [...profile.value.preferences.styles, ...profile.value.preferences.color_palettes]
            : null,
      });
    });
    return () => {
      ignore = true;
    };
  }, []);

  const isWardrobeEmpty = summary.loaded && summary.wardrobeTotal === 0;
  const wardrobeUnavailable = summary.loaded && summary.wardrobeTotal === null;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    router.push(stylistHref(trimmed.slice(0, 1000)));
  };

  return (
    <AppShell width="wide">
      {/* Hero: the one thing to do today */}
      <section className="grid items-center gap-10 pt-2 sm:pt-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <div className="animate-rise">
          <p className="eyebrow mb-4">Trợ lý phối đồ cá nhân</p>
          <h1 className="display text-[2.75rem] sm:text-[4rem]">
            {isWardrobeEmpty ? (
              <>
                Bắt đầu từ
                <br />
                tủ đồ của bạn
              </>
            ) : (
              <>
                Hôm nay
                <br />
                <em className="text-accent">mặc gì?</em>
              </>
            )}
          </h1>

          {!summary.loaded ? (
            <div role="status" aria-live="polite" className="mt-5 max-w-xl space-y-3">
              <span className="sr-only">Đang mở tủ đồ…</span>
              <div className="h-5 w-4/5 animate-pulse rounded bg-sunken" />
              <div className="mt-7 h-14 animate-pulse rounded-full bg-sunken" />
            </div>
          ) : isWardrobeEmpty ? (
            <>
              <p className="mt-5 max-w-lg text-[1.0625rem] leading-relaxed text-ink-2">
                Chụp vài món bạn hay mặc. Mỗi gợi ý sau này đều được chọn từ chính những món đồ đó.
              </p>
              <ol className="mt-7 grid max-w-lg gap-3 text-[0.9375rem] text-ink-2">
                {[
                  'Chụp ảnh một món, nhiều món hoặc cả bộ đang mặc',
                  'Kiểm tra lại loại đồ và màu sắc',
                  'Mô tả dịp đi chơi, đi làm, đi tiệc để nhận bộ phối',
                ].map((step, index) => (
                  <li key={step} className="flex items-start gap-3">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line-strong text-xs font-semibold text-ink">
                      {index + 1}
                    </span>
                    <span className="pt-0.5">{step}</span>
                  </li>
                ))}
              </ol>
              <Link href="/wardrobe?add=1" className="btn btn-primary btn-lg mt-8">
                <CameraIcon size={18} />
                Thêm món đồ đầu tiên
              </Link>
            </>
          ) : (
            <>
              <p className="mt-5 max-w-lg text-[1.0625rem] leading-relaxed text-ink-2">
                Kể cho mình biết bạn sẽ đi đâu và thời tiết thế nào. Bộ phối được chọn từ chính những
                món đồ bạn đang có.
              </p>

              <form onSubmit={handleSubmit} className="mt-7 max-w-xl">
                <label htmlFor="home-stylist-query" className="sr-only">
                  Bạn sẽ đi đâu hôm nay?
                </label>
                <div className="flex items-center gap-2 rounded-full border border-line-strong bg-surface p-1.5 pl-5 shadow-[0_8px_30px_-12px_rgb(28_25_22/0.18)] focus-within:border-ink">
                  <input
                    id="home-stylist-query"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    maxLength={1000}
                    placeholder="Ví dụ: tối nay đi ăn với bạn, trời hơi lạnh"
                    className="min-w-0 flex-1 bg-transparent py-2 text-[0.9375rem] outline-none placeholder:text-muted"
                  />
                  <button type="submit" className="btn btn-primary" disabled={!query.trim()}>
                    Phối đồ
                    <ArrowRightIcon size={16} />
                  </button>
                </div>
              </form>

              <div className="mt-4 flex flex-wrap gap-2" aria-label="Dịp thường gặp">
                {OCCASION_SHORTCUTS.map((occasion) => (
                  <Link key={occasion.label} href={stylistHref(occasion.prompt)} className="chip">
                    {occasion.label}
                  </Link>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="relative hidden lg:block" aria-hidden="true">
          <div className="relative aspect-[4/5] overflow-hidden rounded-[1.75rem] bg-sunken">
            <Image
              src="/images/model-lookbook.jpg"
              alt=""
              fill
              sizes="(max-width: 1200px) 45vw, 520px"
              className="object-cover"
            />
          </div>
          <span className="hang-tag absolute -left-4 top-10 rotate-[-4deg] shadow-sm">Look 01</span>
        </div>
      </section>

      {/* Wardrobe at a glance */}
      <section aria-labelledby="home-overview" className="mt-16 sm:mt-24">
        <h2 id="home-overview" className="display mb-5 text-2xl">
          Tủ đồ của bạn
        </h2>

        <div className="grid gap-4 md:grid-cols-3">
          <Link
            href="/wardrobe"
            className="card group flex flex-col justify-between p-5 transition-colors hover:border-line-strong md:col-span-2"
          >
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-sm font-semibold text-ink-2">Món đồ</p>
              <span className="text-sm font-semibold text-accent group-hover:underline">Mở tủ đồ</span>
            </div>
            <p className="display mt-2 text-4xl tabular-nums">{summary.wardrobeTotal ?? '—'}</p>
            {summary.recentItems.length > 0 ? (
              <ul className="mt-5 grid grid-cols-3 gap-2 sm:grid-cols-6">
                {summary.recentItems.map((item) => (
                  <li
                    key={item.id}
                    className="flex aspect-square items-center justify-center overflow-hidden rounded-xl bg-sunken"
                  >
                    {item.thumbnail_url || item.media_url ? (
                      <PrivateMediaImage
                        source={item.thumbnail_url || item.media_url || ''}
                        alt={item.display_name_vi || item.sub_category}
                        className="h-full w-full object-contain p-1.5"
                        fallbackText="Lỗi ảnh"
                        showRetryButton={false}
                      />
                    ) : (
                      <span className="px-1 text-center text-[0.6875rem] text-muted">
                        {item.display_name_vi || item.sub_category}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            ) : !summary.loaded ? (
              <div className="mt-5 grid grid-cols-3 gap-2 sm:grid-cols-6" aria-hidden="true">
                {Array.from({ length: 6 }).map((_, idx) => (
                  <div key={idx} className="aspect-square animate-pulse rounded-xl bg-sunken" />
                ))}
              </div>
            ) : wardrobeUnavailable ? (
              <p className="mt-4 text-sm text-muted">Chưa tải được tủ đồ. Mở tủ đồ để thử lại.</p>
            ) : (
              <p className="mt-4 text-sm text-muted">Chưa có món nào. Thêm vài món để bắt đầu phối.</p>
            )}
          </Link>

          <div className="grid gap-4">
            <Link
              href="/saved"
              className="card group flex items-center justify-between gap-4 p-5 transition-colors hover:border-line-strong"
            >
              <div>
                <p className="text-sm font-semibold text-ink-2">Bộ đã lưu</p>
                <p className="display mt-1 text-3xl tabular-nums">{summary.savedTotal ?? '—'}</p>
              </div>
              <LooksIcon size={28} className="text-line-strong transition-colors group-hover:text-accent" />
            </Link>

            <Link
              href="/profile"
              className="card group flex flex-col gap-2 p-5 transition-colors hover:border-line-strong"
            >
              <p className="text-sm font-semibold text-ink-2">Gu của tôi</p>
              {summary.styleSummary && summary.styleSummary.length > 0 ? (
                <p className="text-[0.9375rem] text-ink">
                  {summary.styleSummary.slice(0, 4).map(preferenceLabel).join(' · ')}
                </p>
              ) : (
                <p className="text-[0.9375rem] text-muted">
                  Chưa thiết lập.{' '}
                  <span className="font-semibold text-accent group-hover:underline">Chọn phong cách</span>
                </p>
              )}
            </Link>
          </div>
        </div>

        {summary.loaded && !isWardrobeEmpty && (
          <Link href="/wardrobe?add=1" className="btn btn-ghost mt-4 -ml-2">
            <PlusIcon size={16} />
            Thêm món đồ
          </Link>
        )}
      </section>
    </AppShell>
  );
}
