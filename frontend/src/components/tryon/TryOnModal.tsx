'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, createTryOn, getMediaUrl, setOutfitBookmark } from '@/lib/api';
import type { TryOnDisplayItem, TryOnResponseData } from '@/types/tryons';

const SLOT_NAMES: Record<string, string> = {
  top: 'Áo',
  bottom: 'Quần / Váy',
  dress: 'Đầm / Váy liền',
  footwear: 'Giày / Dép',
  outerwear: 'Áo khoác',
  accessory: 'Phụ kiện',
};

export interface TryOnModalProps {
  isOpen: boolean;
  outfitId: string;
  items: TryOnDisplayItem[];
  isBookmarked: boolean;
  onBookmarkChange: (outfitId: string, isBookmarked: boolean) => void;
  onClose: () => void;
}

export function TryOnModal({
  isOpen,
  outfitId,
  items,
  isBookmarked,
  onBookmarkChange,
  onClose,
}: TryOnModalProps) {
  const [result, setResult] = useState<TryOnResponseData | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previousIsBookmarked, setPreviousIsBookmarked] = useState(isBookmarked);
  const [saved, setSaved] = useState(isBookmarked);
  const [isSaving, setIsSaving] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef<number>(0);

  const generate = useCallback(async () => {
    // Abort any pending in-flight request before launching a new one
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    requestIdRef.current += 1;
    const currentRequestId = requestIdRef.current;

    setIsGenerating(true);
    setError(null);
    try {
      const res = await createTryOn(outfitId, { signal: controller.signal });
      if (requestIdRef.current === currentRequestId) {
        setResult(res);
      }
    } catch (requestError) {
      if (
        (requestError instanceof DOMException || requestError instanceof Error) &&
        requestError.name === 'AbortError'
      ) {
        // Intentionally aborted; do not mutate state with error
        return;
      }
      if (requestIdRef.current === currentRequestId) {
        setError(
          requestError instanceof ApiError
            ? requestError.message
            : 'Không thể tạo ảnh minh họa lúc này. Vui lòng thử lại.'
        );
      }
    } finally {
      if (requestIdRef.current === currentRequestId) {
        setIsGenerating(false);
      }
    }
  }, [outfitId]);

  if (isBookmarked !== previousIsBookmarked) {
    setPreviousIsBookmarked(isBookmarked);
    setSaved(isBookmarked);
  }

  useEffect(() => {
    if (!isOpen) {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      return;
    }
    const generationTask = window.setTimeout(() => void generate(), 0);
    return () => {
      window.clearTimeout(generationTask);
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, [generate, isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  const toggleBookmark = async () => {
    if (isSaving) return;
    const nextSaved = !saved;
    setIsSaving(true);
    setError(null);
    try {
      await setOutfitBookmark(outfitId, nextSaved);
      setSaved(nextSaved);
      onBookmarkChange(outfitId, nextSaved);
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : 'Không thể cập nhật trạng thái lưu. Vui lòng thử lại.'
      );
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  const renderLabel = result?.render_kind === 'moodboard'
    ? 'Moodboard dự phòng'
    : 'Ảnh minh họa AI';

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-[#1A1918]/65 px-0 backdrop-blur-sm sm:items-center sm:px-5"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Xem trước bộ trang phục"
        className="max-h-[94dvh] w-full max-w-5xl overflow-y-auto rounded-t-[2rem] bg-[#E8E5DE] p-1.5 shadow-[0_24px_80px_rgba(42,34,29,0.28)] sm:rounded-[2rem]"
      >
        <div className="rounded-t-[calc(2rem-0.375rem)] bg-[#FBFBF9] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] sm:rounded-[calc(2rem-0.375rem)] sm:p-6">
          <header className="flex items-start justify-between gap-5 pb-5">
            <div className="max-w-xl">
              <h2 className="font-serif text-2xl tracking-tight text-[#1A1918] sm:text-3xl">
                Xem trước bộ trang phục
              </h2>
              <p className="mt-1.5 max-w-[58ch] text-sm leading-relaxed text-[#5C564E]">
                Hình ảnh chỉ mang tính minh họa, không mô phỏng chính xác kích thước hoặc độ vừa vặn.
              </p>
            </div>
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              className="shrink-0 rounded-full bg-[#F1EEE8] px-4 py-2 text-xs font-semibold text-[#1A1918] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#E2DDD3] active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
            >
              Đóng
            </button>
          </header>

          <div className="grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,1.35fr)_minmax(17rem,0.65fr)]">
            <div className="min-h-[24rem] overflow-hidden rounded-[1.5rem] bg-[#EEEAE2] p-1.5">
              <div className="flex min-h-[24rem] items-center justify-center overflow-hidden rounded-[calc(1.5rem-0.375rem)] bg-[#F5F2EC]">
                {isGenerating && (
                  <div role="status" className="w-full space-y-4 px-8 text-center">
                    <div className="mx-auto aspect-[3/4] w-full max-w-sm animate-pulse rounded-2xl bg-[#DDD7CD]" />
                    <p className="text-sm font-medium text-[#5C564E]">Đang tạo ảnh minh họa...</p>
                  </div>
                )}

                {!isGenerating && result && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={getMediaUrl(result.image_url)}
                    alt={`${renderLabel} cho bộ trang phục`}
                    className="max-h-[68dvh] w-full object-contain"
                  />
                )}

                {!isGenerating && !result && error && (
                  <div className="max-w-md px-8 py-14 text-center">
                    <p role="alert" className="text-sm leading-relaxed text-rose-800">{error}</p>
                    <button
                      type="button"
                      onClick={() => void generate()}
                      className="mt-5 rounded-full bg-[#1A1918] px-5 py-2.5 text-sm font-semibold text-[#FBFBF9] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#302B27] active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
                    >
                      Thử tạo lại
                    </button>
                  </div>
                )}
              </div>
            </div>

            <aside className="flex flex-col rounded-[1.5rem] bg-white px-5 pb-5 pt-4 shadow-[0_14px_42px_rgba(85,68,55,0.08)]">
              {result && (
                <div className="mb-4 flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold text-[#9C5234]">{renderLabel}</span>
                  <span className="font-mono text-xs tabular-nums text-[#736E65]">
                    {(result.duration_ms / 1000).toFixed(1)} giây
                  </span>
                </div>
              )}

              <h3 className="text-sm font-semibold text-[#1A1918]">Các món trong bộ</h3>
              <div className="mt-3 space-y-2.5">
                {items.map((item) => (
                  <div key={item.id} className="grid grid-cols-[3rem_1fr] items-center gap-3 rounded-2xl bg-[#F7F5F1] p-2.5">
                    <div className="h-12 w-12 overflow-hidden rounded-xl bg-[#E8E5DE]">
                      {item.imageUrl && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={getMediaUrl(item.imageUrl)}
                          alt={`Ảnh ${item.name}`}
                          className="h-full w-full object-cover"
                        />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-[#1A1918]">{item.name}</p>
                      <p className="mt-0.5 text-xs text-[#736E65]">
                        {SLOT_NAMES[item.slot] ?? item.slot}
                        {item.primaryColor ? `, ${item.primaryColor}` : ''}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {error && result && <p role="alert" className="mt-4 text-xs leading-relaxed text-rose-800">{error}</p>}

              <div className="mt-auto grid grid-cols-1 gap-2 pt-5 sm:grid-cols-2 md:grid-cols-1">
                <button
                  type="button"
                  onClick={() => void generate()}
                  disabled={isGenerating}
                  aria-label="Tạo lại ảnh minh họa"
                  className="rounded-full bg-[#1A1918] px-5 py-3 text-sm font-semibold text-[#FBFBF9] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#302B27] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
                >
                  {isGenerating ? 'Đang tạo...' : 'Tạo lại'}
                </button>
                <button
                  type="button"
                  onClick={() => void toggleBookmark()}
                  disabled={isSaving}
                  aria-label={saved ? 'Bỏ lưu bộ đồ' : 'Lưu bộ đồ'}
                  aria-pressed={saved}
                  className="rounded-full bg-[#EEEAE2] px-5 py-3 text-sm font-semibold text-[#1A1918] transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] hover:bg-[#E2DDD3] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-55 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9C5234]"
                >
                  {isSaving ? 'Đang lưu...' : saved ? 'Bỏ lưu' : 'Lưu bộ đồ'}
                </button>
              </div>
            </aside>
          </div>
        </div>
      </section>
    </div>
  );
}
