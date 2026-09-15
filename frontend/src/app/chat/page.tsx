'use client';

import React, { useRef } from 'react';
import Link from 'next/link';
import { useStylistChat } from '@/hooks/useStylistChat';
import { ChatComposer, type ChatComposerRef } from '@/components/chat/ChatComposer';
import { ClarificationBanner } from '@/components/chat/ClarificationBanner';
import { ChatErrorBanner } from '@/components/chat/ChatErrorBanner';
import { RecommendationView } from '@/components/chat/RecommendationView';

const SUGGESTED_PROMPTS = [
  'Đi cafe ngoài trời ở Đà Lạt, se lạnh, muốn set đồ lịch sự nhẹ nhàng',
  'Đi làm văn phòng ngày hè ở Hà Nội, ưu tiên thoải mái thoáng mát',
  'Dự tiệc sinh nhật bạn thân buổi tối ở TP. Hồ Chí Minh, phong cách smart casual',
  'Dạo phố cuối tuần, thời tiết mát mẻ, phong cách tối giản',
];

export default function ChatPage() {
  const {
    status,
    response,
    error,
    isLoading,
    sendMessage,
    retry,
  } = useStylistChat();

  const composerRef = useRef<ChatComposerRef>(null);

  const handleSelectSuggestedPrompt = (prompt: string) => {
    composerRef.current?.setQueryText(prompt);
  };

  const handleFocusComposer = () => {
    composerRef.current?.focus();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/20 to-slate-100 dark:from-slate-950 dark:via-slate-900 dark:to-indigo-950/40 text-slate-800 dark:text-slate-100 transition-colors">
      {/* Sticky Header */}
      <header className="sticky top-0 z-40 w-full bg-white/80 dark:bg-slate-900/80 backdrop-blur-md border-b border-slate-200/80 dark:border-slate-800 shadow-xs">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-2 font-black text-lg tracking-tight text-indigo-600 dark:text-indigo-400 hover:opacity-90 transition"
            >
              <span className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center text-sm font-bold shadow-md shadow-indigo-200 dark:shadow-none">
                FS
              </span>
              <span>Fashion Stylist</span>
            </Link>
            <span className="text-slate-300 dark:text-slate-700">/</span>
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              Tư Vấn Stylist AI
            </span>
          </div>

          <nav className="flex items-center gap-2 sm:gap-4">
            <Link
              href="/wardrobe"
              className="px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              Tủ Đồ
            </Link>
            <Link
              href="/profile"
              className="px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition"
            >
              Gu Thời Trang
            </Link>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-3xl mx-auto px-4 py-8 sm:py-10 space-y-6">
        {/* Page Hero Title */}
        <div className="text-center sm:text-left space-y-1.5">
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
            Trợ Lý Phối Đồ Stylist AI
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Mô tả bối cảnh, sự kiện hoặc thời tiết. AI sẽ chọn lọc trang phục từ chính tủ đồ của bạn để tạo nên các set đồ hoàn chỉnh.
          </p>
        </div>

        {/* Chat Composer Form */}
        <ChatComposer
          ref={composerRef}
          onSend={sendMessage}
          isLoading={isLoading}
        />

        {/* Quick Suggestion Pills (Shown when idle or after completion) */}
        {status === 'idle' && (
          <div className="space-y-2 pt-2">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider block">
              Gợi ý bối cảnh thường gặp:
            </span>
            <div className="flex flex-wrap gap-2">
              {SUGGESTED_PROMPTS.map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSelectSuggestedPrompt(prompt)}
                  className="px-3 py-1.5 rounded-xl text-xs font-medium text-left bg-white dark:bg-slate-800/80 hover:bg-indigo-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 hover:text-indigo-600 dark:hover:text-indigo-400 border border-slate-200 dark:border-slate-700/80 shadow-2xs transition active:scale-98"
                >
                  💡 {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading State Skeleton */}
        {isLoading && (
          <div
            role="status"
            aria-live="polite"
            className="w-full bg-white dark:bg-slate-800/80 rounded-2xl border border-slate-200 dark:border-slate-700 p-6 space-y-4 shadow-sm animate-pulse"
          >
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-indigo-200 dark:bg-indigo-900/50"></div>
              <div className="space-y-1.5 flex-1">
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/3"></div>
                <div className="h-3 bg-slate-100 dark:bg-slate-800 rounded w-1/2"></div>
              </div>
            </div>

            <div className="h-16 bg-slate-100 dark:bg-slate-700/40 rounded-xl"></div>

            <div className="grid grid-cols-3 gap-3 pt-2">
              <div className="h-32 bg-slate-100 dark:bg-slate-700/40 rounded-xl"></div>
              <div className="h-32 bg-slate-100 dark:bg-slate-700/40 rounded-xl"></div>
              <div className="h-32 bg-slate-100 dark:bg-slate-700/40 rounded-xl"></div>
            </div>

            <p className="text-xs text-center text-indigo-600 dark:text-indigo-400 font-medium animate-bounce pt-2">
              Stylist AI đang rà soát tủ đồ và tính toán điểm phối màu...
            </p>
          </div>
        )}

        {/* Clarification State */}
        {status === 'clarification' && response?.clarification_question && (
          <ClarificationBanner
            question={response.clarification_question}
            onFocusComposer={handleFocusComposer}
          />
        )}

        {/* Error State */}
        {status === 'error' && error && (
          <ChatErrorBanner error={error} onRetry={retry} />
        )}

        {/* Success Recommendations State */}
        {status === 'success' && response && (
          <RecommendationView data={response} />
        )}
      </main>
    </div>
  );
}
