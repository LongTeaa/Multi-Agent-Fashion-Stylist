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
        className="w-full bg-white rounded-3xl border border-[#E8E5DE] shadow-xs hover:border-[#D5D1C7] focus-within:border-[#1A1918] focus-within:ring-2 focus-within:ring-[#1A1918]/10 transition-all"
      >
        <div className="p-5 sm:p-6">
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
            suppressHydrationWarning
            placeholder={
              placeholder ||
              'Ví dụ: Tối nay tôi đi cafe ngoài trời ở Đà Lạt, thời tiết se lạnh, muốn set đồ thanh lịch nhẹ nhàng...'
            }
            className="w-full bg-transparent resize-none outline-none text-[#1A1918] placeholder-[#736E65] text-sm sm:text-base leading-relaxed font-sans"
          />

          {/* Location field (collapsible or toggled) */}
          {showLocationInput && (
            <div className="mt-3 pt-3 border-t border-[#E8E5DE] flex items-center gap-2">
              <span className="text-[#736E65] text-xs font-mono flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 text-[#9C5234]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
                className="flex-1 bg-[#FAF8F5] text-xs font-mono text-[#1A1918] px-3 py-1.5 rounded-xl border border-[#E8E5DE] outline-none focus:border-[#9C5234]"
              />
              <button
                type="button"
                onClick={() => {
                  setLocation('');
                  setShowLocationInput(false);
                }}
                className="text-[#736E65] hover:text-rose-600 text-xs p-1"
                aria-label="Xóa địa điểm"
              >
                ✕
              </button>
            </div>
          )}

          {/* Footer toolbar */}
          <div className="mt-4 pt-3 border-t border-[#E8E5DE] flex items-center justify-between text-xs text-[#736E65]">
            <div className="flex items-center gap-2.5">
              {!showLocationInput && (
                <button
                  type="button"
                  onClick={() => setShowLocationInput(true)}
                  className="tactile-btn inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-[#FAF8F5] hover:bg-[#F5F2EC] text-[#5C564E] hover:text-[#1A1918] border border-[#E8E5DE] font-mono text-xs transition"
                >
                  <svg className="w-3.5 h-3.5 text-[#9C5234]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
              <span className="hidden sm:inline text-[#736E65] text-[11px] font-mono">
                Nhấn <kbd className="px-1.5 py-0.5 rounded bg-[#FAF8F5] border border-[#E8E5DE] text-[#1A1918] font-mono text-[10px]">Enter ↵</kbd> để gửi
              </span>
            </div>

            <div className="flex items-center gap-3">
              <span
                className={`text-[11px] font-mono ${
                  isOverLimit ? 'text-rose-600 font-bold' : 'text-[#736E65]'
                }`}
              >
                {query.length}/1000
              </span>

              <button
                type="submit"
                disabled={!canSubmit}
                aria-busy={isLoading}
                suppressHydrationWarning
                className="tactile-btn group inline-flex items-center gap-2.5 pl-5 pr-2 py-2 rounded-full text-xs font-mono uppercase tracking-wider text-white bg-[#1A1918] hover:bg-[#2D2420] disabled:opacity-40 disabled:cursor-not-allowed shadow-xs transition-all active:scale-95"
              >
                {isLoading ? (
                  <>
                    <svg
                      className="animate-spin -ml-0.5 mr-1 h-3.5 w-3.5 text-white"
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
                    <span className="w-6 h-6 rounded-full bg-white/15 flex items-center justify-center group-hover:translate-x-0.5 transition-all text-xs">
                      →
                    </span>
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
