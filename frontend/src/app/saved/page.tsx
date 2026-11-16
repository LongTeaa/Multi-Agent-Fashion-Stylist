'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { AppShell, PageHeader } from '@/components/layout/AppShell';
import { ArrowLeftIcon, ArrowRightIcon, BookmarkIcon, RefreshIcon } from '@/components/ui/icons';
import { formatLookNumber } from '@/lib/looks';
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
    <AppShell width="narrow">
      <PageHeader
        title="Bộ đã lưu"
        description="Những bộ phối bạn muốn mặc lại. Ghi nhận mỗi lần mặc để các gợi ý sau đa dạng hơn."
        actions={
          totalItems > 0 ? (
            <span className="text-sm font-semibold tabular-nums text-muted">{totalItems} bộ đồ</span>
          ) : undefined
        }
      />

      {loading && (
        <div role="status" aria-live="polite" className="space-y-5">
          <span className="sr-only">Đang tải bộ đã lưu…</span>
          {[1, 2].map((idx) => (
            <div key={idx} className="card space-y-4 p-6">
              <div className="h-6 w-1/4 animate-pulse rounded bg-sunken" />
              <div className="grid grid-cols-3 gap-3">
                {[0, 1, 2].map((key) => (
                  <div key={key} className="aspect-square animate-pulse rounded-xl bg-sunken" />
                ))}
              </div>
              <div className="h-12 animate-pulse rounded-xl bg-sunken" />
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div role="alert" className="card p-8 text-center">
          <p className="text-[0.9375rem] text-ink-2">
            {error.message || 'Đã xảy ra lỗi khi tải danh sách bộ đồ đã lưu.'}
          </p>
          <button type="button" onClick={handleRetry} className="btn btn-secondary mt-4">
            <RefreshIcon size={16} />
            Thử lại
          </button>
        </div>
      )}

      {!loading && !error && data && data.total === 0 && (
        <div data-testid="saved-outfits-empty" className="card px-6 py-14 text-center">
          <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-sunken text-accent">
            <BookmarkIcon size={22} />
          </span>
          <h2 className="display mt-5 text-2xl">Chưa có bộ nào được lưu</h2>
          <p className="mx-auto mt-2 max-w-sm text-[0.9375rem] leading-relaxed text-ink-2">
            Khi thấy một bộ phối ưng ý, nhấn Lưu để giữ lại ở đây.
          </p>
          <Link href="/chat" className="btn btn-primary mt-6">
            Bắt đầu phối đồ
            <ArrowRightIcon size={16} />
          </Link>
        </div>
      )}

      {/* Page drift recovery (total > 0 but this page has no items) */}
      {!loading && !error && data && data.total > 0 && data.items.length === 0 && (
        <div className="card p-8 text-center">
          <p className="text-[0.9375rem] text-ink-2">Trang này không còn bộ đồ nào.</p>
          <button
            type="button"
            onClick={() => setPage(Math.max(1, Math.ceil(data.total / pageSize)))}
            className="btn btn-secondary mt-4"
          >
            <ArrowLeftIcon size={16} />
            Quay lại trang trước
          </button>
        </div>
      )}

      {!loading && !error && data && data.items.length > 0 && (
        <div className="space-y-5">
          {data.items.map((outfit, index) => (
            <OutfitCard
              key={outfit.id}
              outfitId={outfit.id}
              title={formatLookNumber((page - 1) * pageSize + index + 1)}
              context={outfit.user_query}
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

          {totalPages > 1 && (
            <nav
              role="navigation"
              aria-label="Phân trang danh sách bộ đồ đã lưu"
              className="flex items-center justify-between border-t border-line pt-6"
            >
              <button type="button" onClick={handlePrevPage} disabled={page <= 1} className="btn btn-secondary btn-sm">
                <ArrowLeftIcon size={15} />
                Trang trước
              </button>
              <span className="text-sm tabular-nums text-muted">
                Trang {page} / {totalPages}
              </span>
              <button
                type="button"
                onClick={handleNextPage}
                disabled={page >= totalPages}
                className="btn btn-secondary btn-sm"
              >
                Trang sau
                <ArrowRightIcon size={15} />
              </button>
            </nav>
          )}
        </div>
      )}
    </AppShell>
  );
}
