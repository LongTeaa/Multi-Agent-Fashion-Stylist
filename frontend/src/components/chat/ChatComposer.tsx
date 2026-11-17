'use client';

import React, { useState, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { ArrowRightIcon, CloseIcon, PinIcon, Spinner } from '@/components/ui/icons';

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

const MAX_QUERY_LENGTH = 1000;
const COUNTER_THRESHOLD = 800;

export const ChatComposer = forwardRef<ChatComposerRef, ChatComposerProps>(
  ({ onSend, isLoading, placeholder, defaultLocation }, ref) => {
    const [query, setQuery] = useState('');
    const [location, setLocation] = useState(defaultLocation || '');
    const [showLocationInput, setShowLocationInput] = useState(Boolean(defaultLocation));
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const locationRef = useRef<HTMLInputElement>(null);

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
        textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
      }
    }, [query]);

    const handleSubmit = (e?: React.FormEvent) => {
      if (e) e.preventDefault();
      const trimmed = query.trim();
      // API contract: 1..1000 characters.
      if (!trimmed || trimmed.length > MAX_QUERY_LENGTH || isLoading) return;

      const trimmedLocation = location.trim().slice(0, 200);
      onSend(trimmed, trimmedLocation || undefined);
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    };

    const isOverLimit = query.length > MAX_QUERY_LENGTH;
    const canSubmit = query.trim().length > 0 && !isOverLimit && !isLoading;

    return (
      <form
        onSubmit={handleSubmit}
        role="form"
        aria-label="Khung gửi câu hỏi tư vấn phối đồ"
        className="card p-2 transition-[border-color,box-shadow] focus-within:border-ink focus-within:shadow-[0_8px_30px_-14px_rgb(28_25_22/0.25)]"
      >
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
          maxLength={MAX_QUERY_LENGTH}
          suppressHydrationWarning
          placeholder={
            placeholder || 'Ví dụ: tối nay đi cafe ngoài trời ở Đà Lạt, trời se lạnh, muốn mặc thanh lịch nhẹ nhàng'
          }
          className="block w-full resize-none bg-transparent px-3 pt-2.5 text-[1rem] leading-relaxed text-ink outline-none placeholder:text-muted disabled:text-muted"
        />

        <div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-0.5 pt-2">
          <div className="flex min-w-0 flex-1 items-center">
            {showLocationInput ? (
              <div className="flex min-w-0 max-w-xs flex-1 items-center gap-1.5 rounded-full bg-sunken py-1 pl-3 pr-1">
                <PinIcon size={15} className="shrink-0 text-accent" />
                <input
                  ref={locationRef}
                  type="text"
                  aria-label="Địa điểm"
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  disabled={isLoading}
                  maxLength={200}
                  placeholder="Hà Nội, Đà Lạt…"
                  className="min-w-0 flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-muted"
                />
                <button
                  type="button"
                  onClick={() => {
                    setLocation('');
                    setShowLocationInput(false);
                  }}
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-muted hover:bg-line hover:text-ink"
                  aria-label="Xóa địa điểm"
                >
                  <CloseIcon size={14} />
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setShowLocationInput(true);
                  requestAnimationFrame(() => locationRef.current?.focus());
                }}
                className="btn btn-ghost btn-sm"
              >
                <PinIcon size={15} />
                Thêm địa điểm
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            {query.length >= COUNTER_THRESHOLD && (
              <span className={`text-xs tabular-nums ${isOverLimit ? 'font-semibold text-danger' : 'text-muted'}`}>
                {query.length}/{MAX_QUERY_LENGTH}
              </span>
            )}
            <button
              type="submit"
              disabled={!canSubmit}
              aria-busy={isLoading}
              suppressHydrationWarning
              className="btn btn-primary"
            >
              {isLoading ? (
                <>
                  <Spinner size={15} />
                  Đang phối…
                </>
              ) : (
                <>
                  Phối đồ
                  <ArrowRightIcon size={16} />
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    );
  }
);

ChatComposer.displayName = 'ChatComposer';
