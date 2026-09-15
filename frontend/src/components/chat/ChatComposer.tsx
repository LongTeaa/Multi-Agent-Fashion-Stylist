'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';

export interface ChatComposerRef {
  focus: () => void;
  setQueryText: (text: string) => void;
}

interface ChatComposerProps {
  onSend: (query: string, location?: string) => void;
  isLoading: boolean;
  placeholder?: string;
  defaultLocation?: string;
}

export const ChatComposer = forwardRef<ChatComposerRef, ChatComposerProps>(
  ({ onSend, isLoading, placeholder, defaultLocation }, ref) => {
    const [query, setQuery] = useState('');
    const [location, setLocation] = useState(defaultLocation || '');
    const [showLocationInput, setShowLocationInput] = useState(Boolean(defaultLocation));
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useImperativeHandle(ref, () => ({
      focus: () => {
        textareaRef.current?.focus();
      },
      setQueryText: (text: string) => {
        setQuery(text);
        textareaRef.current?.focus();
      },
    }));

    // Auto-resize textarea
    useEffect(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
      }
    }, [query]);

    const handleSubmit = (e?: React.FormEvent) => {
      if (e) e.preventDefault();
      const trimmed = query.trim();
      // Strictly enforce min_length=1 and max_length=1000 per API Contract
      if (!trimmed || trimmed.length > 1000 || isLoading) return;

      const trimmedLocation = location.trim().slice(0, 200);
      onSend(trimmed, trimmedLocation || undefined);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    };

    const isOverLimit = query.length > 1000;
    const canSubmit = query.trim().length > 0 && !isOverLimit && !isLoading;

    return (
      <form
        onSubmit={handleSubmit}
        role="form"
        aria-label="Khung gửi câu hỏi tư vấn phối đồ"
        className="w-full bg-white dark:bg-slate-800/90 rounded-2xl border border-slate-200 dark:border-slate-700/80 shadow-lg shadow-indigo-500/5 transition-all focus-within:border-indigo-500 dark:focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-500/20"
      >
        <div className="p-4 sm:p-5">
          {/* Main prompt input */}
          <label htmlFor="stylist-query-input" className="sr-only">
            Nhu cầu phối đồ của bạn
          </label>
          <textarea
            id="stylist-query-input"
            ref={textareaRef}
            rows={2}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            maxLength={1000}
            placeholder={
              placeholder ||
              'Ví dụ: Tối nay tôi đi cafe ngoài trời ở Đà Lạt, thời tiết se lạnh, muốn set đồ thanh lịch nhẹ nhàng...'
            }
            className="w-full bg-transparent resize-none outline-none text-slate-800 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 text-sm sm:text-base leading-relaxed"
          />

          {/* Location field (collapsible or toggled) */}
          {showLocationInput && (
            <div className="mt-3 pt-3 border-t border-slate-100 dark:border-slate-700/50 flex items-center gap-2">
              <span className="text-slate-400 dark:text-slate-500 text-xs font-medium flex items-center gap-1">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                </svg>
                Địa điểm:
              </span>
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                disabled={isLoading}
                maxLength={200}
                placeholder="Ví dụ: Hà Nội, Đà Lạt, TP. Hồ Chí Minh..."
                className="flex-1 bg-slate-50 dark:bg-slate-900/50 text-xs text-slate-700 dark:text-slate-200 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-700 outline-none focus:border-indigo-500"
              />
              <button
                type="button"
                onClick={() => {
                  setLocation('');
                  setShowLocationInput(false);
                }}
                className="text-slate-400 hover:text-slate-600 text-xs p-1"
                aria-label="Xóa địa điểm"
              >
                ✕
              </button>
            </div>
          )}

          {/* Footer toolbar */}
          <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-2">
              {!showLocationInput && (
                <button
                  type="button"
                  onClick={() => setShowLocationInput(true)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-700/60 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 font-medium transition"
                >
                  <svg className="w-3.5 h-3.5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"
                    />
                  </svg>
                  <span>+ Thêm địa điểm</span>
                </button>
              )}
              <span className="hidden sm:inline text-slate-400 text-[11px]">
                Nhấn <kbd className="px-1 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-500 font-sans">Enter ↵</kbd> để gửi
              </span>
            </div>

            <div className="flex items-center gap-3">
              <span
                className={`text-[11px] ${
                  isOverLimit ? 'text-rose-500 font-bold' : 'text-slate-400'
                }`}
              >
                {query.length}/1000
              </span>

              <button
                type="submit"
                disabled={!canSubmit}
                aria-busy={isLoading}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed shadow-md shadow-indigo-500/20 transition active:scale-95"
              >
                {isLoading ? (
                  <>
                    <svg
                      className="animate-spin -ml-0.5 mr-1 h-4 w-4 text-white"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    <span>Stylist đang phối...</span>
                  </>
                ) : (
                  <>
                    <span>Phối Đồ</span>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M13 7l5 5m0 0l-5 5m5-5H6"
                      />
                    </svg>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      </form>
    );
  }
);

ChatComposer.displayName = 'ChatComposer';
