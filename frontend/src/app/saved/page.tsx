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
    // Update local list state so unbookmark is immediately reflected
    setData((prev) => {
      if (!prev) return prev;
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/20 to-slate-100 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950/40 text-slate-800 dark:text-slate-100 transition-colors">
      {/* Header */}
      <header className="sticky top-0 z-40 w-full bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200/80 dark:border-slate-800 shadow-xs">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-2 font-black text-lg tracking-tight text-indigo-600 dark:text-indigo-400 hover:opacity-90 transition"
            >
              <span className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm font-bold shadow-md shadow-indigo-200 dark:shadow-none">
                FS
              </span>
              <span>Fashion Stylist</span>
            </Link>
            <span className="text-slate-300 dark:text-slate-700">/</span>
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              Bộ Đồ Đã Lưu
            </span>
          </div>

          <nav className="flex items-center gap-2 sm:gap-4">
            <Link
              href="/chat"
              className="px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              Tư Vấn Stylist
            </Link>
            <Link
              href="/wardrobe"
              className="px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              Tủ Đồ
            </Link>
            <Link
              href="/profile"
              className="px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              Gu Thời Trang
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-4 py-8 sm:py-10 space-y-6">
        {/* Page Title & Count */}
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
              Bộ Trang Phục Đã Lưu
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              Danh sách các set đồ bạn đã đánh dấu bookmark từ các lần tư vấn của AI Stylist.
            </p>
          </div>

          {totalItems > 0 && (
            <span className="px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/60">
              Tổng cộng {totalItems} bộ đồ
            </span>
          )}
        </div>

        {/* Loading State */}
        {loading && (
          <div
            role="status"
            aria-live="polite"
            className="space-y-4 animate-pulse"
          >
            {[1, 2].map((idx) => (
              <div
                key={idx}
                className="w-full bg-white dark:bg-slate-800/80 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-4 shadow-sm"
              >
                <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-1/3"></div>
                <div className="h-12 bg-slate-100 dark:bg-slate-700/40 rounded-xl"></div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="h-28 bg-slate-100 dark:bg-slate-700/40 rounded-xl"></div>
                  <div className="h-28 bg-slate-100 dark:bg-slate-700/40 rounded-xl"></div>
                  <div className="h-28 bg-slate-100 dark:bg-slate-700/40 rounded-xl"></div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Error State */}
        {!loading && error && (
          <div
            role="alert"
            className="w-full bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800/60 rounded-2xl p-6 text-center space-y-3"
          >
            <p className="text-sm font-semibold text-rose-800 dark:text-rose-200">
              {error.message || 'Đã xảy ra lỗi khi tải danh sách bộ đồ đã lưu.'}
            </p>
            <button
              type="button"
              onClick={handleRetry}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold text-white bg-rose-600 hover:bg-rose-500 shadow-xs transition"
            >
              <span>Thử lại</span>
            </button>
          </div>
        )}

        {/* True Empty State (Total = 0) */}
        {!loading && !error && data && data.total === 0 && (
          <div
            data-testid="saved-outfits-empty"
            className="w-full bg-white dark:bg-slate-800/60 rounded-2xl border border-slate-200 dark:border-slate-700/80 p-8 sm:p-12 text-center space-y-4 shadow-sm"
          >
            <div className="w-14 h-14 rounded-2xl bg-indigo-50 dark:bg-indigo-950/50 text-indigo-500 dark:text-indigo-400 flex items-center justify-center mx-auto text-2xl shadow-xs">
              🔖
            </div>

            <div className="space-y-1.5 max-w-md mx-auto">
              <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">
                Bạn Chưa Lưu Bộ Trang Phục Nào
              </h2>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
                Khi trò chuyện với AI Stylist, bạn có thể nhấn biểu tượng lưu để gom các set đồ ưng ý vào tủ đồ phối sẵn này.
              </p>
            </div>

            <div className="pt-2">
              <Link
                href="/chat"
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs sm:text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-md shadow-indigo-600/20 transition active:scale-95"
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
                lastWornAt={outfit.last_worn_at}
                onBookmarkChange={handleBookmarkChange}
                onWearSuccess={handleWearSuccess}
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
