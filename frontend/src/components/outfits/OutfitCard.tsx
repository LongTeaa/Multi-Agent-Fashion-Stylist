'use client';

import React, { useState, useRef, useEffect } from 'react';
import { setOutfitBookmark, recordOutfitWorn, getMediaUrl, ApiError } from '@/lib/api';
import type { StylistRecommendationItem } from '@/types/chat';
import type { OutfitItemDetailResponse } from '@/types/outfits';

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
  bottom: 'Quần / Váy',
  shoes: 'Giày / Dép',
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
  lastWornAt?: string | null;
  onBookmarkChange?: (outfitId: string, isBookmarked: boolean) => void;
  onWearSuccess?: (outfitId: string, timesWorn: number) => void;
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
  lastWornAt,
  onBookmarkChange,
  onWearSuccess,
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

  // Idempotency key generated once per user intent session, preserved on retry
  const idempotencyKeyRef = useRef<string>('');
  const wearTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (wearTimerRef.current) {
        clearTimeout(wearTimerRef.current);
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

  return (
    <article
      data-testid={testId}
      data-outfit-id={outfitId}
      className={`w-full bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700/80 shadow-sm overflow-hidden transition-all hover:shadow-md ${className}`}
    >
      {/* Card Header */}
      <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-700/60 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          {rank !== undefined && (
            <span
              className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-black shrink-0 ${
                rank === 1
                  ? 'bg-amber-500 text-white shadow-xs shadow-amber-500/30'
                  : rank === 2
                  ? 'bg-slate-400 text-white'
                  : 'bg-amber-800 text-amber-100'
              }`}
            >
              #{rank}
            </span>
          )}

          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-100 truncate">
            {rank !== undefined ? `Gợi Ý Phối Đồ Số ${rank}` : 'Bộ Trang Phục Phối Sẵn'}
          </h3>

          {matchPercentage !== null && (
            <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200/60 dark:border-indigo-800/60 shrink-0">
              <span>{matchPercentage}%</span>{' '}
              <span className="font-medium text-[11px] opacity-80">phù hợp</span>
            </span>
          )}
        </div>

        {/* Header Actions: Bookmark & Wear Badge */}
        <div className="flex items-center gap-2 shrink-0">
          <span className="hidden sm:inline-flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400 font-medium">
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
                ? 'bg-amber-50 dark:bg-amber-950/50 border-amber-300 dark:border-amber-700 text-amber-600 dark:text-amber-400 shadow-xs'
                : 'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:border-slate-300'
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
      <div className="p-5">
        {/* Error notification for bookmark */}
        {bookmarkError && (
          <div
            role="alert"
            className="mb-3 px-3 py-1.5 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center justify-between"
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
        <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed italic border-l-2 border-indigo-500 pl-3 mb-5">
          &ldquo;{explanationVi}&rdquo;
        </p>

        {/* Garment Items Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
          {items.map((item) => {
            const imageUrl = item.imageUrl ? getMediaUrl(item.imageUrl) : null;
            const slotName = SLOT_NAMES[item.slot] || item.slot;

            return (
              <div
                key={item.id}
                className={`flex sm:flex-col items-center sm:items-start gap-3 p-3 rounded-xl border transition-all ${
                  item.isActive === false
                    ? 'bg-slate-100/70 dark:bg-slate-900/30 border-dashed border-rose-300 dark:border-rose-900/60 opacity-85'
                    : 'bg-slate-50 dark:bg-slate-900/50 border-slate-100 dark:border-slate-800'
                }`}
              >
                {/* Thumbnail with Alt Text */}
                <div className="w-16 h-16 sm:w-full sm:h-36 rounded-lg bg-slate-200 dark:bg-slate-800 overflow-hidden relative shrink-0 flex items-center justify-center">
                  {imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={imageUrl}
                      alt={`Ảnh của ${item.name} (${slotName})`}
                      className="w-full h-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <span className="text-slate-400 text-xs font-medium">Không có ảnh</span>
                  )}
                  <span className="absolute top-1.5 left-1.5 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-black/60 text-white backdrop-blur-xs">
                    {slotName}
                  </span>

                  {item.isActive === false && (
                    <span className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded text-[9px] font-bold bg-rose-600 text-white shadow-xs">
                      Đã xóa khỏi tủ
                    </span>
                  )}
                </div>

                {/* Info */}
                <div className="min-w-0 flex-1">
                  <h4 className="text-xs sm:text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">
                    {item.name}
                  </h4>
                  <span className="text-[11px] text-slate-400 capitalize block">
                    Vị trí: {slotName}
                  </span>
                  {item.primaryColor && (
                    <span className="text-[10px] text-slate-500 dark:text-slate-400 block truncate">
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
          <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] text-slate-400 font-medium">Đã áp dụng gu thời trang:</span>
            {appliedPreferences.map((pref, idx) => (
              <span
                key={idx}
                className="px-2 py-0.5 rounded-md text-[10px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
              >
                ✓ {pref}
              </span>
            ))}
          </div>
        )}

        {/* Card Footer: Wear Log Action Button */}
        <div className="mt-5 pt-3.5 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRecordWorn}
              disabled={isWearPending}
              aria-label="Xác nhận đã mặc bộ trang phục này hôm nay"
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-semibold text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-slate-800 hover:bg-indigo-50 dark:hover:bg-indigo-950/50 hover:text-indigo-600 dark:hover:text-indigo-400 border border-slate-200 dark:border-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
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
                  <svg className="w-3.5 h-3.5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
          </div>

          {/* Feedback Badges */}
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

          {lastWornAt && !wearSuccessMsg && (
            <span className="text-[11px] text-slate-400">
              Lần gần nhất: {new Date(lastWornAt).toLocaleDateString('vi-VN')}
            </span>
          )}
        </div>
      </div>
    </article>
  );
};
