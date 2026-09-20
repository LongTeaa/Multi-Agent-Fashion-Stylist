'use client';

import React, { useState, useRef, useEffect } from 'react';
import { setOutfitBookmark, recordOutfitWorn, rateOutfit, ApiError } from '@/lib/api';
import { PrivateMediaImage } from '@/components/media/PrivateMediaImage';
import type { StylistRecommendationItem } from '@/types/chat';
import type { OutfitItemDetailResponse } from '@/types/outfits';
import { TryOnModal } from '@/components/tryon/TryOnModal';

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
  primaryColor?: string;
  isActive?: boolean;
}

export function normalizeStylistItems(items: StylistRecommendationItem[]): NormalizedOutfitItem[] {
  return items.map((it) => ({
    id: it.item_id,
    slot: it.slot,
    name: it.name,
    imageUrl: it.image_url,
    isActive: true,
  }));
}

export function normalizeDetailItems(items: OutfitItemDetailResponse[]): NormalizedOutfitItem[] {
  return items.map((it) => ({
    id: it.wardrobe_item_id,
    slot: it.slot_role,
    name: it.name,
    imageUrl: it.image_url,
    category: it.category,
    subCategory: it.sub_category,
    primaryColor: it.primary_color,
    isActive: it.is_active,
  }));
}

const SLOT_NAMES: Record<string, string> = {
  top: 'Áo',
  bottom: 'Quần / Chân váy',
  dress: 'Đầm / Váy liền',
  footwear: 'Giày / Dép',
  outerwear: 'Áo khoác',
  accessory: 'Phụ kiện',
};

export interface OutfitCardProps {
  outfitId: string;
  rank?: number;
  compositeScore?: number;
  explanationVi: string;
  appliedPreferences?: string[];
  items: NormalizedOutfitItem[];
  initialIsBookmarked?: boolean;
  initialTimesWorn?: number;
  initialRating?: number | null;
  lastWornAt?: string | null;
  onBookmarkChange?: (outfitId: string, isBookmarked: boolean) => void;
  onWearSuccess?: (outfitId: string, timesWorn: number) => void;
  onRatingChange?: (outfitId: string, rating: number) => void;
  className?: string;
  testId?: string;
}

export const OutfitCard: React.FC<OutfitCardProps> = ({
  outfitId,
  rank,
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
      setWearSuccessMsg(
        res.already_processed
          ? 'Đã ghi nhận mặc trước đó!'
          : 'Đã ghi nhận bạn mặc bộ này!'
      );

      // Successfully processed: cycle idempotency key for future wears
      idempotencyKeyRef.current = generateUUIDv4();

      onWearSuccess?.(outfitId, res.times_worn);

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

  return (
    <>
    <article
      data-testid={testId}
      data-outfit-id={outfitId}
      className={`w-full bg-white rounded-3xl border border-[#E8E5DE] shadow-xs overflow-hidden transition-all hover:shadow-md ${className}`}
    >
      {/* Card Header */}
      <div className="px-5 sm:px-6 py-4 border-b border-[#E8E5DE] bg-white flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          {rank !== undefined && (
            <span
              className={`px-3 py-1 rounded-full text-xs font-mono font-semibold shrink-0 ${
                rank === 1
                  ? 'bg-[#1A1918] text-[#FBFBF9] shadow-2xs'
                  : rank === 2
                  ? 'bg-[#FAF8F5] text-[#1A1918] border border-[#D5D1C7]'
                  : 'bg-[#FAF8F5] text-[#736E65] border border-[#E8E5DE]'
              }`}
            >
              #{rank}
            </span>
          )}

          <h3 className="font-serif text-base sm:text-lg font-medium text-[#1A1918] truncate">
            {rank !== undefined ? `Gợi Ý Phối Đồ Số ${rank}` : 'Bộ Trang Phục Phối Sẵn'}
          </h3>

          {matchPercentage !== null && (
            <span className="px-3 py-1 rounded-full text-xs font-mono font-semibold bg-[#9C5234]/10 text-[#9C5234] border border-[#9C5234]/25 shrink-0">
              <span>{matchPercentage}%</span>{' '}
              <span className="font-normal text-[11px] opacity-85">phù hợp</span>
            </span>
          )}
        </div>

        {/* Header Actions: Bookmark & Wear Badge */}
        <div className="flex items-center gap-2.5 shrink-0">
          <span className="hidden sm:inline-flex items-center gap-1.5 text-xs font-mono text-[#736E65]">
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{timesWorn > 0 ? `Đã mặc ${timesWorn} lần` : 'Chưa mặc'}</span>
          </span>

          {/* Bookmark Button (Optimistic) */}
          <button
            type="button"
            onClick={handleToggleBookmark}
            disabled={isBookmarkPending}
            aria-label={isBookmarked ? 'Bỏ lưu bộ đồ này' : 'Lưu bộ đồ này'}
            aria-pressed={isBookmarked}
            className={`p-2 rounded-xl border transition-all ${
              isBookmarked
                ? 'bg-amber-50 border-amber-300 text-amber-600 shadow-2xs'
                : 'bg-[#FAF8F5] border-[#E8E5DE] text-[#736E65] hover:text-[#1A1918] hover:border-[#D5D1C7]'
            }`}
          >
            <svg
              className={`w-4 h-4 transition-transform ${isBookmarkPending ? 'scale-90 opacity-60' : 'scale-100'}`}
              fill={isBookmarked ? 'currentColor' : 'none'}
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Card Body */}
      <div className="p-5 sm:p-6">
        {/* Error notification for bookmark */}
        {bookmarkError && (
          <div
            role="alert"
            className="mb-4 px-3.5 py-2 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between"
          >
            <span>{bookmarkError}</span>
            <button
              type="button"
              onClick={() => setBookmarkError(null)}
              className="text-rose-500 hover:text-rose-700 font-bold ml-2"
            >
              ✕
            </button>
          </div>
        )}

        {/* Stylist Explanation */}
        <p className="font-serif text-base text-[#1A1918] italic leading-relaxed border-l-2 border-[#9C5234] pl-4 my-5 bg-[#FAF8F5]/60 py-3.5 px-4 rounded-r-2xl">
          &ldquo;{explanationVi}&rdquo;
        </p>

        {/* Garment Items Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
          {items.map((item) => {
            const imageUrl = item.imageUrl;
            const slotName = SLOT_NAMES[item.slot] || item.slot;

            return (
              <div
                key={item.id}
                className={`flex sm:flex-col items-center sm:items-start gap-3 p-3.5 rounded-2xl border transition-all ${
                  item.isActive === false
                    ? 'bg-[#FAF8F5]/70 border-dashed border-rose-300 opacity-85'
                    : 'bg-[#FAF8F5] border-[#E8E5DE] hover:border-[#D5D1C7]'
                }`}
              >
                {/* Thumbnail with Alt Text */}
                <div className="w-16 h-16 sm:w-full sm:h-36 rounded-xl bg-white border border-[#E8E5DE] overflow-hidden relative shrink-0 flex items-center justify-center">
                  {imageUrl ? (
                    <PrivateMediaImage
                      source={imageUrl}
                      alt={`Ảnh của ${item.name} (${slotName})`}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex flex-col items-center justify-center gap-1.5 p-2 text-center">
                      <svg className="w-6 h-6 text-[#D5D1C7]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
                      </svg>
                      <span className="text-[#736E65] text-xs font-mono">Không có ảnh</span>
                    </div>
                  )}
                  <span className="absolute top-2 left-2 px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-[#1A1918]/85 text-[#FBFBF9] backdrop-blur-xs">
                    {slotName}
                  </span>

                  {item.isActive === false && (
                    <span className="absolute bottom-2 right-2 px-2 py-0.5 rounded-full text-[10px] font-mono bg-rose-600 text-white shadow-xs">
                      Đã xóa khỏi tủ
                    </span>
                  )}
                </div>

                {/* Info */}
                <div className="min-w-0 flex-1">
                  <h4 className="text-xs sm:text-sm font-semibold text-[#1A1918] truncate">
                    {item.name}
                  </h4>
                  <span className="text-[11px] font-mono text-[#736E65] capitalize block mt-0.5">
                    Vị trí: {slotName}
                  </span>
                  {item.primaryColor && (
                    <span className="text-[10px] font-mono text-[#736E65] block truncate mt-0.5">
                      Màu: {item.primaryColor}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Applied Preferences */}
        {appliedPreferences.length > 0 && (
          <div className="mt-4 pt-3 border-t border-[#E8E5DE] flex items-center gap-2 flex-wrap">
            <span className="text-xs font-mono text-[#736E65]">Đã áp dụng gu thời trang:</span>
            {appliedPreferences.map((pref, idx) => (
              <span
                key={idx}
                className="px-3 py-1 rounded-full text-xs font-mono bg-[#FAF8F5] text-[#1A1918] border border-[#E8E5DE]"
              >
                ✓ {pref}
              </span>
            ))}
          </div>
        )}

        {/* Card Footer: Wear Log Action Button & Rating Controls */}
        <div className="mt-5 pt-4 border-t border-[#E8E5DE] flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsTryOnOpen(true)}
              aria-label="Xem ảnh minh họa bộ trang phục"
              className="tactile-btn rounded-full bg-[#9C5234] px-4 py-2 text-xs font-mono uppercase tracking-wider text-white transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#82452E] active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
            >
              Xem minh họa
            </button>
            <button
              type="button"
              onClick={handleRecordWorn}
              disabled={isWearPending}
              aria-label="Xác nhận đã mặc bộ trang phục này hôm nay"
              className="tactile-btn inline-flex items-center gap-2 px-4 py-2 rounded-full text-xs font-mono uppercase tracking-wider bg-white border border-[#D5D1C7] text-[#1A1918] hover:bg-[#1A1918] hover:text-[#FBFBF9] hover:border-[#1A1918] disabled:opacity-50 disabled:cursor-not-allowed transition shadow-2xs"
            >
              {isWearPending ? (
                <>
                  <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Đang ghi nhận...</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5 text-[#9C5234]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>Đã Mặc Hôm Nay</span>
                </>
              )}
            </button>

            {/* Mobile times worn indicator */}
            <span className="sm:hidden text-[11px] text-slate-400">
              Đã mặc {timesWorn} lần
            </span>

            {wearSuccessMsg && (
              <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 animate-fadeIn flex items-center gap-1">
                ✓ {wearSuccessMsg}
              </span>
            )}

            {wearError && (
              <span className="text-xs font-semibold text-rose-600 dark:text-rose-400 animate-fadeIn flex items-center gap-1">
                ✕ {wearError}
              </span>
            )}
          </div>

          {/* Manual Star Rating Control (1-5 stars) */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] font-mono text-[#736E65]">Đánh giá:</span>
            <div
              className="flex items-center"
              role="group"
              aria-label="Đánh giá bộ trang phục từ 1 đến 5 sao"
            >
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
                    className="p-1 text-[#D5D1C7] hover:text-amber-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed focus:outline-hidden"
                  >
                    <svg
                      className={`w-4 h-4 transition-transform ${
                        isFilled
                          ? 'text-amber-500 fill-amber-500 scale-105'
                          : 'text-[#D5D1C7] fill-none'
                      }`}
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
                      />
                    </svg>
                  </button>
                );
              })}
            </div>

            {userRating && (
              <span className="text-xs font-mono font-bold text-amber-600 ml-0.5">
                {userRating}/5★
              </span>
            )}

            {ratingSuccessMsg && (
              <span className="text-xs font-mono font-semibold text-emerald-600 animate-fadeIn ml-1">
                ✓ {ratingSuccessMsg}
              </span>
            )}

            {ratingError && (
              <span className="text-xs font-mono font-semibold text-rose-600 animate-fadeIn ml-1">
                ✕ {ratingError}
              </span>
            )}

            {lastWornAt && !wearSuccessMsg && (
              <span className="text-[11px] font-mono text-[#736E65] ml-2 hidden sm:inline" suppressHydrationWarning>
                Mặc gần nhất: {new Date(lastWornAt).toLocaleDateString('vi-VN')}
              </span>
            )}
          </div>
        </div>
      </div>
    </article>
    <TryOnModal
      isOpen={isTryOnOpen}
      outfitId={outfitId}
      items={items}
      isBookmarked={isBookmarked}
      onBookmarkChange={(changedOutfitId, nextBookmarked) => {
        setIsBookmarked(nextBookmarked);
        onBookmarkChange?.(changedOutfitId, nextBookmarked);
      }}
      onClose={() => setIsTryOnOpen(false)}
    />
    </>
  );
};
