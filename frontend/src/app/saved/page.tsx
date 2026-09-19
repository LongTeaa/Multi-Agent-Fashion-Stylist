'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { getSavedOutfits, ApiError } from '@/lib/api';
import type { SavedOutfitsResponseData } from '@/types/outfits';
import { OutfitCard, normalizeDetailItems } from '@/components/outfits/OutfitCard';

export default function SavedOutfitsPage() {
  const [page, setPage] = useState<number>(1);
  const pageSize = 10;
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [data, setData] = useState<SavedOutfitsResponseData | null>(null);
  const [refreshKey, setRefreshKey] = useState<number>(0);

  useEffect(() => {
    let ignore = false;
    getSavedOutfits({ page, page_size: pageSize })
      .then((res) => {
        if (!ignore) {
          if (res.total > 0 && res.items.length === 0 && page > 1) {
            // Page drift detected: auto-request valid page
            const validPage = Math.max(1, Math.ceil(res.total / pageSize));
            setPage(validPage);
          } else {
            setData(res);
            setError(null);
            setLoading(false);
          }
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          const apiErr =
            err instanceof ApiError
              ? err
              : new ApiError(
                  (err as Error)?.message || 'Không thể tải danh sách bộ đồ đã lưu.',
                  'UNKNOWN_ERROR',
                  500,
                  err
                );
          setError(apiErr);
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [page, pageSize, refreshKey]);

  const totalItems = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));

  const handleNextPage = () => {
    if (page < totalPages) {
      setLoading(true);
      setPage((prev) => prev + 1);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handlePrevPage = () => {
    if (page > 1) {
      setLoading(true);
      setPage((prev) => prev - 1);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handleRetry = () => {
    setLoading(true);
    setError(null);
    setRefreshKey((prev) => prev + 1);
  };

  const handleBookmarkChange = (outfitId: string, isBookmarked: boolean) => {
    // When an item is unbookmarked in the Saved Outfits page, remove it from the list and decrement total
    setData((prev) => {
      if (!prev) return prev;
      if (!isBookmarked) {
        const remainingItems = prev.items.filter((item) => item.id !== outfitId);
        const newTotal = Math.max(0, prev.total - 1);
        if (remainingItems.length === 0 && prev.page > 1) {
          setPage((p) => Math.max(1, p - 1));
        }
        return {
          ...prev,
          items: remainingItems,
          total: newTotal,
        };
      }
      return {
        ...prev,
        items: prev.items.map((item) =>
          item.id === outfitId ? { ...item, is_bookmarked: isBookmarked } : item
        ),
      };
    });
  };

  const handleWearSuccess = (outfitId: string, timesWorn: number) => {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((item) =>
          item.id === outfitId ? { ...item, times_worn: timesWorn } : item
        ),
      };
    });
  };

  const handleRatingChange = (outfitId: string, rating: number) => {
    setData((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        items: prev.items.map((item) =>
          item.id === outfitId ? { ...item, user_rating: rating } : item
        ),
      };
    });
  };

  return (
    <div className="min-h-screen bg-[#FBFBF9] text-[#1A1918]">
      {/* Header */}
      <header className="sticky top-0 z-40 w-full bg-[#FBFBF9]/90 backdrop-blur-md border-b border-[#E8E5DE]">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-18 flex items-center justify-between">
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
            <span className="text-xs font-mono tracking-wider uppercase text-[#736E65]">
              Bộ Đồ Đã Lưu
            </span>
          </div>

          <nav className="flex items-center gap-2 sm:gap-3">
            <Link
              href="/chat"
              className="px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition-colors"
            >
              Tư Vấn Stylist
            </Link>
            <Link
              href="/wardrobe"
              className="px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition-colors"
            >
              Tủ Đồ
            </Link>
            <Link
              href="/profile"
              className="px-3.5 py-1.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#5C564E] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition-colors"
            >
              Gu Thời Trang
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-4 py-8 sm:py-10 space-y-8">
        {/* Page Title & Count */}
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="space-y-1">
            <span className="text-xs font-mono uppercase tracking-widest text-[#9C5234] block">
              Curated Wardrobe
            </span>
            <h1 className="font-serif text-3xl sm:text-4xl font-normal tracking-tight text-[#1A1918]">
              Bộ Trang Phục Đã Lưu
            </h1>
            <p className="text-sm text-[#5C564E] mt-1 leading-relaxed">
              Danh sách các set đồ bạn đã đánh dấu lưu lại từ các phiên tư vấn phối đồ của AI Stylist.
            </p>
          </div>

          {totalItems > 0 && (
            <span className="px-3.5 py-1.5 rounded-full text-xs font-mono tracking-wider uppercase bg-[#F5F4F0] text-[#736E65] border border-[#E8E5DE]">
              Tổng cộng {totalItems} bộ đồ
            </span>
          )}
        </div>

        {/* Loading State */}
        {loading && (
          <div
            role="status"
            aria-live="polite"
            className="space-y-6 animate-pulse"
          >
            {[1, 2].map((idx) => (
              <div
                key={idx}
                className="w-full bg-white rounded-3xl border border-[#E8E5DE] p-6 sm:p-8 space-y-5 shadow-xs"
              >
                <div className="h-6 bg-[#EAE8E1] rounded w-1/3"></div>
                <div className="h-14 bg-[#F5F4F0] rounded-2xl"></div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="h-32 bg-[#F5F4F0] rounded-2xl"></div>
                  <div className="h-32 bg-[#F5F4F0] rounded-2xl"></div>
                  <div className="h-32 bg-[#F5F4F0] rounded-2xl"></div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div
            role="alert"
            className="w-full bg-rose-50 border border-rose-200 rounded-3xl p-8 text-center space-y-4"
          >
            <p className="text-sm font-medium text-rose-800">
              {error.message || 'Đã xảy ra lỗi khi tải danh sách bộ đồ đã lưu.'}
            </p>
            <button
              type="button"
              onClick={handleRetry}
              className="tactile-btn inline-flex items-center gap-2 px-5 py-2.5 rounded-full text-xs font-mono uppercase tracking-wider text-white bg-rose-700 hover:bg-rose-800 shadow-xs"
            >
              <span>Thử lại</span>
            </button>
          </div>
        )}

        {/* True Empty State (Total = 0) */}
        {!loading && !error && data && data.total === 0 && (
          <div
            data-testid="saved-outfits-empty"
            className="w-full bg-white rounded-3xl border border-[#E8E5DE] p-8 sm:p-14 text-center space-y-5 shadow-xs"
          >
            <div className="w-14 h-14 rounded-2xl bg-[#F5F4F0] text-[#9C5234] flex items-center justify-center mx-auto shadow-2xs">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
              </svg>
            </div>

            <div className="space-y-2 max-w-md mx-auto">
              <h2 className="font-serif text-2xl font-normal text-[#1A1918]">
                Bạn Chưa Lưu Bộ Trang Phục Nào
              </h2>
              <p className="text-sm text-[#5C564E] leading-relaxed">
                Khi trò chuyện với AI Stylist, bạn có thể nhấn biểu tượng lưu để gom các set đồ ưng ý vào tủ đồ phối sẵn này.
              </p>
            </div>

            <div className="pt-3">
              <Link
                href="/chat"
                className="tactile-btn inline-flex items-center gap-2 px-6 py-3.5 rounded-full text-xs font-mono uppercase tracking-wider text-[#FBFBF9] bg-[#1A1918] hover:bg-[#2D2420] shadow-sm"
              >
                <span>Nhờ Stylist Gợi Ý Ngay</span>
                <span>→</span>
              </Link>
            </div>
          </div>
        )}

        {/* Page Drift Recovery (Total > 0 but this page has 0 items) */}
        {!loading && !error && data && data.total > 0 && data.items.length === 0 && (
          <div className="w-full bg-white dark:bg-slate-800/60 rounded-2xl border border-slate-200 dark:border-slate-700/80 p-8 text-center space-y-3 shadow-sm">
            <p className="text-sm text-slate-600 dark:text-slate-300">
              Trang hiện tại không còn bộ đồ nào. Đang quay lại trang hợp lệ...
            </p>
            <button
              type="button"
              onClick={() => setPage(Math.max(1, Math.ceil(data.total / pageSize)))}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition shadow-xs"
            >
              ← Quay lại trang trước
            </button>
          </div>
        )}

        {/* Saved List */}
        {!loading && !error && data && data.items.length > 0 && (
          <div className="space-y-5">
            {data.items.map((outfit) => (
              <OutfitCard
                key={outfit.id}
                outfitId={outfit.id}
                rank={outfit.rank}
                compositeScore={outfit.composite_score}
                explanationVi={outfit.explanation_vi}
                items={normalizeDetailItems(outfit.items)}
                initialIsBookmarked={outfit.is_bookmarked}
                initialTimesWorn={outfit.times_worn}
                initialRating={outfit.user_rating}
                lastWornAt={outfit.last_worn_at}
                onBookmarkChange={handleBookmarkChange}
                onWearSuccess={handleWearSuccess}
                onRatingChange={handleRatingChange}
              />
            ))}

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <nav
                role="navigation"
                aria-label="Phân trang danh sách bộ đồ đã lưu"
                className="pt-6 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between"
              >
                <button
                  type="button"
                  onClick={handlePrevPage}
                  disabled={page <= 1}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/60 disabled:opacity-40 disabled:cursor-not-allowed shadow-2xs transition"
                >
                  <span>← Trang trước</span>
                </button>

                <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                  Trang {page} / {totalPages}
                </span>

                <button
                  type="button"
                  onClick={handleNextPage}
                  disabled={page >= totalPages}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/60 disabled:opacity-40 disabled:cursor-not-allowed shadow-2xs transition"
                >
                  <span>Trang sau →</span>
                </button>
              </nav>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
