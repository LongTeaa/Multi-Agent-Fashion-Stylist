'use client';

import React, { useState, useRef, useEffect } from 'react';
import { rateOutfit, dismissFeedbackPrompt, getStoredSessionId, ApiError } from '@/lib/api';

export interface RatingPromptProps {
  targetOutfitId: string;
  targetRank?: number;
  onRated?: (outfitId: string, stars: number) => void;
  onDismiss?: () => void;
  className?: string;
  testId?: string;
}

export const RatingPrompt: React.FC<RatingPromptProps> = ({
  targetOutfitId,
  targetRank,
  onRated,
  onDismiss,
  className = '',
  testId = 'rating-prompt',
}) => {
  const [hoverRating, setHoverRating] = useState<number | null>(null);
  const [selectedRating, setSelectedRating] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [isDismissing, setIsDismissing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const autoCloseTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    return () => {
      if (autoCloseTimerRef.current) {
        clearTimeout(autoCloseTimerRef.current);
      }
    };
  }, []);

  const handleRate = async (stars: number) => {
    if (!Number.isInteger(stars) || stars < 1 || stars > 5 || isSubmitting || isDismissing) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setSelectedRating(stars);

    try {
      const sessionId = getStoredSessionId();
      await rateOutfit(targetOutfitId, {
        stars,
        source: 'prompted',
        client_session_id: sessionId,
      });

      setSuccessMsg('Cảm ơn bạn đã phản hồi!');

      if (autoCloseTimerRef.current) {
        clearTimeout(autoCloseTimerRef.current);
      }
      autoCloseTimerRef.current = setTimeout(() => {
        onRated?.(targetOutfitId, stars);
        onDismiss?.();
      }, 1500);
    } catch (err) {
      setSelectedRating(null);
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Không thể lưu đánh giá lúc này. Vui lòng thử lại.';
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDismiss = async () => {
    if (isSubmitting || isDismissing) return;

    setIsDismissing(true);
    setError(null);

    try {
      const sessionId = getStoredSessionId();
      await dismissFeedbackPrompt({ client_session_id: sessionId });
      onDismiss?.();
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : 'Không thể đồng bộ trạng thái bỏ qua. Vui lòng thử lại.';
      setError(msg);
    } finally {
      setIsDismissing(false);
    }
  };

  return (
    <aside
      role="region"
      aria-label="Khảo sát đánh giá gợi ý phối đồ"
      data-testid={testId}
      className={`fixed bottom-6 right-6 z-50 max-w-md w-[calc(100vw-3rem)] bg-white/95 backdrop-blur-md rounded-2xl border border-[#E8E5DE] shadow-xl shadow-[#1A1918]/5 p-5 transition-all animate-fadeIn ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#9C5234]"></span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-[#9C5234]">
              Stylist Feedback
            </span>
            {targetRank !== undefined && (
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#F5F4F0] text-[#736E65]">
                Set #{targetRank}
              </span>
            )}
          </div>

          <h4 className="font-serif text-sm sm:text-base font-medium text-[#1A1918] leading-snug">
            Bạn chấm gợi ý vừa rồi mấy sao?
          </h4>
          <p className="text-xs text-[#5C564E] leading-relaxed">
            Đánh giá của bạn giúp AI tinh chỉnh gu thẩm mỹ cho các lần phối đồ sau.
          </p>
        </div>

        {/* Dismiss 'X' Button */}
        <button
          type="button"
          onClick={handleDismiss}
          disabled={isSubmitting || isDismissing || Boolean(successMsg)}
          aria-label="Đóng khảo sát đánh giá"
          className="p-1 rounded-lg text-[#736E65] hover:text-[#1A1918] hover:bg-[#F5F4F0] transition disabled:opacity-50"
        >
          ✕
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div
          role="alert"
          className="mt-3 px-3 py-1.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs"
        >
          {error}
        </div>
      )}

      {/* Success Confirmation */}
      {successMsg ? (
        <div className="mt-3 py-2 px-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs font-semibold flex items-center gap-1.5 animate-fadeIn">
          <span>✓</span>
          <span>{successMsg}</span>
        </div>
      ) : (
        /* 5-Star Interactive Rating Control */
        <div className="mt-4 flex items-center justify-between gap-2 flex-wrap">
          <div
            className="flex items-center gap-1"
            role="group"
            aria-label="Chọn số sao từ 1 đến 5"
          >
            {[1, 2, 3, 4, 5].map((star) => {
              const isFilled = (hoverRating ?? selectedRating ?? 0) >= star;
              return (
                <button
                  key={star}
                  type="button"
                  onClick={() => handleRate(star)}
                  onMouseEnter={() => setHoverRating(star)}
                  onMouseLeave={() => setHoverRating(null)}
                  onFocus={() => setHoverRating(star)}
                  onBlur={() => setHoverRating(null)}
                  disabled={isSubmitting || isDismissing}
                  aria-label={`Đánh giá ${star} sao`}
                  className="p-1 text-slate-300 hover:text-amber-400 dark:text-slate-600 dark:hover:text-amber-400 transition-transform active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-hidden"
                >
                  <svg
                    className={`w-6 h-6 transition-all ${
                      isFilled
                        ? 'text-amber-400 fill-amber-400 scale-110'
                        : 'text-slate-300 dark:text-slate-600 fill-none'
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

          <button
            type="button"
            onClick={handleDismiss}
            disabled={isSubmitting || isDismissing}
            className="text-xs font-semibold text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition px-2 py-1"
          >
            Để sau
          </button>
        </div>
      )}
    </aside>
  );
};
