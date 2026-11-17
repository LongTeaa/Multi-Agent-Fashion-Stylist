'use client';

import React, { useState, useRef, useEffect } from 'react';
import { setOutfitBookmark, recordOutfitWorn, rateOutfit, ApiError } from '@/lib/api';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';
import type { StylistRecommendationItem } from '@/types/chat';
import type { OutfitItemDetailResponse } from '@/types/outfits';
import { TryOnModal } from '@/components/tryon/TryOnModal';
import { BookmarkIcon, CheckIcon, CloseIcon, Spinner, StarIcon } from '@/components/ui/icons';
import { formatLookNumber } from '@/lib/looks';
import { attributeLabel } from '@/lib/preferenceLabels';

/**
 * Standard RFC 4122 Version 4 UUID generator with fallback
 * Guaranteed to satisfy backend UUID v4 validation in all environments
 */
export function generateUUIDv4(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export interface NormalizedOutfitItem {
  id: string;
  slot: string;
  name: string;
  imageUrl?: string | null;
  category?: string;
  subCategory?: string;
  groupLabel?: string | null;
  primaryColor?: string;
  isActive?: boolean;
}

export function normalizeStylistItems(items: StylistRecommendationItem[]): NormalizedOutfitItem[] {
  return items.map((it) => ({
    id: it.item_id,
    slot: it.slot,
    name: it.name,
    groupLabel: it.group_label_vi,
    imageUrl: it.image_url,
    isActive: true,
  }));
}

export function normalizeDetailItems(items: OutfitItemDetailResponse[]): NormalizedOutfitItem[] {
  return items.map((it) => ({
    id: it.wardrobe_item_id,
    slot: it.slot_role,
    name: it.name,
    groupLabel: it.group_label_vi,
    imageUrl: it.image_url,
    category: it.category,
    subCategory: it.sub_category,
    primaryColor: it.primary_color,
    isActive: it.is_active,
  }));
}

const SLOT_NAMES: Record<string, string> = {
  top: 'Áo',
  bottom: 'Quần / Váy',
  dress: 'Đầm',
  footwear: 'Giày',
  outerwear: 'Áo khoác',
  accessory: 'Phụ kiện',
};

export interface OutfitCardProps {
  outfitId: string;
  rank?: number;
  /** Overrides the default "Look NN" title. */
  title?: string;
  /** The original request this look answered, shown under the title. */
  context?: string | null;
  compositeScore?: number;
  explanationVi: string;
  appliedPreferences?: string[];
  items: NormalizedOutfitItem[];
  initialIsBookmarked?: boolean;
  initialTimesWorn?: number;
  initialRating?: number | null;
  lastWornAt?: string | null;
  onBookmarkChange?: (outfitId: string, isBookmarked: boolean) => void;
  onWearSuccess?: (outfitId: string, timesWorn: number, lastWornAt: string) => void;
  onRatingChange?: (outfitId: string, rating: number) => void;
  className?: string;
  testId?: string;
}

export const OutfitCard: React.FC<OutfitCardProps> = ({
  outfitId,
  rank,
  title,
  context,
  compositeScore,
  explanationVi,
  appliedPreferences = [],
  items = [],
  initialIsBookmarked = false,
  initialTimesWorn = 0,
  initialRating = null,
  lastWornAt,
  onBookmarkChange,
  onWearSuccess,
  onRatingChange,
  className = '',
  testId = 'outfit-card',
}) => {
  // Bookmark state (Optimistic UI with prop sync during render)
  const [prevInitialBookmarked, setPrevInitialBookmarked] = useState<boolean>(initialIsBookmarked);
  const [isBookmarked, setIsBookmarked] = useState<boolean>(initialIsBookmarked);
  if (initialIsBookmarked !== prevInitialBookmarked) {
    setPrevInitialBookmarked(initialIsBookmarked);
    setIsBookmarked(initialIsBookmarked);
  }
  const [isBookmarkPending, setIsBookmarkPending] = useState<boolean>(false);
  const [bookmarkError, setBookmarkError] = useState<string | null>(null);

  // Wear log state (Idempotent UI with prop sync during render)
  const [prevInitialTimesWorn, setPrevInitialTimesWorn] = useState<number>(initialTimesWorn);
  const [timesWorn, setTimesWorn] = useState<number>(initialTimesWorn);
  if (initialTimesWorn !== prevInitialTimesWorn) {
    setPrevInitialTimesWorn(initialTimesWorn);
    setTimesWorn(initialTimesWorn);
  }
  // Last-worn date follows the same prop-sync pattern so a fresh wear updates it immediately.
  const [prevLastWornAt, setPrevLastWornAt] = useState<string | null | undefined>(lastWornAt);
  const [lastWorn, setLastWorn] = useState<string | null | undefined>(lastWornAt);
  if (lastWornAt !== prevLastWornAt) {
    setPrevLastWornAt(lastWornAt);
    setLastWorn(lastWornAt);
  }
  const [isWearPending, setIsWearPending] = useState<boolean>(false);
  const [wearSuccessMsg, setWearSuccessMsg] = useState<string | null>(null);
  const [wearError, setWearError] = useState<string | null>(null);

  // Manual rating state (1-5 stars with prop sync during render)
  const [prevInitialRating, setPrevInitialRating] = useState<number | null>(initialRating ?? null);
  const [userRating, setUserRating] = useState<number | null>(initialRating ?? null);
  if (initialRating !== undefined && initialRating !== prevInitialRating) {
    setPrevInitialRating(initialRating);
    setUserRating(initialRating);
  }
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [isRatingPending, setIsRatingPending] = useState<boolean>(false);
  const [ratingError, setRatingError] = useState<string | null>(null);
  const [ratingSuccessMsg, setRatingSuccessMsg] = useState<string | null>(null);
  const [isTryOnOpen, setIsTryOnOpen] = useState(false);

  // Idempotency key generated once per user intent session, preserved on retry
  const idempotencyKeyRef = useRef<string>('');
  const wearTimerRef = useRef<NodeJS.Timeout | null>(null);
  const ratingTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (wearTimerRef.current) {
        clearTimeout(wearTimerRef.current);
      }
      if (ratingTimerRef.current) {
        clearTimeout(ratingTimerRef.current);
      }
    };
  }, []);

  const matchPercentage =
    compositeScore !== undefined ? Math.round(compositeScore * 100) : null;

  const handleToggleBookmark = async () => {
    if (isBookmarkPending) return;

    const nextBookmarked = !isBookmarked;
    const prevBookmarked = isBookmarked;

    // 1. Optimistic update
    setIsBookmarked(nextBookmarked);
    setBookmarkError(null);
    setIsBookmarkPending(true);
    onBookmarkChange?.(outfitId, nextBookmarked);

    // 2. Network call
    try {
      await setOutfitBookmark(outfitId, nextBookmarked);
    } catch (err) {
      // 3. Rollback on failure
      setIsBookmarked(prevBookmarked);
      onBookmarkChange?.(outfitId, prevBookmarked);
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Không thể cập nhật trạng thái lưu. Vui lòng thử lại.';
      setBookmarkError(msg);
    } finally {
      setIsBookmarkPending(false);
    }
  };

  const handleRecordWorn = async () => {
    if (isWearPending) return;

    if (!idempotencyKeyRef.current) {
      idempotencyKeyRef.current = generateUUIDv4();
    }

    setIsWearPending(true);
    setWearError(null);
    setWearSuccessMsg(null);

    try {
      const res = await recordOutfitWorn(outfitId, {
        idempotency_key: idempotencyKeyRef.current,
      });

      setTimesWorn(res.times_worn);
      setLastWorn(res.worn_at);
      setWearSuccessMsg(
        res.already_processed
          ? 'Đã ghi nhận mặc trước đó!'
          : 'Đã ghi nhận bạn mặc bộ này!'
      );

      // Successfully processed: cycle idempotency key for future wears
      idempotencyKeyRef.current = generateUUIDv4();

      onWearSuccess?.(outfitId, res.times_worn, res.worn_at);

      // Auto-clear success badge after 4 seconds (with timer cleanup)
      if (wearTimerRef.current) {
        clearTimeout(wearTimerRef.current);
      }
      wearTimerRef.current = setTimeout(() => {
        setWearSuccessMsg(null);
      }, 4000);
    } catch (err) {
      // On network failure, KEEP the same idempotency key so retry uses it
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Không thể ghi nhận lượt mặc. Vui lòng thử lại.';
      setWearError(msg);
    } finally {
      setIsWearPending(false);
    }
  };

  const handleRateOutfit = async (stars: number) => {
    if (!Number.isInteger(stars) || stars < 1 || stars > 5 || isRatingPending) return;

    setIsRatingPending(true);
    setRatingError(null);
    setRatingSuccessMsg(null);

    try {
      const res = await rateOutfit(outfitId, { stars, source: 'manual' });
      setUserRating(res.stars);
      setRatingSuccessMsg(`Đã đánh giá ${res.stars}★`);
      onRatingChange?.(outfitId, res.stars);

      if (ratingTimerRef.current) {
        clearTimeout(ratingTimerRef.current);
      }
      ratingTimerRef.current = setTimeout(() => {
        setRatingSuccessMsg(null);
      }, 3500);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Không thể lưu đánh giá. Vui lòng thử lại.';
      setRatingError(msg);
    } finally {
      setIsRatingPending(false);
    }
  };

  const displayTitle = title ?? (rank !== undefined ? formatLookNumber(rank) : 'Bộ phối');
  const worn = timesWorn > 0;

  return (
    <>
      <article
        data-testid={testId}
        data-outfit-id={outfitId}
        className={`card overflow-hidden animate-rise ${className}`}
      >
        {/* Header: look number, match, save */}
        <header className="flex items-start justify-between gap-3 px-5 pb-3 pt-4 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <h3 className="display text-[1.375rem] italic">{displayTitle}</h3>
              {matchPercentage !== null && (
                <span className="text-sm text-accent">
                  <span className="font-semibold tabular-nums">{matchPercentage}%</span>{' '}
                  <span>phù hợp</span>
                </span>
              )}
            </div>
            {context && <p className="mt-1 line-clamp-1 text-sm text-muted">Cho: “{context}”</p>}
            {worn && (
              <p className="mt-1 text-xs text-muted" suppressHydrationWarning>
                Đã mặc {timesWorn} lần
                {lastWorn ? ` · gần nhất ${new Date(lastWorn).toLocaleDateString('vi-VN')}` : ''}
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={handleToggleBookmark}
            disabled={isBookmarkPending}
            aria-label={isBookmarked ? 'Bỏ lưu bộ đồ này' : 'Lưu bộ đồ này'}
            aria-pressed={isBookmarked}
            className={`btn btn-sm shrink-0 ${isBookmarked ? 'bg-accent-soft text-accent' : 'btn-secondary'}`}
          >
            <BookmarkIcon size={15} filled={isBookmarked} />
            <span>{isBookmarked ? 'Đã lưu' : 'Lưu'}</span>
          </button>
        </header>

        {bookmarkError && (
          <div role="alert" className="notice notice-danger mx-5 mb-3 sm:mx-6">
            <span className="flex-1">{bookmarkError}</span>
            <button
              type="button"
              onClick={() => setBookmarkError(null)}
              aria-label="Đóng thông báo lỗi"
              className="shrink-0 opacity-70 hover:opacity-100"
            >
              <CloseIcon size={14} />
            </button>
          </div>
        )}

        {/* The look: garments laid out like a flat-lay */}
        <ul className="grid grid-cols-3 gap-2.5 px-5 sm:grid-cols-[repeat(auto-fill,minmax(8.5rem,1fr))] sm:gap-3 sm:px-6">
          {items.map((item) => {
            const slotName = item.groupLabel || SLOT_NAMES[item.slot] || item.slot;
            const removed = item.isActive === false;
            return (
              <li key={item.id} className="min-w-0">
                <div
                  className={`relative flex aspect-square items-center justify-center overflow-hidden rounded-xl ${
                    removed ? 'border border-dashed border-danger/50 bg-surface' : 'bg-sunken'
                  }`}
                >
                  {item.imageUrl ? (
                    <PrivateMediaImage
                      source={item.imageUrl}
                      alt={`Ảnh của ${item.name} (${slotName})`}
                      className={`h-full w-full object-contain p-2 ${removed ? 'opacity-50' : ''}`}
                      loading="lazy"
                    />
                  ) : (
                    <span className="px-2 text-center text-xs text-muted">Không có ảnh</span>
                  )}
                  {removed && (
                    <span className="absolute inset-x-1.5 bottom-1.5 rounded-md bg-danger px-1.5 py-0.5 text-center text-[0.625rem] font-semibold text-white">
                      Đã xóa khỏi tủ
                    </span>
                  )}
                </div>
                <span className="hang-tag mt-2 max-w-full overflow-hidden text-ellipsis">{slotName}</span>
                <p className="mt-1 line-clamp-2 text-[0.8125rem] font-medium leading-snug text-ink">{item.name}</p>
                {attributeLabel(item.primaryColor) && (
                  <p className="truncate text-xs text-muted first-letter:uppercase">{attributeLabel(item.primaryColor)}</p>
                )}
              </li>
            );
          })}
        </ul>

        {/* Why it works */}
        <div className="mx-5 mt-5 rounded-xl bg-paper px-4 py-3.5 sm:mx-6">
          <p className="text-xs font-semibold text-accent">Vì sao hợp</p>
          <p className="mt-1 text-[0.9375rem] leading-relaxed text-ink-2">{explanationVi}</p>
          {appliedPreferences.length > 0 && (
            <p className="mt-2 text-xs text-muted">
              Theo gu của bạn: <span className="text-ink-2">{appliedPreferences.join(' · ')}</span>
            </p>
          )}
        </div>

        {/* Actions: one primary, the rest quiet */}
        <footer className="mt-5 flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-t border-line px-5 py-3.5 sm:px-6">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setIsTryOnOpen(true)}
              aria-label="Mặc thử: xem ảnh minh họa bộ trang phục"
              className="btn btn-primary btn-sm"
            >
              Mặc thử
            </button>
            <button
              type="button"
              onClick={handleRecordWorn}
              disabled={isWearPending}
              aria-label="Xác nhận đã mặc bộ trang phục này hôm nay"
              className="btn btn-ghost btn-sm"
            >
              {isWearPending ? <Spinner size={14} /> : <CheckIcon size={15} />}
              <span>{isWearPending ? 'Đang ghi nhận…' : 'Đã mặc hôm nay'}</span>
            </button>
            {wearSuccessMsg && (
              <span className="animate-rise text-xs font-semibold text-success">
                ✓ {wearSuccessMsg}
              </span>
            )}
            {wearError && (
              <span className="animate-rise text-xs font-semibold text-danger">
                ✕ {wearError}
              </span>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            <div className="flex items-center" role="group" aria-label="Đánh giá bộ trang phục từ 1 đến 5 sao">
              {[1, 2, 3, 4, 5].map((star) => {
                const isFilled = (hoverRating ?? userRating ?? 0) >= star;
                return (
                  <button
                    key={star}
                    type="button"
                    onClick={() => handleRateOutfit(star)}
                    onMouseEnter={() => setHoverRating(star)}
                    onMouseLeave={() => setHoverRating(null)}
                    onFocus={() => setHoverRating(star)}
                    onBlur={() => setHoverRating(null)}
                    disabled={isRatingPending}
                    aria-label={`Đánh giá ${star} sao`}
                    className={`rounded p-0.5 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      isFilled ? 'text-accent' : 'text-line-strong hover:text-accent'
                    }`}
                  >
                    <StarIcon size={17} filled={isFilled} />
                  </button>
                );
              })}
            </div>
            {userRating && <span className="text-xs font-semibold tabular-nums text-ink-2">{userRating}/5★</span>}
            {ratingSuccessMsg && (
              <span className="animate-rise text-xs font-semibold text-success">✓ {ratingSuccessMsg}</span>
            )}
            {ratingError && <span className="animate-rise text-xs font-semibold text-danger">✕ {ratingError}</span>}
          </div>
        </footer>
      </article>
      <TryOnModal
        isOpen={isTryOnOpen}
        outfitId={outfitId}
        items={items}
        isBookmarked={isBookmarked}
        isWorn={worn}
        onBookmarkChange={(changedOutfitId, nextBookmarked) => {
          setIsBookmarked(nextBookmarked);
          onBookmarkChange?.(changedOutfitId, nextBookmarked);
        }}
        onWornChange={(changedOutfitId, _nextWorn, nextTimesWorn, nextWornAt) => {
          const updatedTimesWorn = nextTimesWorn ?? timesWorn + 1;
          const wornAt = nextWornAt ?? new Date().toISOString();
          setTimesWorn(updatedTimesWorn);
          setLastWorn(wornAt);
          onWearSuccess?.(changedOutfitId, updatedTimesWorn, wornAt);
        }}
        onClose={() => setIsTryOnOpen(false)}
      />
    </>
  );
};
