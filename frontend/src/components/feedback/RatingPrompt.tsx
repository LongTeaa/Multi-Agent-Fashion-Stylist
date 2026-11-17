'use client';

import React, { useState, useRef, useEffect } from 'react';
import { rateOutfit, dismissFeedbackPrompt, getStoredSessionId, ApiError } from '@/lib/api';
import { CheckIcon, CloseIcon, StarIcon } from '@/components/ui/icons';
import { formatLookNumber } from '@/lib/looks';

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
      className={`card fixed inset-x-4 bottom-24 z-50 animate-rise p-5 shadow-[0_20px_50px_-20px_rgb(28_25_22/0.35)] sm:inset-x-auto sm:right-6 sm:w-[24rem] md:bottom-6 ${className}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {targetRank !== undefined && (
            <span className="hang-tag mb-2">{formatLookNumber(targetRank)}</span>
          )}
          <h4 className="display text-lg">Bạn chấm gợi ý vừa rồi mấy sao?</h4>
          <p className="mt-1 text-sm leading-relaxed text-ink-2">
            Mỗi lần chấm giúp các gợi ý sau hợp gu bạn hơn.
          </p>
        </div>

        <button
          type="button"
          onClick={handleDismiss}
          disabled={isSubmitting || isDismissing || Boolean(successMsg)}
          aria-label="Đóng khảo sát đánh giá"
          className="btn btn-ghost btn-icon -mr-2 -mt-2 shrink-0"
        >
          <CloseIcon size={16} />
        </button>
      </div>

      {error && (
        <div role="alert" className="notice notice-danger mt-3 py-2 text-xs">
          {error}
        </div>
      )}

      {successMsg ? (
        <div className="notice notice-success mt-3 animate-rise py-2 text-sm font-semibold">
          <CheckIcon size={16} />
          <span>{successMsg}</span>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-0.5" role="group" aria-label="Chọn số sao từ 1 đến 5">
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
                  className={`rounded-md p-1 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    isFilled ? 'text-accent' : 'text-line-strong hover:text-accent'
                  }`}
                >
                  <StarIcon size={26} filled={isFilled} />
                </button>
              );
            })}
          </div>

          <button
            type="button"
            onClick={handleDismiss}
            disabled={isSubmitting || isDismissing}
            className="btn btn-ghost btn-sm"
          >
            Để sau
          </button>
        </div>
      )}
    </aside>
  );
};
